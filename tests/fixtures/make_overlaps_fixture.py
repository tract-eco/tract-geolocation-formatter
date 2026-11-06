"""
Build tests/fixtures/overlaps.gpkg for the GH-12 overlap check (manual QGIS runs).

Run with QGIS's Python (needs qgis.core):

    PROJ_LIB=/Applications/QGIS-3.38.app/Contents/Resources/proj \\
    /Applications/QGIS-3.38.app/Contents/MacOS/bin/python3 tests/fixtures/make_overlaps_fixture.py

Two layers, EPSG:4326, fields ``case``, ``NodeID``, ``PlotID``, ``expect``:

- ``overlaps``   — 2D MultiPolygons: category A, B and C cases.
- ``overlaps_z`` — MultiPolygonZ: a Z feature with overlapping parts (dissolved)
  and a cross-NodeID Z pair (clip skipped).

With ``--many [OUT]`` it instead writes a single ``many`` layer of 10 000 plots
(default ``tests/fixtures/overlaps_many.gpkg``, not committed) for timing the
cross-feature stage:

    ... make_overlaps_fixture.py --many /tmp/overlaps_many.gpkg

Each case sits in its own 0.01 degree cell so cases never interact. One unit
is 0.001 degree (~111 m east-west at the equator-ish base latitude used here),
so plots are ~1 ha, well above MIN_PLOT_AREA_HA.
"""

import os
import sys

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsVectorFileWriter,
    QgsWkbTypes,
)


def _string_type():
    # Same probe as STRING_FIELD_TYPE in the main module: QMetaType on QGIS >= 3.38,
    # QVariant before (QGIS 4 drops the QVariant overload).
    try:
        from qgis.PyQt.QtCore import QMetaType
        QgsField("_probe", QMetaType.Type.QString)
        return QMetaType.Type.QString
    except (ImportError, AttributeError, TypeError):
        from qgis.PyQt.QtCore import QVariant
        return QVariant.String

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlaps.gpkg")
UNIT = 0.001
BASE_X, BASE_Y = 10.0, 5.0


