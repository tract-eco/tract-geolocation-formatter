# -*- coding: utf-8 -*-
"""
Land cover overlap check (SPEC-landcover-overlap) — QGIS and GDAL side.

Imported lazily by the main class, only when the check is ticked. Holds everything that
touches GDAL configuration, rasters, memory layers or the processing registry; the pure
logic is in ``landcover.py`` (plan DEC-9).

Rules this module keeps:

- GDAL HTTP options are set only inside ``gdal_http_scope`` and restored on exit, also
  after an exception (FR-4.4, AC-23).
- The one exception is ``GDAL_CURL_CA_BUNDLE``: when it is unset and HTTPS fails
  without it, it is set for the rest of the QGIS session, because QGIS renders the
  WorldCover layer after the check (DEC-10). An existing value is never changed.
- GDAL's exception mode is never changed; return values are checked (DEC-13).
- Messages go to the QGIS message log, not ``_log`` (DEC-12). Proxy credentials are
  never logged.
"""

import contextlib
import hashlib
import json
import math
import os
import tempfile

from osgeo import gdal, ogr
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsDistanceArea,
    QgsFeature,
    QgsGeometry,
    QgsMessageLog,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)

from . import landcover as lc

LOG_TAG = "TRACT Geolocation Formatter"

# Pixel size above which Project mode warns (FR-4 Project check 6): a pixel whose
# diagonal is longer than that of a 30 m square pixel.
COARSE_PIXEL_DIAGONAL_M = 30.0 * math.sqrt(2.0)

# Applied only for the duration of the Fetch-mode check.
HTTP_OPTIONS = {
    "GDAL_HTTP_TIMEOUT": "30",
    "GDAL_HTTP_CONNECTTIMEOUT": "10",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.vrt",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "100000000",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
}

CA_OPTION = "GDAL_CURL_CA_BUNDLE"


def log(message, level=None):
    """Write to the QGIS message log under the plugin's tab (DEC-12)."""
    if level is None:
        level = Qgis.MessageLevel.Info
    QgsMessageLog.logMessage(message, LOG_TAG, level)


# --------------------------------------------------------------------------- #
# GDAL configuration scope (FR-4.4)
# --------------------------------------------------------------------------- #

def proxy_options():
    """GDAL proxy options from QGIS's proxy settings, or ``{}`` when no proxy is set.

    Uses ``QgsNetworkAccessManager.fallbackProxy()``, which reflects the proxy the user
    configured in QGIS (Settings → Options → Network). System/default proxies are left
    to curl. The password is returned for GDAL only and must never be logged.
    """
    try:
        from qgis.core import QgsNetworkAccessManager
        from qgis.PyQt.QtNetwork import QNetworkProxy

        proxy = QgsNetworkAccessManager.instance().fallbackProxy()
    except Exception:
        return {}
    host = proxy.hostName()
    ptype = proxy.type()
    if not host or ptype in (
        QNetworkProxy.ProxyType.NoProxy,
        QNetworkProxy.ProxyType.DefaultProxy,
    ):
        return {}
    address = "{}:{}".format(host, proxy.port()) if proxy.port() > 0 else host
    if ptype == QNetworkProxy.ProxyType.Socks5Proxy:
        address = "socks5://" + address
    options = {"GDAL_HTTP_PROXY": address}
    if proxy.user():
        options["GDAL_HTTP_PROXYUSERPWD"] = "{}:{}".format(proxy.user(), proxy.password())
    return options


@contextlib.contextmanager
def gdal_http_scope(proxy=None):
    """Set the HTTP options for the check and restore the previous values on exit.

    ``proxy``: proxy options to apply (default: ``proxy_options()``). A proxy option the
    user already set for GDAL is kept as it is.
    """
    options = dict(HTTP_OPTIONS)
    for key, value in (proxy_options() if proxy is None else proxy).items():
        if gdal.GetConfigOption(key) is None:
            options[key] = value
    saved = {key: gdal.GetConfigOption(key) for key in options}
    try:
        for key, value in options.items():
            gdal.SetConfigOption(key, value)
        yield
    finally:
        for key, value in saved.items():
            gdal.SetConfigOption(key, value)


