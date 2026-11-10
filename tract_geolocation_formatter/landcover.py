# -*- coding: utf-8 -*-
"""
Land cover overlap check (SPEC-landcover-overlap) — pure logic, standard library only.

What lives here (plan DEC-9):

- WorldCover tile naming and the tile resolver (FR-3, DEC-4).
- The per-plot computation from zonal-histogram counts (FR-5, D6–D8).
- The GeoJSON properties (FR-10) and landcover CSV rows (FR-6) built from it.
- Constants and the plain config/outcome containers shared with the main class.

Everything touching GDAL or QGIS objects is in ``landcover_source.py``. This module is
intentionally free of any QGIS import so it unit-tests under any Python 3.9+.

Histogram input format, per class: ``{plot_index: {key: pixel_count}}`` where ``key`` is
an ``int`` class value or ``"NODATA"``. A plot index missing from the histogram counts as
zero pixels (no coverage).
"""

import math
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

WORLDCOVER_BASE_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
WORLDCOVER_TILE_TEMPLATE = "ESA_WorldCover_10m_2021_v200_{}_Map.tif"
# A tile known to exist (HTTP 200, verified 2026-11-09), read first to tell a missing
# tile from an unreachable bucket (DEC-11).
CANARY_TILE = "N51W003"
TILE_SIZE_DEG = 3

WATER = "water"
BUILT_UP = "built_up"
NOT_ASSESSED = "not_assessed"
CLASSES = (WATER, BUILT_UP)

WATER_VALUE = 80      # WorldCover "Permanent water bodies"
BUILT_UP_VALUE = 50   # WorldCover "Built-up"
FETCH_CLASS_VALUES = {WATER: WATER_VALUE, BUILT_UP: BUILT_UP_VALUE}

SOURCE_FETCH = "ESA WorldCover 2021 v200"
ATTRIBUTION = (
    "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) "
    "processed by ESA WorldCover consortium"
)
LICENCE = "CC BY 4.0"

GROUP_NAME = "TRACT land cover check"
LAYER_NAME = "WorldCover 2021: water & built-up"
MAX_TILES_WITHOUT_CONFIRM = 12

MODE_FETCH = "fetch"
MODE_PROJECT = "project"

# FR-10: (area field, percent field) per class.
FIELD_NAMES = {
    WATER: ("WaterOverlap_m2", "WaterOverlap_pct"),
    BUILT_UP: ("BuiltUpOverlap_m2", "BuiltUpOverlap_pct"),
}
ALL_FIELD_NAMES = tuple(name for cls in CLASSES for name in FIELD_NAMES[cls])

# FR-6
CSV_FIELDNAMES = [
    "feature_id",
    "NodeID",
    "PlotID",
    "class",
    "overlap_area_m2",
    "overlap_pct",
    "plot_area_m2",
    "source",
]

NODATA_KEY = "NODATA"

# Class statuses in an outcome.
STATUS_RAN = "ran"
STATUS_NOT_CHECKED = "not_checked"
STATUS_NOT_RUN = "not_run"


# --------------------------------------------------------------------------- #
# Tile resolver (FR-3)
# --------------------------------------------------------------------------- #

def tile_name(lat0, lon0):
    """WorldCover tile name for the cell whose lower-left corner is (lat0, lon0).

    Both are multiples of 3 degrees. ``tile_name(-3, -60)`` → ``"S03W060"``.
    """
    lat0 = int(lat0)
    lon0 = int(lon0)
    lat = "{}{:02d}".format("N" if lat0 >= 0 else "S", abs(lat0))
    lon = "{}{:03d}".format("E" if lon0 >= 0 else "W", abs(lon0))
    return lat + lon


def tile_url(name):
    """HTTPS URL of a tile by name (no ``/vsicurl/`` prefix)."""
    return WORLDCOVER_BASE_URL + WORLDCOVER_TILE_TEMPLATE.format(name)


def _cell_range(vmin, vmax, lo_limit, hi_limit):
    """Cell indices (multiples of TILE_SIZE_DEG) covering [vmin, vmax] (DEC-4).

    The max edge lying exactly on a multiple of 3 doesn't pull in the next cell; a
    degenerate range on a multiple of 3 maps to the cell starting there.
    """
    lo = math.floor(vmin / TILE_SIZE_DEG)
    hi = math.ceil(vmax / TILE_SIZE_DEG) - 1
    if hi < lo:
        hi = lo
    lo = max(lo, lo_limit)
    hi = min(hi, hi_limit)
    return range(lo, hi + 1)


