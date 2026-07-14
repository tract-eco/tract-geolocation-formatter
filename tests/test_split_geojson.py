"""
Unit tests for the GH-8 split helpers.

Unlike the other test modules, these do NOT require a QGIS environment: the
functions under test are pure ``json`` + stdlib. Because the helpers live in the
qgis-importing plugin module, we stub the heavy imports (qgis, shapely) in
``sys.modules`` *only* when they are not already importable — so the same test
file also runs unchanged inside a real QGIS Python environment.

    python -m pytest tests/test_split_geojson.py -v
"""

import json
import os
import sys
import tempfile
import types
import unittest


def _install_import_stubs():
    """Register minimal fake modules so the plugin module imports without QGIS.

    Only used when the real modules are absent. Each fake module returns a
    permissive placeholder for any attribute access, which is enough to satisfy
    the ``from qgis.core import (...)`` / ``from shapely.geometry import ...``
    statements at the top of the plugin module.
    """

    class _Any:
        def __init__(self, *a, **k):
            pass

        def __call__(self, *a, **k):
            return _Any()

        def __getattr__(self, _name):
            return _Any()

    class _StubModule(types.ModuleType):
        def __getattr__(self, _name):
            return _Any()

    import importlib

    for name in (
        "shapely",
        "shapely.geometry",
        "qgis",
        "qgis.PyQt",
        "qgis.PyQt.QtCore",
        "qgis.PyQt.QtGui",
        "qgis.PyQt.QtWidgets",
        "qgis.core",
    ):
        if name in sys.modules:
            continue
        # Only stub modules that genuinely can't be imported — never clobber a
        # real dependency (e.g. Shapely in a QGIS/venv env), which would poison
        # other test modules that rely on the real one.
        try:
            importlib.import_module(name)
            continue
        except Exception:
            sys.modules[name] = _StubModule(name)

    # The plugin module does `from .TRACT_Geolocation_Formatter_dialog import
    # TractGeolocationFormatterDialog`; stub that sibling so we don't execute
    # the real (qgis-dependent) dialog module.
    dlg_name = "tract_geolocation_formatter.TRACT_Geolocation_Formatter_dialog"
    if dlg_name not in sys.modules:
        dlg = types.ModuleType(dlg_name)
        dlg.TractGeolocationFormatterDialog = _Any
        sys.modules[dlg_name] = dlg


# Make the repo root importable, then load the helpers (stubbing only if needed).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from tract_geolocation_formatter.TRACT_Geolocation_Formatter import (
        _partition_node_ids,
        _split_geojson_by_node_id,
        _split_output_path,
    )
except ImportError:
    _install_import_stubs()
    from tract_geolocation_formatter.TRACT_Geolocation_Formatter import (
        _partition_node_ids,
        _split_geojson_by_node_id,
        _split_output_path,
    )


def _feature(node_id, fid):
    """Build a minimal GeoJSON feature with the given NodeID (or None)."""
    props = {"fid": fid}
    if node_id is not _MISSING:
        props["NodeID"] = node_id
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [float(fid), 0.0]},
    }


_MISSING = object()  # sentinel: omit the NodeID property entirely


def _feature_collection(features):
    return {
        "type": "FeatureCollection",
        "name": "plots",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }


class TestSplitOutputPath(unittest.TestCase):

    def test_geojson_extension(self):
        self.assertEqual(_split_output_path("/data/plots.geojson", 2), "/data/plots-2.geojson")

    def test_json_extension(self):
        self.assertEqual(_split_output_path("/data/plots.json", 3), "/data/plots-3.json")

    def test_no_extension(self):
        self.assertEqual(_split_output_path("/data/plots", 1), "/data/plots-1")

    def test_dots_in_dir(self):
        self.assertEqual(
            _split_output_path("/data.old/plots.geojson", 5),
            "/data.old/plots-5.geojson",
        )


class TestPartitionNodeIds(unittest.TestCase):

    def test_num_files_respected(self):
        counts = {"a": 3, "b": 1, "c": 2, "d": 4}
        bins = _partition_node_ids(counts, 2)
        self.assertEqual(len(bins), 2)
        # Every key appears exactly once across all bins.
        flat = [k for b in bins for k in b]
        self.assertCountEqual(flat, list(counts))

    def test_balances_counts(self):
        counts = {"a": 5, "b": 4, "c": 3, "d": 2, "e": 1}  # total 15
        bins = _partition_node_ids(counts, 3)
        loads = [sum(counts[k] for k in b) for b in bins]
        # 15 over 3 bins ideally 5 each; LPT achieves 5/5/5 here.
        self.assertEqual(sorted(loads), [5, 5, 5])

    def test_deterministic(self):
        counts = {"z": 2, "a": 2, "m": 2, "b": 1}
        self.assertEqual(_partition_node_ids(counts, 2), _partition_node_ids(counts, 2))

    def test_single_group_single_file(self):
        self.assertEqual(_partition_node_ids({"only": 7}, 1), [["only"]])

    def test_equal_counts_round_robin(self):
        counts = {"a": 1, "b": 1, "c": 1, "d": 1}
        bins = _partition_node_ids(counts, 2)
        loads = sorted(sum(counts[k] for k in b) for b in bins)
        self.assertEqual(loads, [2, 2])


