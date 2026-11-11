"""
End-to-end runs of the export with the land cover check (SPEC-landcover-overlap, Task 4).

Runs the real ``_run_transformation_from_dialog`` headless (QGIS Python only; skipped
elsewhere) with a stub QGIS interface, on generated rasters loaded as project layers
(Project mode). Offline: the one Fetch-mode test points GDAL at a closed local port, so
nothing leaves the machine.
"""

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "fixtures"))

try:
    from osgeo import gdal  # noqa: F401
    from qgis.core import QgsProject  # noqa: F401

    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

FIELDS = ["WaterOverlap_m2", "WaterOverlap_pct", "BuiltUpOverlap_m2", "BuiltUpOverlap_pct"]


def setUpModule():
    if not QGIS_AVAILABLE:
        return
    from _qgis_app import qgis_app
    from qgis.PyQt.QtCore import QSettings

    qgis_app()
    QSettings().setValue("locale/userLocale", "en_US")  # temp INI (see _qgis_app)


class _Iface:
    def __init__(self):
        from qgis.gui import QgsMessageBar
        from qgis.PyQt.QtWidgets import QWidget

        self.bar = QgsMessageBar()
        self.win = QWidget()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return self.win


@unittest.skipUnless(QGIS_AVAILABLE, "Requires QGIS Python environment")
class LandcoverPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from make_landcover_fixture import make_fixture
        from qgis.core import QgsProject, QgsRasterLayer

        import tract_geolocation_formatter.TRACT_Geolocation_Formatter as M

        cls.M = M
        cls.tmp = tempfile.mkdtemp(prefix="tract_landcover_pipeline_")
        cls.fx = make_fixture(os.path.join(cls.tmp, "fixture"))
        cls.main = QgsRasterLayer(cls.fx["main"], "classes", "gdal")
        cls.outside = QgsRasterLayer(cls.fx["outside"], "elsewhere", "gdal")
        QgsProject.instance().addMapLayers([cls.main, cls.outside], False)
        cls._run_no = 0

    @classmethod
    def tearDownClass(cls):
        from qgis.core import QgsProject

        QgsProject.instance().removeAllMapLayers()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ helpers

    def _input_layer(self, plots=None, extra_field=False, fc=None):
        """Memory layer of the fixture plots with NodeID/PlotID (and optionally a clash)."""
        from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer

        uri = "MultiPolygon?crs=EPSG:4326&field=NodeID:string&field=PlotID:string"
        if extra_field:
            uri += "&field=WaterOverlap_pct:double"
        layer = QgsVectorLayer(uri, "plots_in", "memory")
        feats = []
        for i, feature in enumerate((fc or self.fx["plots"])["features"]):
            if plots is not None and i not in plots:
                continue
            g = feature["geometry"]
            if g["type"] not in ("Polygon", "MultiPolygon"):
                continue
            f = QgsFeature(layer.fields())
            attrs = ["N{}".format(i % 3), "P{}".format(i)]
            if extra_field:
                attrs.append(12.5)
            f.setAttributes(attrs)
            f.setGeometry(QgsGeometry.fromWkt(_wkt(g)))
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        return layer

    def _run(self, landcover=None, plots=None, extra_field=False, split=0, overlap=False,
             subdir=None, before_run=None, fc=None):
        """Run the export. ``landcover``: None (off) or dict(mode, water, built_up)."""
        from qgis.core import QgsProject

        M = self.M
        LandcoverPipelineTests._run_no += 1
        out_dir = os.path.join(self.tmp, subdir or "run{}".format(self._run_no))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "plots.geojson")

        layer = self._input_layer(plots, extra_field, fc)
        QgsProject.instance().addMapLayer(layer)
        p = M.TractGeolocationFormatter(_Iface())
        report = {}
        p._show_report_dialog = lambda html: report.setdefault("html", html)
        p._prompt_hole_fix_policy = lambda: "flag"
        p._log = lambda m: report.setdefault("text", m) if "SUMMARY" in str(m) else None
        p.dlg = M.TractGeolocationFormatterDialog()
        p._connect_landcover_signals()
        p._populate_dialog()
        d = p.dlg
        d.layerComboBox.setCurrentIndex([lyr.name() for lyr in p._polygon_layers].index("plots_in"))
        d.nodeExistingRadio.setChecked(True)
        d.nodeFieldCombo.setCurrentText("NodeID")
        d.plotExistingRadio.setChecked(True)
        d.plotFieldCombo.setCurrentText("PlotID")
        d.outputPathLineEdit.setText(out_path)
        d.overlapCheckBox.setChecked(overlap)
        d.splitCheckBox.setChecked(bool(split))
        if split:
            d.splitCountSpin.setValue(split)
        # ``landcover``: None = nothing ticked. Otherwise per class (DEC-21):
        # None = unticked, "worldcover", or (layer|None, band, value) = project layer.
        # {"mode": "fetch"} ticks both classes on WorldCover; "mode": "project" with
        # tuples is the old shorthand and still reads the same.
        landcover = landcover or {}
        default = "worldcover" if landcover.get("mode") == "fetch" else None
        for cls, prefix in (("water", "landcoverWater"), ("built_up", "landcoverBuiltUp")):
            spec = landcover.get(cls, default)
            getattr(d, prefix + "CheckBox").setChecked(spec is not None)
            source = getattr(d, prefix + "SourceCombo")
            if spec is None:
                continue
            if spec == "worldcover":
                source.setCurrentIndex(source.findData("worldcover"))
                continue
            source.setCurrentIndex(source.findData("project"))
            getattr(d, prefix + "LayerCombo").setLayer(spec[0])
            if spec[0] is not None:
                getattr(d, prefix + "BandCombo").setCurrentIndex(spec[1] - 1)
            getattr(d, prefix + "ValueCombo").setEditText(str(spec[2]))
        boxes = []
        stub = staticmethod(lambda *a, **k: boxes.append(a[2] if len(a) > 2 else "") or 0)
        with mock.patch.object(M.QMessageBox, "warning", stub), \
                mock.patch.object(M.QMessageBox, "critical", stub):
            if before_run:
                before_run(p)
            p._run_transformation_from_dialog()
        QgsProject.instance().removeMapLayer(layer.id())
        from qgis.PyQt import sip

        sip.delete(d)
        base = os.path.splitext(out_path)[0]
        result = {
            "dir": out_dir,
            "out": out_path,
            "text": report.get("text", ""),
            "boxes": boxes,
            "csv": base + "_landcover_overlaps.csv",
        }
        if os.path.exists(out_path):
            with open(out_path, "rb") as fh:
                result["bytes"] = fh.read()
            result["fc"] = json.loads(result["bytes"].decode("utf-8"))
        return result

    def _csv_rows(self, path):
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def _lines(self, res):
        return [ln.strip(" •-") for ln in res["text"].splitlines() if "overlap:" in ln]

    def _both(self, water_value=80, built_value=50, layer=None):
        layer = layer or self.main
        return {"mode": "project", "water": (layer, 1, water_value), "built_up": (layer, 1, built_value)}

    # ------------------------------------------------------------------ tests

    def test_ac1_off_adds_nothing(self):
        """AC-1 (in-suite part): check off → no fields, no CSV, no report lines."""
        res = self._run(None)
        for f in res["fc"]["features"]:
            self.assertFalse(set(FIELDS) & set(f["properties"]))
        self.assertFalse(os.path.exists(res["csv"]))
        self.assertEqual(self._lines(res), [])
        self.assertNotIn("Land cover", res["text"])

    def test_ac30_fields_values_and_order(self):
        off = self._run(None, subdir="ac30_off")
        on = self._run(self._both(), subdir="ac30_on")
        rows = self._csv_rows(on["csv"])
        by_feature = {}
        for k, f in enumerate(on["fc"]["features"]):
            props = f["properties"]
            self.assertEqual(list(props)[-4:], FIELDS)
            keys = list(props)
            self.assertLess(keys.index("TRACTIssue"), keys.index("WaterOverlap_m2"))
            off_props = off["fc"]["features"][k]["properties"]
            self.assertEqual(props["TRACTStatus"], off_props["TRACTStatus"])
            self.assertEqual(props["TRACTIssue"], off_props["TRACTIssue"])
            by_feature[props["PlotID"]] = props
        lake = by_feature["P0"]
        self.assertEqual(lake["WaterOverlap_pct"], 100.0)
        self.assertEqual(lake["BuiltUpOverlap_pct"], 0.0)
        self.assertEqual(lake["BuiltUpOverlap_m2"], 0.0)
        water_row = [r for r in rows if r["PlotID"] == "P0" and r["class"] == "water"][0]
        self.assertEqual(float(water_row["overlap_pct"]), lake["WaterOverlap_pct"])
        self.assertEqual(float(water_row["overlap_area_m2"]), lake["WaterOverlap_m2"])
        self.assertEqual(by_feature["P2"]["WaterOverlap_pct"], 50.0)
        self.assertEqual(by_feature["P1"]["BuiltUpOverlap_pct"], 100.0)
        outside = by_feature["P3"]  # AC-31 end to end
        self.assertEqual([outside[k] for k in FIELDS], [None] * 4)
        self.assertEqual(
            self._lines(on),
            ["Water overlap: 3 of 5 plots", "Built-up overlap: 2 of 5 plots"],
        )
        self.assertIn("Land cover overlaps", on["text"])

    def test_csv_rows_and_ids(self):
        res = self._run(self._both())
        rows = self._csv_rows(res["csv"])
        self.assertEqual(
            [(r["PlotID"], r["class"]) for r in rows],
            [("P0", "water"), ("P1", "built_up"), ("P2", "water"), ("P3", "no_coverage"),
             ("P4", "water"), ("P4", "built_up")],  # one no_coverage row (shared raster)
        )
        self.assertTrue(all(r["feature_id"] != "" for r in rows))
        self.assertEqual(rows[0]["source"], "classes, band 1, value 80")
        self.assertEqual(rows[1]["source"], "classes, band 1, value 50")
        self.assertEqual(rows[3]["source"], "classes, band 1")  # no_coverage: raster + band

    def test_ac25_no_overlaps_header_only(self):
        res = self._run(self._both(water_value=99, built_value=98), plots=[0, 1, 2, 4])
        with open(res["csv"], encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), ",".join(
                ["feature_id", "NodeID", "PlotID", "class", "overlap_area_m2", "overlap_pct",
                 "plot_area_m2", "source"]))
        self.assertEqual(self._lines(res),
                         ["Water overlap: 0 of 4 plots", "Built-up overlap: 0 of 4 plots"])
        self.assertEqual(res["fc"]["features"][0]["properties"]["WaterOverlap_pct"], 0.0)

    def test_ac26_ac32_built_up_not_checked(self):
        res = self._run({"mode": "project", "water": (self.main, 1, 80), "built_up": None})
        self.assertEqual(self._lines(res)[1], "Built-up overlap: not checked")
        self.assertNotIn("built_up", {r["class"] for r in self._csv_rows(res["csv"])})
        for f in res["fc"]["features"]:
            self.assertEqual(list(f["properties"])[-2:], ["WaterOverlap_m2", "WaterOverlap_pct"])
            self.assertNotIn("BuiltUpOverlap_pct", f["properties"])

    def test_ac32_nothing_ran_geojson_unchanged(self):
        off = self._run(None, subdir="ac32_off")
        res = self._run({"mode": "project", "water": (self.main, 1, ""), "built_up": None},
                        subdir="ac32_on")
        self.assertEqual(res["bytes"], off["bytes"])
        self.assertFalse(os.path.exists(res["csv"]))
        self.assertEqual(self._lines(res)[0], "Water overlap: not run (No class value set for classes)")

    def test_ac12_ac13_one_class_fails_other_runs(self):
        res = self._run({"mode": "project", "water": (self.outside, 1, 80),
                         "built_up": (self.main, 1, 50)})
        self.assertEqual(self._lines(res), [
            "Water overlap: not run (The selected layer does not cover your plots)",
            "Built-up overlap: 2 of 5 plots",
        ])
        self.assertEqual(list(res["fc"]["features"][0]["properties"])[-2:],
                         ["BuiltUpOverlap_m2", "BuiltUpOverlap_pct"])

    def test_ac3_internal_error_leaves_outputs(self):
        off = self._run(None, subdir="ac3_off")

        def boom(*a, **k):
            raise RuntimeError("boom")

        with mock.patch("tract_geolocation_formatter.landcover_source.build_plots_layer", boom):
            res = self._run(self._both(), subdir="ac3_on")
        self.assertEqual(res["bytes"], off["bytes"])
        self.assertFalse(os.path.exists(res["csv"]))
        self.assertEqual(self._lines(res), ["Water overlap: not run (internal error)",
                                            "Built-up overlap: not run (internal error)"])

    def test_ac33_rewrite_failure_leaves_geojson(self):
        off = self._run(None, subdir="ac33_off")
        with mock.patch.object(self.M.os, "replace", side_effect=OSError("disk full")):
            res = self._run(self._both(), subdir="ac33_on")
        self.assertEqual(res["bytes"], off["bytes"])
        self.assertEqual(os.listdir(res["dir"]), os.listdir(off["dir"]))
        self.assertFalse(any(n.endswith(".tmp") for n in os.listdir(res["dir"])))
        self.assertIn("not run (internal error)", self._lines(res)[0])

    def test_ac34_clashing_input_field(self):
        on = self._run(self._both(), extra_field=True)
        props = on["fc"]["features"][0]["properties"]
        self.assertEqual(props["WaterOverlap_pct_orig"], 12.5)
        self.assertEqual(props["WaterOverlap_pct"], 100.0)
        off = self._run(None, extra_field=True)
        props = off["fc"]["features"][0]["properties"]
        self.assertEqual(props["WaterOverlap_pct"], 12.5)
        self.assertNotIn("WaterOverlap_pct_orig", props)

    def test_ac28_deterministic(self):
        a = self._run(self._both(), subdir="ac28_a")
        b = self._run(self._both(), subdir="ac28_b")
        self.assertEqual(a["bytes"], b["bytes"])
        with open(a["csv"], "rb") as fa, open(b["csv"], "rb") as fb:
            self.assertEqual(fa.read(), fb.read())

    def test_ac27_split_and_deletion(self):
        """AC-27: GH-12 deletion before the check; split files carry the fields."""
        M = self.M

        def fake_overlaps(self_, output_path, written_fids, *a, **k):
            with open(output_path, encoding="utf-8") as fh:
                fc = json.load(fh)
            gone = written_fids[1]
            fc["features"] = [f for i, f in enumerate(fc["features"]) if i != 1]
            with open(output_path, "w", encoding="utf-8") as fh:
                json.dump(fc, fh)
            return {
                "changed": True, "needs_fix_count": 0, "deleted_fids": [gone],
                "final_node_ids": [f["properties"]["NodeID"] for f in fc["features"]],
            }

        with mock.patch.object(M.TractGeolocationFormatter, "_process_feature_overlaps", fake_overlaps), \
                mock.patch.object(M.TractGeolocationFormatter, "_overlap_records",
                                  lambda *a, **k: []):
            res = self._run(self._both(), overlap=True, split=2)
        split_files = sorted(n for n in os.listdir(res["dir"]) if n.endswith(".geojson"))
        self.assertEqual(len(split_files), 2)
        plot_ids = []
        for name in split_files:
            with open(os.path.join(res["dir"], name), encoding="utf-8") as fh:
                for f in json.load(fh)["features"]:
                    self.assertTrue(set(FIELDS) <= set(f["properties"]))
                    plot_ids.append(f["properties"]["PlotID"])
        self.assertEqual(sorted(plot_ids), ["P0", "P2", "P3", "P4"])
        self.assertNotIn("P1", {r["PlotID"] for r in self._csv_rows(res["csv"])})
        self.assertEqual(self._lines(res), ["Water overlap: 3 of 4 plots",
                                            "Built-up overlap: 1 of 4 plots"])

    def test_ac2_fetch_mode_without_network(self):
        """AC-2: bucket unreachable → main outputs as with the check off, "not run"."""
        from osgeo import gdal

        off = self._run(None, subdir="ac2_off")
        saved = gdal.GetConfigOption("GDAL_HTTP_PROXY")
        gdal.SetConfigOption("GDAL_HTTP_PROXY", "127.0.0.1:9")  # closed local port
        try:
            gdal.VSICurlClearCache()
            res = self._run({"mode": "fetch"}, subdir="ac2_on")
        finally:
            gdal.SetConfigOption("GDAL_HTTP_PROXY", saved)
            gdal.VSICurlClearCache()
        self.assertEqual(res["bytes"], off["bytes"])
        self.assertFalse(os.path.exists(res["csv"]))
        self.assertEqual(self._lines(res), ["Water overlap: not run (cannot reach WorldCover)",
                                            "Built-up overlap: not run (cannot reach WorldCover)"])

    def _fetch_with_local_raster(self, **kwargs):
        """Both classes on WorldCover, the fixture raster standing in for it (offline)."""
        return self._fetch_with_local_raster_spec({"mode": "fetch"}, **kwargs)

    def _fetch_with_local_raster_spec(self, landcover, **kwargs):
        fake = lambda tiles, *a, **k: (self.fx["main"], [tiles[0]], tiles[1:])  # noqa: E731
        with mock.patch("tract_geolocation_formatter.landcover_source.resolve_worldcover", fake):
            return self._run(landcover, **kwargs)

    def _group(self):
        from qgis.core import QgsProject

        from tract_geolocation_formatter.landcover import GROUP_NAME

        return QgsProject.instance().layerTreeRoot().findGroup(GROUP_NAME)

    def _clear_run_layers(self):
        from qgis.core import QgsProject

        keep = {self.main.id(), self.outside.id()}
        project = QgsProject.instance()
        project.removeMapLayers([lid for lid in project.mapLayers() if lid not in keep])
        root = project.layerTreeRoot()
        for child in list(root.children()):
            if child.name() != "classes":
                root.removeChildNode(child)

    def test_ac18_ac22_fetch_mode_layer_and_results(self):
        """AC-18: styled layer in its group below the output; AC-22: plots in a missing
        tile are not assessed. The tile reads are replaced by the local fixture raster."""
        from qgis.core import QgsProject

        self._clear_run_layers()
        try:
            res = self._fetch_with_local_raster()
            self.assertEqual(self._lines(res), ["Water overlap: 3 of 5 plots",
                                                "Built-up overlap: 2 of 5 plots"])
            rows = self._csv_rows(res["csv"])
            self.assertEqual(rows[0]["source"], "ESA WorldCover 2021 v200")
            self.assertIn(("P3", "no_coverage"), [(r["PlotID"], r["class"]) for r in rows])
            group = self._group()
            self.assertIsNotNone(group)
            layers = group.findLayers()
            self.assertEqual(len(layers), 1)
            self.assertEqual(layers[0].layer().source(), self.fx["main"])
            names = [c.name() for c in QgsProject.instance().layerTreeRoot().children()]
            self.assertLess(names.index("plots.geojson"), names.index(group.name()))
            self.assertEqual(os.listdir(res["dir"]),
                             [n for n in os.listdir(res["dir"]) if not n.endswith(".vrt")])
        finally:
            self._clear_run_layers()

    def test_ac20_second_fetch_run_replaces_group(self):
        from qgis.core import QgsProject

        self._clear_run_layers()
        try:
            self._fetch_with_local_raster(subdir="ac20_a")
            self._fetch_with_local_raster(subdir="ac20_b")
            root = QgsProject.instance().layerTreeRoot()
            groups = [c for c in root.children() if c.name() == self._group().name()]
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(self._group().findLayers()), 1)
        finally:
            self._clear_run_layers()

    def test_ac16_project_mode_leaves_user_layers_alone(self):
        from qgis.core import QgsProject

        self._clear_run_layers()
        root = QgsProject.instance().layerTreeRoot()
        root.addLayer(self.main)
        node = root.findLayer(self.main.id())
        node.setItemVisibilityChecked(False)
        before = (type(self.main.renderer()).__name__, self.main.renderer().opacity(),
                  node.itemVisibilityChecked(), self.main.source())
        try:
            self._run(self._both())
            node = root.findLayer(self.main.id())
            after = (type(self.main.renderer()).__name__, self.main.renderer().opacity(),
                     node.itemVisibilityChecked(), self.main.source())
            self.assertEqual(before, after)
            self.assertIsNone(self._group())
            self.assertEqual([c.name() for c in root.children()].count("classes"), 1)
        finally:
            # Leave the node in the tree: removing a layer's node also removes the layer
            # from the project (QgsLayerTreeRegistryBridge), and later tests use it.
            root.findLayer(self.main.id()).setItemVisibilityChecked(True)
            self._clear_run_layers()

    def test_ac36_mixed_sources(self):
        """AC-36: water from a project layer, built-up from WorldCover (stubbed locally)."""
        self._clear_run_layers()
        try:
            res = self._fetch_with_local_raster_spec(
                {"water": (self.main, 1, 80), "built_up": "worldcover"})
            rows = self._csv_rows(res["csv"])
            sources = {(r["class"], r["source"]) for r in rows}
            self.assertIn(("water", "classes, band 1, value 80"), sources)
            self.assertIn(("built_up", "ESA WorldCover 2021 v200"), sources)
            self.assertEqual(list(res["fc"]["features"][0]["properties"])[-4:], FIELDS)
            self.assertEqual(self._lines(res), ["Water overlap: 3 of 5 plots",
                                                "Built-up overlap: 2 of 5 plots"])
            layer = self._group().findLayers()[0].layer()
            self.assertEqual(layer.name(), "WorldCover 2021: water & built-up")
        finally:
            self._clear_run_layers()

    def test_ac37_only_water_on_worldcover(self):
        self._clear_run_layers()
        try:
            res = self._fetch_with_local_raster_spec({"water": "worldcover"})
            self.assertEqual(self._lines(res), ["Water overlap: 3 of 5 plots",
                                                "Built-up overlap: not checked"])
            for f in res["fc"]["features"]:
                self.assertEqual(list(f["properties"])[-2:], ["WaterOverlap_m2", "WaterOverlap_pct"])
                self.assertNotIn("BuiltUpOverlap_pct", f["properties"])
            self.assertIsNotNone(self._group())
        finally:
            self._clear_run_layers()

    def test_ac38_worldcover_unreachable_project_class_still_runs(self):
        from osgeo import gdal

        self._clear_run_layers()
        saved = gdal.GetConfigOption("GDAL_HTTP_PROXY")
        gdal.SetConfigOption("GDAL_HTTP_PROXY", "127.0.0.1:9")  # closed local port
        try:
            gdal.VSICurlClearCache()
            res = self._run({"water": "worldcover", "built_up": (self.main, 1, 50)})
        finally:
            gdal.SetConfigOption("GDAL_HTTP_PROXY", saved)
            gdal.VSICurlClearCache()
            self._clear_run_layers()
        self.assertEqual(self._lines(res), ["Water overlap: not run (cannot reach WorldCover)",
                                            "Built-up overlap: 2 of 5 plots"])
        for f in res["fc"]["features"]:
            self.assertEqual(list(f["properties"])[-2:], ["BuiltUpOverlap_m2", "BuiltUpOverlap_pct"])
        self.assertEqual({r["class"] for r in self._csv_rows(res["csv"])} - {"no_coverage"}, {"built_up"})
        self.assertIsNone(self._group())

    def test_ac39_ticked_project_class_without_layer(self):
        res = self._run({"water": (None, 1, 80), "built_up": (self.main, 1, 50)})
        self.assertEqual(self._lines(res)[0], "Water overlap: not run (no layer selected)")

    def test_ac16_project_only_makes_no_network_request(self):
        calls = []
        with mock.patch("tract_geolocation_formatter.landcover_source.resolve_worldcover",
                        lambda *a, **k: calls.append(a)), \
                mock.patch("tract_geolocation_formatter.landcover_source.gdal_http_scope",
                           side_effect=AssertionError("no HTTP scope expected")):
            res = self._run(self._both())
        self.assertEqual(calls, [])
        self.assertEqual(self._lines(res), ["Water overlap: 3 of 5 plots",
                                            "Built-up overlap: 2 of 5 plots"])

    def test_ac21_many_tiles_cancel(self):
        """AC-21: more than 12 tiles → confirmation; No → "not run (cancelled)", no reads."""
        M = self.M
        asked = []

        def no(*a, **k):
            asked.append(a[2])
            return M.QMessageBox.StandardButton.No

        reads = []
        with mock.patch.object(M.QMessageBox, "question", staticmethod(no)), \
                mock.patch("tract_geolocation_formatter.landcover_source.resolve_worldcover",
                           lambda *a, **k: reads.append(a)), \
                mock.patch("tract_geolocation_formatter.landcover.tiles_for_bboxes",
                           lambda boxes: ["N{:02d}E000".format(3 * i) for i in range(13)]):
            res = self._run({"mode": "fetch"})
        self.assertEqual(len(asked), 1)
        self.assertIn("13 WorldCover tiles", asked[0])
        self.assertEqual(reads, [])
        self.assertEqual(self._lines(res), ["Water overlap: not run (cancelled)",
                                            "Built-up overlap: not run (cancelled)"])


