"""
Tests for the QGIS/GDAL side of the land cover check (SPEC-landcover-overlap, Task 2).

Needs QGIS's Python (qgis.core + osgeo); skipped elsewhere. Offline: fixture rasters are
generated in a temp folder. Network tests run only with TRACT_NETWORK_TESTS=1.

    python -m unittest test_landcover_source -v      (from tests/, QGIS Python)
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "fixtures"))

try:
    from osgeo import gdal  # noqa: F401
    from qgis.core import QgsRasterLayer  # noqa: F401

    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

NETWORK = os.environ.get("TRACT_NETWORK_TESTS") == "1"


def setUpModule():
    if not QGIS_AVAILABLE:
        return
    from _qgis_app import qgis_app

    qgis_app()


@unittest.skipUnless(QGIS_AVAILABLE, "Requires QGIS Python environment")
class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from make_landcover_fixture import make_fixture

        from tract_geolocation_formatter import landcover as lc
        from tract_geolocation_formatter import landcover_source as src

        cls.lc = lc
        cls.src = src
        cls.tmp = tempfile.mkdtemp(prefix="tract_landcover_")
        cls.fx = make_fixture(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def raster(self, key, name=None):
        from qgis.core import QgsRasterLayer

        layer = QgsRasterLayer(self.fx[key], name or key, "gdal")
        self.assertTrue(layer.isValid(), key)
        return layer

    def plots(self):
        return self.src.build_plots_layer(self.fx["plots"])


class HttpScopeTests(_Base):
    """AC-23: options restored after the check, on success and on failure."""

    KEYS = ("GDAL_HTTP_TIMEOUT", "GDAL_HTTP_MAX_RETRY", "VSI_CACHE", "GDAL_HTTP_PROXY",
            "GDAL_HTTP_PROXYUSERPWD")

    def setUp(self):
        from osgeo import gdal

        self.gdal = gdal
        self.saved = {k: gdal.GetConfigOption(k) for k in self.KEYS}
        gdal.SetConfigOption("GDAL_HTTP_TIMEOUT", "999")
        gdal.SetConfigOption("GDAL_HTTP_MAX_RETRY", None)
        gdal.SetConfigOption("GDAL_HTTP_PROXY", None)
        gdal.SetConfigOption("GDAL_HTTP_PROXYUSERPWD", None)

    def tearDown(self):
        for k, v in self.saved.items():
            self.gdal.SetConfigOption(k, v)

    def test_set_inside_restored_after(self):
        with self.src.gdal_http_scope(proxy={}):
            self.assertEqual(self.gdal.GetConfigOption("GDAL_HTTP_TIMEOUT"), "30")
            self.assertEqual(self.gdal.GetConfigOption("GDAL_HTTP_MAX_RETRY"), "3")
        self.assertEqual(self.gdal.GetConfigOption("GDAL_HTTP_TIMEOUT"), "999")
        self.assertIsNone(self.gdal.GetConfigOption("GDAL_HTTP_MAX_RETRY"))

    def test_restored_after_exception(self):
        with self.assertRaises(ValueError):
            with self.src.gdal_http_scope(proxy={"GDAL_HTTP_PROXY": "proxy.local:3128"}):
                raise ValueError("boom")
        self.assertEqual(self.gdal.GetConfigOption("GDAL_HTTP_TIMEOUT"), "999")
        self.assertIsNone(self.gdal.GetConfigOption("GDAL_HTTP_PROXY"))

    def test_proxy_applied_and_removed(self):
        proxy = {"GDAL_HTTP_PROXY": "proxy.local:3128", "GDAL_HTTP_PROXYUSERPWD": "u:p"}
        with self.src.gdal_http_scope(proxy=proxy):
            self.assertEqual(self.gdal.GetConfigOption("GDAL_HTTP_PROXY"), "proxy.local:3128")
            self.assertEqual(self.gdal.GetConfigOption("GDAL_HTTP_PROXYUSERPWD"), "u:p")
        self.assertIsNone(self.gdal.GetConfigOption("GDAL_HTTP_PROXY"))
        self.assertIsNone(self.gdal.GetConfigOption("GDAL_HTTP_PROXYUSERPWD"))

    def test_existing_user_proxy_kept(self):
        self.gdal.SetConfigOption("GDAL_HTTP_PROXY", "mine:8080")
        with self.src.gdal_http_scope(proxy={"GDAL_HTTP_PROXY": "qgis:3128"}):
            self.assertEqual(self.gdal.GetConfigOption("GDAL_HTTP_PROXY"), "mine:8080")
        self.assertEqual(self.gdal.GetConfigOption("GDAL_HTTP_PROXY"), "mine:8080")

    def test_proxy_options_without_qgis_proxy(self):
        self.assertEqual(self.src.proxy_options(), {})


class CaBundleTests(_Base):
    """DEC-10: an existing CA bundle is never changed; an unset one is filled only if it helps."""

    def setUp(self):
        from osgeo import gdal

        self.gdal = gdal
        self.saved = {k: gdal.GetConfigOption(k) for k in ("GDAL_CURL_CA_BUNDLE", "CURL_CA_BUNDLE")}
        gdal.SetConfigOption("GDAL_CURL_CA_BUNDLE", None)
        gdal.SetConfigOption("CURL_CA_BUNDLE", None)
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("SSL_CERT_FILE", None)
        os.environ.pop("CURL_CA_BUNDLE", None)
        os.environ.pop("GDAL_CURL_CA_BUNDLE", None)
        fd, self.pem = tempfile.mkstemp(suffix=".pem")
        os.close(fd)

    def tearDown(self):
        self.env.stop()
        os.remove(self.pem)
        for k, v in self.saved.items():
            self.gdal.SetConfigOption(k, v)

    def test_existing_value_untouched(self):
        self.gdal.SetConfigOption("GDAL_CURL_CA_BUNDLE", "/my/bundle.pem")
        self.assertFalse(self.src.ensure_ca_bundle(lambda: True, candidates=[self.pem]))
        self.assertEqual(self.gdal.GetConfigOption("GDAL_CURL_CA_BUNDLE"), "/my/bundle.pem")

    def test_kept_when_it_fixes_https(self):
        seen = []
        probe = lambda: seen.append(self.gdal.GetConfigOption("GDAL_CURL_CA_BUNDLE")) or True  # noqa: E731
        self.assertTrue(self.src.ensure_ca_bundle(probe, candidates=[self.pem]))
        self.assertEqual(seen, [self.pem])
        self.assertEqual(self.gdal.GetConfigOption("GDAL_CURL_CA_BUNDLE"), self.pem)

    def test_unset_again_when_nothing_helps(self):
        self.assertFalse(self.src.ensure_ca_bundle(lambda: False, candidates=[self.pem]))
        self.assertIsNone(self.gdal.GetConfigOption("GDAL_CURL_CA_BUNDLE"))

    def test_candidates_exist(self):
        for path in self.src.ca_bundle_candidates():
            self.assertTrue(os.path.isfile(path))


class ResolveWorldCoverTests(_Base):
    """FR-4 Fetch / DEC-11 with fake existence checks (offline)."""

    def _resolve(self, existing, tiles, fix=lambda probe: False):
        calls = []

        def exists(path):
            return any(path.endswith("_{}_Map.tif".format(t)) for t in existing)

        def make_vrt(path, sources):
            calls.append((path, sources))
            return path

        result = self.src.resolve_worldcover(
            tiles, directory=self.tmp, exists=exists, make_vrt=make_vrt, fix_tls=fix
        )
        return result, calls

    def test_unreachable_when_canary_fails(self):
        with self.assertRaises(self.src.WorldCoverUnreachable):
            self._resolve(existing=[], tiles=["N36E000"])

    def test_canary_fixed_by_ca_bundle(self):
        state = {"ok": False}

        def fix(probe):
            state["ok"] = True
            return True

        def exists(path):
            return state["ok"]

        path, present, missing = self.src.resolve_worldcover(
            ["N36E000"], directory=self.tmp, exists=exists, make_vrt=None, fix_tls=fix
        )
        self.assertEqual(present, ["N36E000"])
        self.assertTrue(path.startswith("/vsicurl/https://esa-worldcover"))

    def test_single_tile_is_vsicurl_path(self):
        (path, present, missing), calls = self._resolve(["N51W003", "N36E000"], ["N36E000"])
        self.assertEqual(path, "/vsicurl/" + self.lc.tile_url("N36E000"))
        self.assertEqual(calls, [])

    def test_missing_tile_skipped_silently(self):
        """AC-22 (resolver part): a 404 tile is listed as missing, not an error."""
        (path, present, missing), calls = self._resolve(
            ["N51W003", "N36E000"], ["N36E000", "S30W120"]
        )
        self.assertEqual(present, ["N36E000"])
        self.assertEqual(missing, ["S30W120"])

    def test_no_tile_exists(self):
        (path, present, missing), _ = self._resolve(["N51W003"], ["S30W120"])
        self.assertIsNone(path)
        self.assertEqual(missing, ["S30W120"])

    def test_two_tiles_build_vrt_in_temp_folder(self):
        """AC-19 (resolver part): several tiles → one VRT in the given temp folder."""
        (path, present, _), calls = self._resolve(
            ["N51W003", "N51E000"], ["N51E000", "N51W003"]
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(os.path.dirname(path), self.tmp)
        self.assertTrue(os.path.basename(path).startswith("worldcover_"))
        self.assertEqual(calls[0][1], ["/vsicurl/" + self.lc.tile_url(t) for t in present])

    def test_vrt_name_stable_and_in_plugin_temp_dir(self):
        a = self.src.vrt_path(["N51W003", "N51E000"])
        b = self.src.vrt_path(["N51E000", "N51W003"])
        self.assertEqual(a, b)
        self.assertEqual(os.path.dirname(a), self.src.temp_dir())
        self.assertTrue(self.src.temp_dir().startswith(tempfile.gettempdir()))

    def test_build_vrt_of_local_rasters(self):
        out = os.path.join(self.tmp, "vrt", "mosaic.vrt")
        self.src.build_vrt(out, [self.fx["main"], self.fx["outside"]])
        from qgis.core import QgsRasterLayer

        self.assertTrue(QgsRasterLayer(out, "mosaic", "gdal").isValid())


class PlotsLayerTests(_Base):
    def test_polygonal_features_only_with_source_index(self):
        layer, geoms = self.plots()
        self.assertEqual(sorted(geoms), [0, 1, 2, 3, 4])
        self.assertEqual(sorted(f["idx"] for f in layer.getFeatures()), [0, 1, 2, 3, 4])
        self.assertEqual(layer.crs().authid(), "EPSG:4326")

    def test_multipolygon_is_one_plot(self):
        _, geoms = self.plots()
        self.assertTrue(geoms[4].isMultipart())
        self.assertEqual(geoms[4].constGet().numGeometries(), 2)

    def test_z_dropped(self):
        fc = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0, 5], [1, 0, 5], [1, 1, 5], [0, 0, 5]]]},
        }]}
        layer, geoms = self.src.build_plots_layer(fc)
        self.assertEqual(layer.featureCount(), 1)
        self.assertFalse(geoms[0].constGet().is3D())

    def test_bboxes_feed_the_tile_resolver(self):
        _, geoms = self.plots()
        self.assertEqual(
            self.lc.tiles_for_bboxes(self.src.plot_bboxes(geoms)), ["N48E009", "N48E018"]
        )


class ZonalHistogramTests(_Base):
    def test_counts_match_fixture(self):
        from make_landcover_fixture import EXPECTED

        layer, _ = self.plots()
        hist = self.src.run_zonal_histogram(self.raster("main"), 1, layer)
        for idx, expected in EXPECTED.items():
            self.assertEqual(hist.get(idx, {}), expected, idx)

    def test_end_to_end_with_compute(self):
        """D6 on real histogram counts: the mixed plot is 50 % water, nodata included."""
        layer, geoms = self.plots()
        hist = self.src.run_zonal_histogram(self.raster("main"), 1, layer)
        areas = {idx: 1000.0 for idx in geoms}
        r = self.lc.compute_landcover(
            {self.lc.WATER: hist, self.lc.BUILT_UP: hist},
            {self.lc.WATER: 80, self.lc.BUILT_UP: 50}, areas, plot_order=sorted(geoms),
        )
        self.assertAlmostEqual(r.values[self.lc.WATER][2][0], 50.0)
        self.assertIsNone(r.values[self.lc.WATER][3])
        self.assertAlmostEqual(r.values[self.lc.BUILT_UP][4][0], 4 / 14 * 100)
        self.assertEqual(r.count(self.lc.WATER), 3)
        self.assertEqual(r.count(self.lc.BUILT_UP), 2)

    def test_ac11_shared_layer_and_band_runs_once(self):
        layer, _ = self.plots()
        raster = self.raster("main")
        calls = []

        def run(r, band, plots, feedback=None):
            calls.append((r.id(), band))
            return {0: {80: 1}}

        out = self.src.histograms_for_classes(
            {self.lc.WATER: (raster, 1), self.lc.BUILT_UP: (raster, 1)}, layer, run=run
        )
        self.assertEqual(len(calls), 1)
        self.assertIs(out[self.lc.WATER], out[self.lc.BUILT_UP])

    def test_different_bands_run_separately(self):
        layer, _ = self.plots()
        raster = self.raster("three_band")
        calls = []

        def run(r, band, plots, feedback=None):
            calls.append(band)
            return {}

        self.src.histograms_for_classes(
            {self.lc.WATER: (raster, 2), self.lc.BUILT_UP: (raster, 3)}, layer, run=run
        )
        self.assertEqual(calls, [2, 3])

    def test_ac15_multi_band_counts_only_own_band(self):
        layer, _ = self.plots()
        raster = self.raster("three_band")
        hists = self.src.histograms_for_classes(
            {self.lc.WATER: (raster, 2), self.lc.BUILT_UP: (raster, 3)}, layer
        )
        self.assertEqual(hists[self.lc.WATER][0].get(7), 80)   # lake: water band
        self.assertIsNone(hists[self.lc.BUILT_UP][0].get(7))   # lake: not in built-up band
        self.assertEqual(hists[self.lc.BUILT_UP][1].get(7), 25)
        self.assertIsNone(hists[self.lc.WATER][1].get(7))

    def test_ac14_projected_raster_reprojects_plots(self):
        from make_landcover_fixture import UTM_EPSG, utm_rect
        from osgeo import gdal
        from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                               QgsPointXY, QgsProject)

        to_wgs = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:{}".format(UTM_EPSG)),
            QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())

        def ring(x0, y0, x1, y1):
            pts = [to_wgs.transform(QgsPointXY(x, y)) for x, y in utm_rect(x0, y0, x1, y1)]
            return [[p.x(), p.y()] for p in pts]

        # Fully in the water half, and straddling the water/other boundary (x = 571800).
        fc = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Polygon", "coordinates": [ring(571620, 5538500, 571700, 5538700)]}},
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Polygon", "coordinates": [ring(571750, 5538500, 571850, 5538700)]}},
        ]}
        layer, _ = self.src.build_plots_layer(fc)
        with open(self.fx["utm"], "rb") as fh:
            before = hashlib.sha1(fh.read()).hexdigest()

        utm = self.raster("utm")
        h_utm = self.src.histograms_for_classes({self.lc.WATER: (utm, 1)}, layer)[self.lc.WATER]
        warped = os.path.join(self.tmp, "utm_as_4326.tif")
        ds = gdal.Warp(warped, self.fx["utm"], dstSRS="EPSG:4326", resampleAlg="near",
                       xRes=0.0001, yRes=0.0001)
        ds = None  # close it so the file is complete before QGIS opens it
        from qgis.core import QgsRasterLayer

        h_wgs = self.src.histograms_for_classes(
            {self.lc.WATER: (QgsRasterLayer(warped, "w", "gdal"), 1)}, layer)[self.lc.WATER]

        def pct(h, idx):
            return h[idx].get(80, 0) / sum(h[idx].values()) * 100

        self.assertEqual(pct(h_utm, 0), 100.0)
        self.assertEqual(pct(h_wgs, 0), 100.0)
        self.assertAlmostEqual(pct(h_utm, 1), 50.0, delta=10)
        self.assertAlmostEqual(pct(h_utm, 1), pct(h_wgs, 1), delta=10)
        with open(self.fx["utm"], "rb") as fh:
            self.assertEqual(hashlib.sha1(fh.read()).hexdigest(), before)


class ProjectValidationTests(_Base):
    def extent(self):
        _, geoms = self.plots()
        geoms.pop(3)  # the far "outside" plot would stretch the extent to lon 20
        return self.src.plots_extent(geoms)

    def test_valid_class(self):
        value, error, warning = self.src.validate_project_class(self.raster("main"), 1, "80", self.extent())
        self.assertEqual((value, error, warning), (80, None, None))

    def test_ac12_web_layer_rejected(self):
        from qgis.core import QgsRasterLayer

        xyz = QgsRasterLayer("type=xyz&url=http://127.0.0.1:9/{z}/{x}/{y}.png&zmax=19&zmin=0",
                             "Basemap", "wms")
        _, error, _ = self.src.validate_project_class(xyz, 1, "80", self.extent())
        self.assertEqual(error, "Basemap is a web map layer; its pixels are colours, not classes.")

    def test_ac12_missing_band(self):
        _, error, _ = self.src.validate_project_class(self.raster("main", "lc"), 2, "80", self.extent())
        self.assertEqual(error, "Band 2 does not exist in lc.")

    def test_ac12_empty_value(self):
        _, error, _ = self.src.validate_project_class(self.raster("main", "lc"), 1, "  ", self.extent())
        self.assertEqual(error, "No class value set for lc.")

    def test_ac12_non_integer_value(self):
        _, error, _ = self.src.validate_project_class(self.raster("main", "lc"), 1, "8.5", self.extent())
        self.assertEqual(error, "Class value '8.5' for lc is not a whole number.")

    def test_ac13_layer_not_covering_plots(self):
        _, error, _ = self.src.validate_project_class(self.raster("outside"), 1, "80", self.extent())
        self.assertEqual(error, "The selected layer does not cover your plots.")

    def test_ac17_coarse_pixels_warn_but_run(self):
        value, error, warning = self.src.validate_project_class(
            self.raster("coarse", "coarse"), 1, 80, self.extent())
        self.assertEqual(value, 80)
        self.assertIsNone(error)
        self.assertIn("coarse: pixels are about", warning)

    def test_projected_raster_ten_metre_pixels_no_warning(self):
        _, error, warning = self.src.validate_project_class(self.raster("utm"), 1, 80, None)
        self.assertIsNone(error)
        self.assertIsNone(warning)

    def test_parse_class_value(self):
        p = self.src.parse_class_value
        self.assertEqual([p("7"), p(" 50 "), p(80), p(""), p(None), p("x"), p("1.0")],
                         [7, 50, 80, None, None, None, None])


class WorldCoverLayerTests(_Base):
    """FR-4 Fetch 5–6 / D13: group placement, style, attribution, replacement (offline)."""

    def setUp(self):
        from qgis.core import QgsProject, QgsVectorLayer

        self.project = QgsProject()
        self.output = QgsVectorLayer("Polygon?crs=EPSG:4326", "out.geojson", "memory")
        self.basemap = QgsVectorLayer("Polygon?crs=EPSG:4326", "basemap", "memory")
        # Tree: out.geojson (top), basemap (bottom), built explicitly.
        self.project.addMapLayers([self.basemap, self.output], False)
        root = self.project.layerTreeRoot()
        root.addLayer(self.output)
        root.addLayer(self.basemap)

    def tearDown(self):
        self.project.removeAllMapLayers()
        self.project.clear()

    def _tree(self):
        root = self.project.layerTreeRoot()
        return [c.name() for c in root.children()]

    def test_ac18_group_below_run_layer_styled_visible(self):
        from qgis.core import QgsPalettedRasterRenderer

        layer = self.src.add_worldcover_layer(self.fx["main"], [self.output.id()], self.project)
        self.assertEqual(self._tree(), ["out.geojson", self.lc.GROUP_NAME, "basemap"])
        group = self.project.layerTreeRoot().findGroup(self.lc.GROUP_NAME)
        self.assertTrue(group.isVisible())
        self.assertEqual([n.layerId() for n in group.findLayers()], [layer.id()])
        self.assertTrue(group.findLayers()[0].isVisible())
        self.assertEqual(layer.name(), "WorldCover 2021: water & built-up")
        renderer = layer.renderer()
        self.assertIsInstance(renderer, QgsPalettedRasterRenderer)
        colours = {int(c.value): c.color.name() for c in renderer.classes()}
        self.assertEqual(set(colours), {50, 80})
        self.assertEqual(colours[50], "#e61919")
        self.assertEqual(colours[80], "#195ae6")
        self.assertAlmostEqual(renderer.opacity(), 0.7)
        self.assertEqual(self.src.layer_attribution(layer), self.lc.ATTRIBUTION)
        self.assertEqual(layer.metadata().rights(), [self.lc.ATTRIBUTION])
        self.assertEqual(layer.metadata().licenses(), ["CC BY 4.0"])

    def test_below_lowest_of_several_run_layers(self):
        from qgis.core import QgsVectorLayer

        split = QgsVectorLayer("Polygon?crs=EPSG:4326", "out-1.geojson", "memory")
        self.project.addMapLayer(split, False)
        self.project.layerTreeRoot().insertLayer(0, split)  # top of the tree
        self.src.add_worldcover_layer(self.fx["main"], [split.id(), self.output.id()], self.project)
        self.assertEqual(self._tree(), ["out-1.geojson", "out.geojson", self.lc.GROUP_NAME, "basemap"])

    def test_anchor_inside_a_subgroup(self):
        root = self.project.layerTreeRoot()
        sub = root.insertGroup(0, "my plots")
        node = root.findLayer(self.output.id())
        sub.addChildNode(node.clone())  # move into the subgroup; the layer stays loaded
        root.removeChildNode(node)
        self.src.add_worldcover_layer(self.fx["main"], [self.output.id()], self.project)
        self.assertEqual([c.name() for c in sub.children()], ["out.geojson", self.lc.GROUP_NAME])

    def test_no_anchor_goes_to_top(self):
        self.src.add_worldcover_layer(self.fx["main"], [], self.project)
        self.assertEqual(self._tree()[0], self.lc.GROUP_NAME)

    def test_ac20_rerun_replaces_group_and_layer(self):
        first = self.src.add_worldcover_layer(self.fx["main"], [self.output.id()], self.project)
        first_id = first.id()
        second = self.src.add_worldcover_layer(self.fx["main"], [self.output.id()], self.project)
        self.assertEqual(self._tree().count(self.lc.GROUP_NAME), 1)
        self.assertIsNone(self.project.mapLayer(first_id))
        self.assertIsNotNone(self.project.mapLayer(second.id()))

    def test_invalid_raster_raises_and_changes_nothing(self):
        with self.assertRaises(RuntimeError):
            self.src.add_worldcover_layer(os.path.join(self.tmp, "missing.tif"),
                                          [self.output.id()], self.project)
        self.assertEqual(self._tree(), ["out.geojson", "basemap"])


@unittest.skipUnless(QGIS_AVAILABLE and NETWORK, "network test: set TRACT_NETWORK_TESTS=1")
class NetworkSmokeTests(_Base):
    def test_resolve_two_tiles_and_404(self):
        with self.src.gdal_http_scope():
            path, present, missing = self.src.resolve_worldcover(
                ["N51E000", "N51W003", "S30W120"], directory=self.tmp)
        self.assertEqual(present, ["N51E000", "N51W003"])
        self.assertEqual(missing, ["S30W120"])
        self.assertTrue(path.endswith(".vrt"))


if __name__ == "__main__":
    unittest.main()