class TestSplitGeojsonByNodeId(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def _write(self, features, filename="plots.geojson"):
        path = os.path.join(self.tmpdir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_feature_collection(features), fh)
        return path

    def _load(self, path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_union_equals_input(self):
        """AC3: union of split features == input (count + NodeID set)."""
        features = [_feature(f"N{i % 4}", i) for i in range(20)]
        path = self._write(features)
        written = _split_geojson_by_node_id(path, 3)

        all_feats = []
        node_sets = []
        for out_path, count in written:
            fc = self._load(out_path)
            self.assertEqual(len(fc["features"]), count)
            all_feats.extend(fc["features"])
            node_sets.append({f["properties"]["NodeID"] for f in fc["features"]})

        self.assertEqual(len(all_feats), len(features))
        self.assertEqual(
            {f["properties"]["NodeID"] for f in all_feats},
            {f["properties"]["NodeID"] for f in features},
        )
        # AC3: NodeID sets are pairwise disjoint.
        for i in range(len(node_sets)):
            for j in range(i + 1, len(node_sets)):
                self.assertEqual(node_sets[i] & node_sets[j], set())

    def test_counts_balanced(self):
        """AC4: feature counts balanced across files."""
        # 6 groups of 10 features each -> 60 features into 3 files -> 20 each.
        features = []
        fid = 0
        for g in range(6):
            for _ in range(10):
                features.append(_feature(f"N{g}", fid))
                fid += 1
        path = self._write(features)
        written = _split_geojson_by_node_id(path, 3)
        counts = sorted(c for _p, c in written)
        self.assertEqual(counts, [20, 20, 20])

    def test_deterministic_output(self):
        """AC5: identical input yields identical partition across two runs."""
        features = [_feature(f"N{i % 5}", i) for i in range(23)]
        path_a = self._write(features, "a.geojson")
        path_b = self._write(features, "b.geojson")
        written_a = _split_geojson_by_node_id(path_a, 3)
        written_b = _split_geojson_by_node_id(path_b, 3)

        for (pa, _ca), (pb, _cb) in zip(written_a, written_b):
            fa = self._load(pa)["features"]
            fb = self._load(pb)["features"]
            self.assertEqual(
                [f["properties"]["NodeID"] for f in fa],
                [f["properties"]["NodeID"] for f in fb],
            )
            self.assertEqual(
                [f["properties"]["fid"] for f in fa],
                [f["properties"]["fid"] for f in fb],
            )

    def test_too_many_files_raises(self):
        """AC6/AC9: num_files > unique raises ValueError; no files written."""
        features = [_feature("N0", 0), _feature("N1", 1), _feature("N2", 2)]
        path = self._write(features)
        with self.assertRaises(ValueError):
            _split_geojson_by_node_id(path, 4)
        # No split files were written.
        siblings = [n for n in os.listdir(self.tmpdir) if n != "plots.geojson"]
        self.assertEqual(siblings, [])

    def test_less_than_two_unique_raises(self):
        """AC6: the <2 unique case raises when 2 files requested."""
        features = [_feature("only", 0), _feature("only", 1)]
        path = self._write(features)
        with self.assertRaises(ValueError):
            _split_geojson_by_node_id(path, 2)

    def test_num_files_equals_unique(self):
        """AC2: num_files == unique produces exactly num_files files."""
        features = [_feature(f"N{i}", i) for i in range(4)]
        path = self._write(features)
        written = _split_geojson_by_node_id(path, 4)
        self.assertEqual(len(written), 4)
        self.assertTrue(all(c == 1 for _p, c in written))

    def test_num_files_less_than_unique(self):
        """AC2: num_files < unique produces exactly num_files files."""
        features = [_feature(f"N{i}", i) for i in range(10)]
        path = self._write(features)
        written = _split_geojson_by_node_id(path, 3)
        self.assertEqual(len(written), 3)
        self.assertEqual(sum(c for _p, c in written), 10)

    def test_null_and_missing_node_id_single_group(self):
        """AC7: missing/None NodeID features form a single '' group."""
        features = [
            _feature(None, 0),
            _feature(_MISSING, 1),   # property absent entirely
            _feature("N1", 2),
            _feature("N2", 3),
        ]
        path = self._write(features)
        # 3 unique groups: "", "N1", "N2" -> requesting 3 must succeed.
        written = _split_geojson_by_node_id(path, 3)
        self.assertEqual(len(written), 3)
        # The two empty-NodeID features must land together in exactly one file.
        empties_per_file = []
        for out_path, _count in written:
            fc = self._load(out_path)
            empties = [
                f for f in fc["features"]
                if f["properties"].get("NodeID") in (None, "") or "NodeID" not in f["properties"]
            ]
            empties_per_file.append(len(empties))
        self.assertEqual(sorted(empties_per_file), [0, 0, 2])
        # Requesting 4 (more than the 3 unique groups) must raise.
        with self.assertRaises(ValueError):
            _split_geojson_by_node_id(path, 4)

    def test_header_preserved(self):
        """Header keys (type, crs, name) preserved in each split file."""
        features = [_feature(f"N{i}", i) for i in range(6)]
        path = self._write(features)
        written = _split_geojson_by_node_id(path, 2)
        src = self._load(path)
        for out_path, _count in written:
            fc = self._load(out_path)
            self.assertEqual(fc["type"], src["type"])
            self.assertEqual(fc["name"], src["name"])
            self.assertEqual(fc["crs"], src["crs"])

    def test_original_feature_order_preserved(self):
        """Feature order within each file follows the monolith's order."""
        features = [_feature(f"N{i % 2}", i) for i in range(10)]
        path = self._write(features)
        written = _split_geojson_by_node_id(path, 2)
        for out_path, _count in written:
            fc = self._load(out_path)
            fids = [f["properties"]["fid"] for f in fc["features"]]
            self.assertEqual(fids, sorted(fids))


if __name__ == "__main__":
    unittest.main()