def tiles_for_bboxes(bboxes):
    """Sorted, de-duplicated tile names whose cell intersects at least one bbox.

    ``bboxes``: iterable of ``(xmin, ymin, xmax, ymax)`` in EPSG:4326 degrees.
    Only cells touched by a plot bbox are returned, not every cell of the overall
    extent (AC-6). Antimeridian-crossing boxes are out of scope.
    """
    names = set()
    for xmin, ymin, xmax, ymax in bboxes:
        # Latitude cells -30..29 (-90..87), longitude cells -60..59 (-180..177).
        for lat_cell in _cell_range(ymin, ymax, -30, 29):
            for lon_cell in _cell_range(xmin, xmax, -60, 59):
                names.add(tile_name(lat_cell * TILE_SIZE_DEG, lon_cell * TILE_SIZE_DEG))
    return sorted(names)


# --------------------------------------------------------------------------- #
# Config and outcome containers
# --------------------------------------------------------------------------- #

@dataclass
class ClassSpec:
    """Project-mode reference for one class: a raster layer, a band and a class value."""

    layer_id: str
    band: int
    value: object  # int when valid; kept raw so validation can report a bad entry


@dataclass
class LandcoverConfig:
    """Dialog state for one run, read once at the start (plan § _run_landcover_check)."""

    enabled: bool = False
    mode: str = MODE_FETCH
    # Project mode only: class key -> ClassSpec, or None for "do not check this class".
    classes: dict = field(default_factory=dict)


@dataclass
class LandcoverResult:
    """Pure result of ``compute_landcover``.

    - ``classes``: class keys that were computed, in CLASSES order.
    - ``plot_order``: plot indices in output order.
    - ``values[cls][idx]``: ``(overlap_pct, overlap_area_m2)``, unrounded, or ``None``
      when the plot has no reference pixels for that class (``not_assessed``).
    - ``class_pixels[cls][idx]``: pixel count of the class (0 for not assessed).
    - ``plot_areas[idx]``: plot area in m² (AREA_CRS).
    """

    classes: tuple
    plot_order: list
    values: dict
    class_pixels: dict
    plot_areas: dict

    def reported(self, cls, idx):
        """D7: a plot is reported for a class when it holds at least one class pixel."""
        return self.class_pixels[cls].get(idx, 0) >= 1

    def count(self, cls):
        """Number of plots reported for a class (the X / Y in the report lines)."""
        return sum(1 for idx in self.plot_order if self.reported(cls, idx))

    def not_assessed(self, cls):
        """Plot indices with no reference coverage for a class, in output order."""
        return [idx for idx in self.plot_order if self.values[cls].get(idx) is None]


@dataclass
class LandcoverOutcome:
    """What the main class needs after the check: statuses, result and map info."""

    statuses: dict = field(default_factory=dict)   # cls -> STATUS_*
    reasons: dict = field(default_factory=dict)    # cls -> short reason (not run)
    sources: dict = field(default_factory=dict)    # cls -> CSV `source` text
    coverage_sources: dict = field(default_factory=dict)  # cls -> `source` of not_assessed rows
    result: object = None                          # LandcoverResult or None
    n_plots: int = 0
    raster_path: str = None                        # Fetch mode: /vsicurl/ path or VRT
    tiles: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    # Per-plot identifiers for the CSV: {"feature_ids"|"node_ids"|"plot_ids": {idx: value}}
    plot_meta: dict = field(default_factory=dict)

    @classmethod
    def failed(cls, reason):
        """Both classes not run for one reason (guard, cancel, unreachable bucket)."""
        return cls(
            statuses={c: STATUS_NOT_RUN for c in CLASSES},
            reasons={c: reason for c in CLASSES},
        )

    def classes_ran(self):
        return tuple(c for c in CLASSES if self.statuses.get(c) == STATUS_RAN)


def project_source_label(layer_name, band, value):
    """CSV `source` text in Project mode: ``<layer name>, band <b>, value <v>``."""
    return "{}, band {}, value {}".format(layer_name, band, value)


def project_coverage_label(layer_name, band):
    """`source` of a Project-mode ``not_assessed`` row: the raster and band, no value.

    Coverage depends on the raster, not on the class value, so two classes reading the
    same layer and band give one ``not_assessed`` row (DEC-14).
    """
    return "{}, band {}".format(layer_name, band)


# --------------------------------------------------------------------------- #
# Computation (FR-5, D6–D8)
# --------------------------------------------------------------------------- #