def ca_bundle_candidates():
    """CA bundle files to try, most specific first (DEC-10)."""
    candidates = []
    try:
        prefix = QgsApplication.prefixPath()        # macOS: …/QGIS.app/Contents/MacOS
        pkg = QgsApplication.pkgDataPath()          # macOS: …/Contents/Resources/qgis
        candidates += [
            os.path.join(prefix, "..", "Resources", "certs", "certs.pem"),
            os.path.join(pkg, "..", "certs", "certs.pem"),
        ]
    except Exception:
        pass
    # System bundles (macOS, Linux). No third-party package (e.g. certifi) is used:
    # the plugin imports only qgis, qgis.PyQt, osgeo and the standard library.
    candidates += ["/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"]
    seen = []
    for path in candidates:
        path = os.path.normpath(path)
        if path not in seen and os.path.isfile(path):
            seen.append(path)
    return seen


def ca_bundle_is_set():
    """True when GDAL or curl already has a CA bundle configured."""
    return bool(
        gdal.GetConfigOption(CA_OPTION)
        or gdal.GetConfigOption("CURL_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
    )


def ensure_ca_bundle(probe, candidates=None):
    """Make HTTPS work for GDAL when it doesn't, without changing anything that is set.

    ``probe()`` returns True when the canary tile can be read. Called only after a
    failed probe. If no CA bundle is configured, try each candidate: set it, clear the
    vsicurl cache, probe again. The first that works stays set for the QGIS session
    (DEC-10); if none works, the option is unset again. Returns True when a bundle
    was set and HTTPS now works.
    """
    if ca_bundle_is_set():
        return False
    for path in ca_bundle_candidates() if candidates is None else candidates:
        gdal.SetConfigOption(CA_OPTION, path)
        _clear_vsicurl_cache()
        if probe():
            log("GDAL had no CA certificate bundle; using {} for this QGIS session "
                "so the WorldCover layer can be read.".format(path))
            return True
    gdal.SetConfigOption(CA_OPTION, None)
    _clear_vsicurl_cache()
    return False


def _clear_vsicurl_cache():
    partial = getattr(gdal, "VSICurlPartialClearCache", None)
    if partial is not None:
        partial("/vsicurl/" + lc.WORLDCOVER_BASE_URL)
    else:
        gdal.VSICurlClearCache()


# --------------------------------------------------------------------------- #
# WorldCover resolution (FR-4 Fetch, DEC-6, DEC-11)
# --------------------------------------------------------------------------- #

class WorldCoverUnreachable(Exception):
    """The canary tile can't be read: network, TLS, proxy or DNS failure."""


def vsicurl_path(name):
    return "/vsicurl/" + lc.tile_url(name)


def vsi_exists(path):
    """True when GDAL can stat the path (a HEAD request for /vsicurl/)."""
    gdal.ErrorReset()
    return gdal.VSIStatL(path) is not None


def temp_dir():
    """The plugin's own subfolder of the system temp dir (never the output folder)."""
    return os.path.join(tempfile.gettempdir(), "tract_geolocation_formatter")


def vrt_path(tiles, directory=None):
    """VRT file for a tile set; the same tiles always map to the same name."""
    digest = hashlib.sha1(",".join(sorted(tiles)).encode("utf-8")).hexdigest()[:16]
    return os.path.join(directory or temp_dir(), "worldcover_{}.vrt".format(digest))


def build_vrt(path, sources):
    """Write a VRT mosaic of ``sources`` to ``path``; raise on failure."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gdal.ErrorReset()
    ds = gdal.BuildVRT(path, sources)
    if ds is None:
        raise RuntimeError("could not build the WorldCover mosaic ({})".format(
            gdal.GetLastErrorMsg() or "unknown GDAL error"))
    ds.FlushCache()
    ds = None
    return path


def resolve_worldcover(tiles, directory=None, exists=vsi_exists, make_vrt=build_vrt,
                       fix_tls=ensure_ca_bundle):
    """Find which tiles exist and return a single raster path for them.

    Returns ``(raster_path, present_tiles, missing_tiles)``; ``raster_path`` is ``None``
    when no tile exists (all plots then fall outside WorldCover coverage). Raises
    ``WorldCoverUnreachable`` when the canary tile can't be read even after trying a
    CA bundle. Must run inside ``gdal_http_scope``. The keyword arguments exist for tests.
    """
    canary = vsicurl_path(lc.CANARY_TILE)
    if not exists(canary) and not fix_tls(lambda: exists(canary)):
        raise WorldCoverUnreachable("cannot reach WorldCover")
    present, missing = [], []
    for name in tiles:
        if name == lc.CANARY_TILE or exists(vsicurl_path(name)):
            present.append(name)
        else:
            missing.append(name)  # 404, e.g. open ocean: skipped silently (FR-4.2)
    if not present:
        return None, present, missing
    if len(present) == 1:
        return vsicurl_path(present[0]), present, missing
    path = make_vrt(vrt_path(present, directory), [vsicurl_path(n) for n in present])
    return path, present, missing


# --------------------------------------------------------------------------- #
# Plots as memory layers
# --------------------------------------------------------------------------- #

def _qgs_geometry_from_geojson(geometry):
    ogr_geom = ogr.CreateGeometryFromJson(json.dumps(geometry))
    if ogr_geom is None:
        return None
    geom = QgsGeometry()
    geom.fromWkb(bytes(ogr_geom.ExportToIsoWkb()))
    return geom if not geom.isNull() else None


def build_plots_layer(fc):
    """Memory layer of the polygonal output features, keyed by their GeoJSON index.

    Returns ``(layer, geometries)``: an EPSG:4326 MultiPolygon memory layer with one
    integer field ``idx`` (the feature's index in ``fc["features"]``), and
    ``{idx: QgsGeometry}`` in EPSG:4326. A MultiPolygon is one plot (D9). Non-polygonal
    and empty features are left out. Z/M are dropped for the analysis only.
    """
    layer = QgsVectorLayer(
        "MultiPolygon?crs=EPSG:4326&field=idx:integer", "landcover_plots", "memory"
    )
    geometries = {}
    features = []
    for idx, feature in enumerate(fc.get("features") or []):
        geometry = (feature or {}).get("geometry") or {}
        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        geom = _qgs_geometry_from_geojson(geometry)
        if geom is None or geom.isEmpty():
            continue
        abstract = geom.get()
        abstract.dropZValue()
        abstract.dropMValue()
        geom.convertToMultiType()
        f = QgsFeature(layer.fields())
        f.setAttributes([idx])
        f.setGeometry(geom)
        features.append(f)
        geometries[idx] = geom
    if features and not layer.dataProvider().addFeatures(features)[0]:
        raise RuntimeError("could not build the plots layer for the land cover check")
    return layer, geometries


def plots_extent(geometries):
    """Bounding rectangle (EPSG:4326) of the plot geometries, or ``None``."""
    extent = None
    for geom in geometries.values():
        box = geom.boundingBox()
        if extent is None:
            extent = QgsRectangle(box)
        else:
            extent.combineExtentWith(box)
    return extent


def plot_bboxes(geometries):
    """``(xmin, ymin, xmax, ymax)`` per plot, for ``landcover.tiles_for_bboxes``."""
    return [
        (b.xMinimum(), b.yMinimum(), b.xMaximum(), b.yMaximum())
        for b in (g.boundingBox() for g in geometries.values())
    ]


def reproject_plots(layer, crs):
    """Copy of the plots layer in ``crs`` (FR-4 Project check 5); the raster is never warped.

    A plot that can't be transformed is left out, so it is reported as not assessed.
    """
    source_crs = layer.crs()
    if crs == source_crs:
        return layer
    transform = QgsCoordinateTransform(source_crs, crs, QgsProject.instance())
    out = QgsVectorLayer("MultiPolygon?field=idx:integer", "landcover_plots_reprojected", "memory")
    out.setCrs(crs)
    features = []
    for f in layer.getFeatures():
        geom = QgsGeometry(f.geometry())
        try:
            geom.transform(transform)
        except QgsCsException:
            continue
        g = QgsFeature(out.fields())
        g.setAttributes([f["idx"]])
        g.setGeometry(geom)
        features.append(g)
    if features and not out.dataProvider().addFeatures(features)[0]:
        raise RuntimeError("could not reproject the plots for the land cover check")
    return out


# --------------------------------------------------------------------------- #
# Zonal histogram (FR-5, DEC-2)
# --------------------------------------------------------------------------- #

_NATIVE_PROVIDER = []  # keeps a provider we registered alive (headless use)


def _zonal_histogram_algorithm():
    registry = QgsApplication.processingRegistry()
    alg = registry.createAlgorithmById("native:zonalhistogram")
    if alg is None:
        from qgis.analysis import QgsNativeAlgorithms

        provider = QgsNativeAlgorithms()
        if registry.addProvider(provider):
            _NATIVE_PROVIDER.append(provider)
        alg = registry.createAlgorithmById("native:zonalhistogram")
    if alg is None:
        raise RuntimeError("the QGIS zonal histogram algorithm is not available")
    return alg


def _histogram_key(suffix):
    if suffix.upper() == "NODATA":
        return lc.NODATA_KEY
    try:
        value = float(suffix)
    except ValueError:
        return None
    return int(value) if value.is_integer() else value


def run_zonal_histogram(raster_layer, band, plots_layer, feedback=None):
    """Pixel counts per plot: ``{idx: {value|"NODATA": count}}``.

    Runs ``native:zonalhistogram`` through the processing registry (no dependency on the
    Processing Python plugin). Pixels whose centre lies in the plot are counted; a plot
    with no pixel centre gets the one pixel it lies in. Plots outside the raster get no
    counts.
    """
    alg = _zonal_histogram_algorithm()
    context = QgsProcessingContext()
    context.setProject(QgsProject.instance())
    params = {
        "INPUT_RASTER": raster_layer,
        "RASTER_BAND": int(band),
        "INPUT_VECTOR": plots_layer,
        "COLUMN_PREFIX": "HISTO_",
        "OUTPUT": "memory:",
    }
    results, ok = alg.run(params, context, feedback or QgsProcessingFeedback())
    if not ok:
        raise RuntimeError("the zonal histogram failed")
    output = results.get("OUTPUT")
    out_layer = context.getMapLayer(output) if isinstance(output, str) else output
    if out_layer is None:
        raise RuntimeError("the zonal histogram returned no layer")
    columns = []
    for field in out_layer.fields():
        name = field.name()
        if name.startswith("HISTO_"):
            key = _histogram_key(name[len("HISTO_"):])
            if key is not None:
                columns.append((name, key))
    histograms = {}
    for f in out_layer.getFeatures():
        counts = {}
        for name, key in columns:
            value = f[name]
            try:
                n = int(value)
            except (TypeError, ValueError):
                n = 0
            if n:
                counts[key] = counts.get(key, 0) + n
        histograms[f["idx"]] = counts
    return histograms


def histograms_for_classes(sources, plots_layer, feedback=None, run=run_zonal_histogram):
    """Run the histogram once per distinct (raster, band) and share it (AC-11).

    ``sources``: ``{cls: (raster_layer, band)}``. Plots are reprojected to each raster's
    CRS when needed. Returns ``{cls: {idx: counts}}``; classes sharing a raster and band
    get the same dict.
    """
    cache = {}
    out = {}
    for cls in lc.CLASSES:
        if cls not in sources:
            continue
        raster, band = sources[cls]
        key = (raster.id() or raster.source(), int(band))
        if key not in cache:
            plots = reproject_plots(plots_layer, raster.crs())
            cache[key] = run(raster, int(band), plots, feedback)
        out[cls] = cache[key]
    return out


# --------------------------------------------------------------------------- #
# Project mode validation (FR-4 Project, checks 1–6)
# --------------------------------------------------------------------------- #

def parse_class_value(value):
    """Integer class value from the dialog text, or ``None`` when empty/invalid."""
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def pixel_diagonal_m(layer, extent_4326):
    """Pixel diagonal in metres, measured at the centre of the plot extent."""
    crs = layer.crs()
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    centre = extent_4326.center()
    to_layer = QgsCoordinateTransform(wgs84, crs, QgsProject.instance())
    c = to_layer.transform(QgsPointXY(centre))
    corner = QgsPointXY(c.x() + layer.rasterUnitsPerPixelX(), c.y() + layer.rasterUnitsPerPixelY())
    da = QgsDistanceArea()
    da.setSourceCrs(crs, QgsProject.instance().transformContext())
    da.setEllipsoid("EPSG:7030")
    return da.measureLine(c, corner)


def validate_project_class(layer, band, value, extent_4326):
    """Check one Project-mode class. Returns ``(class_value, error, warning)``.

    ``error`` is a user-facing message when the class can't run (it is then skipped);
    ``warning`` is a non-blocking note (coarse pixels). ``class_value`` is the parsed
    integer when there is no error.
    """
    name = layer.name() if layer is not None else ""
    if not isinstance(layer, QgsRasterLayer) or layer.providerType() != "gdal":
        return None, "{} is a web map layer; its pixels are colours, not classes.".format(name), None
    if not layer.isValid():
        return None, "{} can't be read.".format(name), None
    try:
        band = int(band)
    except (TypeError, ValueError):
        band = 0
    if band < 1 or band > layer.bandCount():
        return None, "Band {} does not exist in {}.".format(band, name), None
    if value is None or not str(value).strip():
        return None, "No class value set for {}.".format(name), None
    class_value = parse_class_value(value)
    if class_value is None:
        return None, "Class value '{}' for {} is not a whole number.".format(value, name), None
    if extent_4326 is None:
        return class_value, None, None
    try:
        to_wgs84 = QgsCoordinateTransform(
            layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance()
        )
        layer_extent = to_wgs84.transformBoundingBox(layer.extent())
    except QgsCsException:
        layer_extent = None
    if layer_extent is None or not layer_extent.intersects(extent_4326):
        return None, "The selected layer does not cover your plots.", None
    warning = None
    try:
        diagonal = pixel_diagonal_m(layer, extent_4326)
    except Exception:
        diagonal = 0.0
    if diagonal > COARSE_PIXEL_DIAGONAL_M:
        warning = ("{}: pixels are about {:.0f} m across; overlap results are approximate "
                   "for small plots.".format(name, diagonal / math.sqrt(2.0)))
    return class_value, None, warning


# --------------------------------------------------------------------------- #
# WorldCover map layer (FR-4 Fetch 5–6, D13)
# --------------------------------------------------------------------------- #

BUILT_UP_COLOUR = (230, 25, 25)    # red
WATER_COLOUR = (25, 90, 230)       # blue
LAYER_OPACITY = 0.7


def _layer_order(root):
    """Layer ids in layer-tree order, top to bottom (depth first)."""
    return [node.layerId() for node in root.findLayers()]


def _remove_groups(project, name):
    """Remove every group called ``name`` and the layers in it (re-run, AC-20)."""
    root = project.layerTreeRoot()
    while True:
        group = root.findGroup(name)
        if group is None:
            return
        layer_ids = [node.layerId() for node in group.findLayers()]
        parent = group.parent() or root
        parent.removeChildNode(group)
        if layer_ids:
            project.removeMapLayers(layer_ids)


def _insert_group(project, name, anchor_layer_ids):
    """New group directly below the lowest anchor layer; at the top if none is in the tree."""
    root = project.layerTreeRoot()
    order = _layer_order(root)
    anchors = [lid for lid in anchor_layer_ids if lid in order]
    if not anchors:
        return root.insertGroup(0, name)
    lowest = max(anchors, key=order.index)
    node = root.findLayer(lowest)
    parent = node.parent() or root
    index = 0
    for i, child in enumerate(parent.children()):
        if getattr(child, "layerId", None) is not None and child.layerId() == lowest:
            index = i
            break
    return parent.insertGroup(index + 1, name)


def _style_worldcover(layer):
    """Paletted: 50 red, 80 blue, every other value not drawn; 70 % opacity."""
    from qgis.core import QgsPalettedRasterRenderer
    from qgis.PyQt.QtGui import QColor

    classes = [
        QgsPalettedRasterRenderer.Class(lc.BUILT_UP_VALUE, QColor(*BUILT_UP_COLOUR), "Built-up"),
        QgsPalettedRasterRenderer.Class(lc.WATER_VALUE, QColor(*WATER_COLOUR), "Permanent water bodies"),
    ]
    renderer = QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes)
    renderer.setOpacity(LAYER_OPACITY)
    layer.setRenderer(renderer)


def _set_attribution(layer):
    """D13: attribution on the layer and in its metadata (rights + licence)."""
    server_properties = getattr(layer, "serverProperties", None)
    if server_properties is not None and hasattr(server_properties(), "setAttribution"):
        server_properties().setAttribution(lc.ATTRIBUTION)
    elif hasattr(layer, "setAttribution"):
        layer.setAttribution(lc.ATTRIBUTION)
    metadata = layer.metadata()
    metadata.setTitle(lc.LAYER_NAME)
    metadata.setRights([lc.ATTRIBUTION])
    metadata.setLicenses([lc.LICENCE])
    layer.setMetadata(metadata)


def layer_attribution(layer):
    """The attribution text set by ``_set_attribution`` (for tests and checks)."""
    server_properties = getattr(layer, "serverProperties", None)
    if server_properties is not None and hasattr(server_properties(), "attribution"):
        return server_properties().attribution()
    return layer.attribution() if hasattr(layer, "attribution") else ""


def add_worldcover_layer(raster_path, anchor_layer_ids, project=None):
    """Add the styled WorldCover layer in its group, below the run's lowest layer.

    Replaces any existing ``TRACT land cover check`` group. Returns the layer. Raises
    when the raster can't be opened; the caller logs it (the CSV and fields stay valid).
    """
    project = project or QgsProject.instance()
    layer = QgsRasterLayer(raster_path, lc.LAYER_NAME, "gdal")
    if not layer.isValid():
        raise RuntimeError("the WorldCover layer could not be opened")
    _style_worldcover(layer)
    _set_attribution(layer)
    _remove_groups(project, lc.GROUP_NAME)
    group = _insert_group(project, lc.GROUP_NAME, anchor_layer_ids)
    project.addMapLayer(layer, False)
    node = group.addLayer(layer)
    group.setItemVisibilityChecked(True)
    node.setItemVisibilityChecked(True)
    return layer