@unittest.skipUnless(QGIS_AVAILABLE and os.environ.get("TRACT_NETWORK_TESTS") == "1",
                     "network test: set TRACT_NETWORK_TESTS=1")
class NetworkFetchPipelineTests(LandcoverPipelineTests):
    """Real Fetch-mode run (AC-18/AC-19): the fixture plots lie in tiles N48E009 and
    N48E018, so the run reads two real WorldCover tiles through a VRT in the temp folder."""

    def test_real_fetch_run(self):
        from qgis.core import QgsProject

        from tract_geolocation_formatter import landcover_source as src

        self._clear_run_layers()
        try:
            res = self._run({"mode": "fetch"}, subdir="network_fetch")
            lines = self._lines(res)
            self.assertTrue(lines[0].startswith("Water overlap: ") and lines[0].endswith(" of 5 plots"), lines)
            self.assertTrue(lines[1].endswith(" of 5 plots"), lines)
            self.assertTrue(os.path.exists(res["csv"]))
            for f in res["fc"]["features"]:
                self.assertIsNotNone(f["properties"]["WaterOverlap_pct"])  # all covered
            group = self._group()
            layer = group.findLayers()[0].layer()
            self.assertTrue(layer.source().endswith(".vrt"))
            self.assertEqual(os.path.dirname(layer.source()), src.temp_dir())
            self.assertFalse(any(n.endswith(".vrt") for n in os.listdir(res["dir"])))
            names = [c.name() for c in QgsProject.instance().layerTreeRoot().children()]
            self.assertLess(names.index("plots.geojson"), names.index(group.name()))
            print("\n  real WorldCover:", lines, "tiles via", os.path.basename(layer.source()))
        finally:
            self._clear_run_layers()