def compute_landcover(histograms, class_values, plot_areas, plot_order=None):
    """Per-plot overlap for every class in ``class_values``.

    - ``histograms``: ``{cls: {idx: {value|"NODATA": count}}}``; classes may share the
      same dict when they use the same raster and band.
    - ``class_values``: ``{cls: int}``; only these classes are computed.
    - ``plot_areas``: ``{idx: m²}``; its keys are the plots to assess.
    - ``plot_order``: output order of the indices; defaults to sorted keys.

    ``total_pixels`` includes nodata. ``overlap_pct = class / total × 100``;
    ``overlap_area_m2 = pct / 100 × plot_area``. No threshold (D7). A plot with
    ``total_pixels == 0`` for a class is not assessed for it (``None``).
    """
    order = list(plot_order) if plot_order is not None else sorted(plot_areas)
    classes = tuple(c for c in CLASSES if c in class_values)
    values = {}
    class_pixels = {}
    for cls in classes:
        hist = histograms.get(cls) or {}
        target = int(class_values[cls])
        values[cls] = {}
        class_pixels[cls] = {}
        for idx in order:
            counts = hist.get(idx) or {}
            total = sum(counts.values())
            if total <= 0:
                values[cls][idx] = None
                class_pixels[cls][idx] = 0
                continue
            n = counts.get(target, 0)
            pct = n / total * 100.0
            values[cls][idx] = (pct, pct / 100.0 * plot_areas[idx])
            class_pixels[cls][idx] = n
    return LandcoverResult(
        classes=classes,
        plot_order=order,
        values=values,
        class_pixels=class_pixels,
        plot_areas=dict(plot_areas),
    )


# --------------------------------------------------------------------------- #
# Output builders (FR-10, FR-6)
# --------------------------------------------------------------------------- #

def geojson_properties(result):
    """FR-10 properties per plot: ``{idx: {field: value}}``.

    Only the classes in ``result.classes`` get fields. Area rounded to 1 decimal and
    percent to 2; ``0.0`` when the plot has no pixel of the class; ``None`` (JSON
    null) when the plot is not assessed for the class.
    """
    props = {}
    for idx in result.plot_order:
        p = {}
        for cls in result.classes:
            area_field, pct_field = FIELD_NAMES[cls]
            v = result.values[cls].get(idx)
            if v is None:
                p[area_field] = None
                p[pct_field] = None
            else:
                pct, area = v
                p[area_field] = round(area, 1)
                p[pct_field] = round(pct, 2)
        props[idx] = p
    return props


def _fmt(value, decimals):
    return "{:.{}f}".format(value, decimals)


def csv_rows(result, feature_ids, node_ids, plot_ids, sources, coverage_sources=None):
    """FR-6 rows in long format, deterministic order.

    One row per plot per reported class, then one ``not_assessed`` row per plot and
    distinct coverage source with no coverage. Order: output order, then water,
    built_up, not_assessed. ``feature_ids``/``node_ids``/``plot_ids`` map plot index →
    value; ``sources`` maps class → `source` text; ``coverage_sources`` maps class →
    the `source` text of its ``not_assessed`` rows (default: ``sources``). Numbers are
    formatted strings so the file is byte-stable.
    """
    coverage_sources = coverage_sources or {}
    rows = []
    for idx in result.plot_order:
        base = {
            "feature_id": feature_ids.get(idx, ""),
            "NodeID": node_ids.get(idx) or "",
            "PlotID": plot_ids.get(idx) or "",
            "plot_area_m2": _fmt(result.plot_areas[idx], 1),
        }
        for cls in result.classes:
            if not result.reported(cls, idx):
                continue
            pct, area = result.values[cls][idx]
            row = dict(base)
            row.update({
                "class": cls,
                "overlap_area_m2": _fmt(area, 1),
                "overlap_pct": _fmt(pct, 2),
                "source": sources.get(cls, ""),
            })
            rows.append(row)
        seen_sources = []
        for cls in result.classes:
            if result.values[cls].get(idx) is not None:
                continue
            source = coverage_sources.get(cls, sources.get(cls, ""))
            if source in seen_sources:
                continue
            seen_sources.append(source)
            row = dict(base)
            row.update({
                "class": NOT_ASSESSED,
                "overlap_area_m2": "",
                "overlap_pct": "",
                "source": source,
            })
            rows.append(row)
    # Restore the documented column order for readers that iterate dict keys.
    return [{k: row[k] for k in CSV_FIELDNAMES} for row in rows]