def _cell(n):
    """Origin of case cell n (10 cells per row)."""
    return BASE_X + (n % 10) * 0.01, BASE_Y + (n // 10) * 0.01


def _ring(cell, pts, z=None):
    ox, oy = _cell(cell)
    pts = list(pts) + [pts[0]]
    if z is None:
        return "(" + ", ".join("%.6f %.6f" % (ox + x * UNIT, oy + y * UNIT) for x, y in pts) + ")"
    return "(" + ", ".join("%.6f %.6f %s" % (ox + x * UNIT, oy + y * UNIT, z) for x, y in pts) + ")"


def _box(cell, x0, y0, x1, y1, z=None):
    return "(" + _ring(cell, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z) + ")"


def _multi(*polys, z=False):
    return ("MULTIPOLYGON Z (" if z else "MULTIPOLYGON (") + ", ".join(polys) + ")"


# (case, NodeID, PlotID, wkt, expect)
FEATURES_2D = [
    # --- Category A -------------------------------------------------------
    ("A_boxes", "NA1", "PA1", _multi(_box(0, 0, 0, 2, 2), _box(0, 1, 1, 3, 3)),
     "dissolved; area = 7 units (not 6); overlap_parts row (25 %)"),
    ("A_contained_part", "NA2", "PA2", _multi(_box(1, 0, 0, 4, 4), _box(1, 1, 1, 2, 2)),
     "dissolved to the outer box; overlap_parts row (100 %)"),
    ("A_bowtie_box", "NA3", "PA3",
     _multi("(" + _ring(2, [(0, 0), (2, 2), (2, 0), (0, 2)]) + ")", _box(2, 1.5, 0, 3, 2)),
     "bowtie part repaired, overlap with box detected and dissolved"),
    ("A_5pct_and_half_pct", "NA4", "PA4",
     _multi(_box(3, 0, 0, 2, 2), _box(3, 1.9, 0, 3.9, 2),
            _box(3, 5, 0, 7, 2), _box(3, 6.99, 0, 8.99, 2)),
     "both dissolved; overlap_parts row only for parts 1/2 (5 %); 3/4 (0.5 %) below threshold"),
    ("A_edge_touch", "NA5", "PA5", _multi(_box(4, 0, 0, 1, 1), _box(4, 1, 0, 2, 1)),
     "no overlap; unchanged by the check"),
    # --- Category B (same NodeID) -----------------------------------------
    ("B_partial_big", "NB1", "PB1a", _multi(_box(10, 0, 0, 2, 2)), "keeps the overlap"),
    ("B_partial_small", "NB1", "PB1b", _multi(_box(10, 1.9, 0, 3.4, 2)),
     "B partial (~6.7 % of smaller); clipped when same-NodeID clipping is on"),
    ("B_chain_A", "NB2", "PB2a", _multi(_box(11, 0, 0, 3, 3)), "largest of chain; unchanged"),
    ("B_chain_B", "NB2", "PB2b", _multi(_box(11, 2.5, 0, 5, 2.5)), "clipped by A"),
    ("B_chain_C", "NB2", "PB2c", _multi(_box(11, 2, 2, 4, 4)), "clipped by A and B"),
    ("B_container", "NB3", "PB3a", _multi(_box(12, 0, 0, 3, 3)), "container"),
    ("B_contained", "NB3", "PB3b", _multi(_box(12, 1, 1, 2, 2)), "default action: delete contained"),
    ("B_identical_1", "NB4", "PB4a", _multi(_box(13, 0, 0, 2, 2)), "identical; earlier one survives"),
    ("B_identical_2", "NB4", "PB4b", _multi(_box(13, 0, 0, 2, 2)), "identical; deleted with delete contained"),
    # --- Category C (different NodeIDs) -----------------------------------
    ("C_5pct_a", "NC1", "PC1", _multi(_box(20, 0, 0, 2, 2)), "C partial 5 %"),
    ("C_5pct_b", "NC2", "PC2", _multi(_box(20, 1.9, 0, 3.9, 2)), "C partial 5 %"),
    ("C_halfpct_a", "NC3", "PC3", _multi(_box(21, 0, 0, 2, 2)), "C partial 0.5 %: below threshold"),
    ("C_halfpct_b", "NC4", "PC4", _multi(_box(21, 1.99, 0, 3.99, 2)), "C partial 0.5 %: below threshold"),
    ("C_lone_container", "NC5", "PC5", _multi(_box(22, 0, 0, 3, 3)), "contains the only plot of NC6"),
    ("C_lone_contained", "NC6", "PC6", _multi(_box(22, 1, 1, 2, 2)),
     "only plot of NC6; deleting it shows the last-plot warning"),
    ("C_edge_a", "NC7", "PC7", _multi(_box(23, 0, 0, 1, 1)), "shares an edge only: no finding"),
    ("C_edge_b", "NC8", "PC8", _multi(_box(23, 1, 0, 2, 1)), "shares an edge only: no finding"),
    ("C_tiny_big", "NC9", "PC9", _multi(_box(24, 0, 0, 2, 2)), "large partner of the tiny plot"),
    ("C_tiny_small", "NC10", "PC10", _multi(_box(24, 1.96, 0, 2.01, 0.05)),
     "~0.003 ha, 80 % inside NC9; 'Remove from smaller' leaves ~6 m2 -> NEEDS_FIX Area below minimum"),
]

FEATURES_Z = [
    ("A_z", "NZ1", "PZ1", _multi(_box(30, 0, 0, 2, 2, 5), _box(30, 1, 1, 3, 3, 5), z=True),
     "Z MultiPolygon: dissolved like any other"),
    ("C_z_a", "NZ2", "PZ2", _multi(_box(31, 0, 0, 2, 2, 7), z=True), "C partial with Z (10 %): clip skipped"),
    ("C_z_b", "NZ3", "PZ3", _multi(_box(31, 1.8, 0, 3.8, 2, 7), z=True), "C partial with Z: clip skipped"),
]


def _many_rows(n_side=100):
    """n_side x n_side grid of ~1 ha plots, 10 plots per NodeID (one row segment).

    Mix of findings, roughly what a large real upload looks like:
    - every 3rd plot reaches 5 % into its right-hand neighbour (same NodeID inside a
      segment of 10, different NodeID at segment edges);
    - every 50th plot has a second, overlapping part (category A);
    - every 97th plot contains a small plot of its own NodeID (containment).
    Grid pitch is 1.2 units, so plots that are not meant to overlap never touch.
    """
    rows = []
    pitch = 1.2
    for k in range(n_side * n_side):
        r, c = divmod(k, n_side)
        x0, y0 = c * pitch, r * pitch
        x1 = x0 + (1.0 + 0.2 + 0.05 if k % 3 == 0 and c < n_side - 1 else 1.0)
        node = "N%04d" % (r * (n_side // 10) + c // 10)
        parts = [_box(0, x0, y0, x1, y0 + 1)]
        if k % 50 == 0:
            parts.append(_box(0, x0 + 0.5, y0 + 0.5, x0 + 1.0, y0 + 1.0))
        rows.append(("many_%05d" % k, node, "P%05d" % k, _multi(*parts), ""))
        if k % 97 == 0:
            rows.append(("many_%05d_in" % k, node, "P%05di" % k,
                         _multi(_box(0, x0 + 0.3, y0 + 0.3, x0 + 0.6, y0 + 0.6)), ""))
    return rows


def _write_layer(name, wkb_type, rows, append, out=None):
    fields = QgsFields()
    for fname in ("case", "NodeID", "PlotID", "expect"):
        fields.append(QgsField(fname, _string_type()))
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = name
    if append:
        opts.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    writer = QgsVectorFileWriter.create(
        out or OUT, fields, wkb_type, QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateTransformContext(), opts,
    )
    if writer.hasError() != QgsVectorFileWriter.WriterError.NoError:
        raise RuntimeError(writer.errorMessage())
    for case, node_id, plot_id, wkt, expect in rows:
        geom = QgsGeometry.fromWkt(wkt)
        if geom.isNull():
            raise ValueError("bad WKT for %s" % case)
        feat = QgsFeature(fields)
        feat.setAttributes([case, node_id, plot_id, expect])
        feat.setGeometry(geom)
        writer.addFeature(feat)
    del writer


def main():
    app = QgsApplication([], False)
    app.initQgis()
    if "--many" in sys.argv:
        rest = sys.argv[sys.argv.index("--many") + 1:]
        out = rest[0] if rest else os.path.join(os.path.dirname(OUT), "overlaps_many.gpkg")
        if os.path.exists(out):
            os.remove(out)
        rows = _many_rows()
        _write_layer("many", QgsWkbTypes.Type.MultiPolygon, rows, append=False, out=out)
        print("wrote", out, len(rows), "features")
        app.exitQgis()
        return 0
    if os.path.exists(OUT):
        os.remove(OUT)
    _write_layer("overlaps", QgsWkbTypes.Type.MultiPolygon, FEATURES_2D, append=False)
    _write_layer("overlaps_z", QgsWkbTypes.Type.MultiPolygonZ, FEATURES_Z, append=True)
    print("wrote", OUT, len(FEATURES_2D), "+", len(FEATURES_Z), "features")
    app.exitQgis()
    return 0


if __name__ == "__main__":
    sys.exit(main())