@unittest.skipUnless(QGIS_AVAILABLE and os.environ.get("TRACT_NETWORK_TESTS") == "1",
                     "network test: set TRACT_NETWORK_TESTS=1")
class NetworkE2ETests(LandcoverPipelineTests):
    """AC-24 / AC-35 on real WorldCover data (tile N51W003, southern England):
    tests/fixtures/landcover_e2e_plots.geojson holds a plot on Rutland Water, one in
    Oakham, one touching the Thames at Oxford and one on farmland (Task 7)."""

    def test_ac24_ac35_lake_village_riverbank(self):
        from qgis.core import QgsFeatureRequest, QgsProject

        with open(os.path.join(_HERE, "fixtures", "landcover_e2e_plots.geojson"), encoding="utf-8") as fh:
            fc = json.load(fh)
        self._clear_run_layers()
        try:
            res = self._run({"mode": "fetch"}, fc=fc, subdir="e2e_real")
            self.assertEqual(self._lines(res), ["Water overlap: 2 of 4 plots",
                                                "Built-up overlap: 1 of 4 plots"])
            props = {f["properties"]["PlotID"]: f["properties"] for f in res["fc"]["features"]}
            lake, village, river, field = props["P0"], props["P1"], props["P2"], props["P3"]
            self.assertEqual(lake["WaterOverlap_pct"], 100.0)
            self.assertEqual(lake["BuiltUpOverlap_pct"], 0.0)
            self.assertGreaterEqual(village["BuiltUpOverlap_pct"], 90.0)
            self.assertEqual(village["WaterOverlap_pct"], 0.0)
            self.assertTrue(15.0 <= river["WaterOverlap_pct"] <= 40.0, river["WaterOverlap_pct"])
            self.assertEqual([field[k] for k in FIELDS], [0.0, 0.0, 0.0, 0.0])
            rows = self._csv_rows(res["csv"])
            self.assertEqual([(r["PlotID"], r["class"]) for r in rows],
                             [("P0", "water"), ("P1", "built_up"), ("P2", "water")])
            for r in rows:
                self.assertEqual(r["source"], "ESA WorldCover 2021 v200")
                # area = pct × plot area, computed unrounded; the CSV pct is rounded to
                # 2 decimals (±0.005 % of the plot) and the areas to 1 decimal.
                plot_area = float(r["plot_area_m2"])
                self.assertAlmostEqual(
                    float(r["overlap_area_m2"]), float(r["overlap_pct"]) / 100 * plot_area,
                    delta=0.00005 * plot_area + 0.1)
            # AC-35: the loaded output layer has the fields and the filter selects the water rows.
            layer = [lyr for lyr in QgsProject.instance().mapLayers().values()
                     if lyr.name() == "plots.geojson"][0]
            self.assertTrue(set(FIELDS) <= set(layer.fields().names()))
            hits = [f["PlotID"] for f in layer.getFeatures(
                QgsFeatureRequest().setFilterExpression('"WaterOverlap_pct" > 0'))]
            self.assertEqual(sorted(hits), sorted(r["PlotID"] for r in rows if r["class"] == "water"))
            # One tile → the /vsicurl/ path itself, no VRT.
            wc = self._group().findLayers()[0].layer()
            self.assertTrue(wc.source().startswith("/vsicurl/https://esa-worldcover"), wc.source())
            print("\n  real e2e:", self._lines(res),
                  {k: (v["WaterOverlap_pct"], v["BuiltUpOverlap_pct"]) for k, v in props.items()})
        finally:
            self._clear_run_layers()


def load_tests(loader, tests, pattern):
    """Collect the offline tests once; the network class adds only its own test
    (it inherits the helpers, not a second copy of the offline tests)."""
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(LandcoverPipelineTests))
    suite.addTest(NetworkFetchPipelineTests("test_real_fetch_run"))
    suite.addTest(NetworkE2ETests("test_ac24_ac35_lake_village_riverbank"))
    return suite


def _wkt(geometry):
    def ring(coords):
        return "(" + ",".join("{} {}".format(x, y) for x, y in coords) + ")"

    if geometry["type"] == "Polygon":
        return "MULTIPOLYGON((" + ",".join(ring(r) for r in geometry["coordinates"]) + "))"
    return "MULTIPOLYGON(" + ",".join(
        "(" + ",".join(ring(r) for r in poly) + ")" for poly in geometry["coordinates"]
    ) + ")"


if __name__ == "__main__":
    unittest.main()
