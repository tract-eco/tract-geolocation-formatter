# -*- coding: utf-8 -*-
"""
Polygon overlap detection (GH-12) — pure Shapely, no QGIS.

Three categories:

- **A** — parts of one MultiPolygon overlap each other. Found with
  ``find_part_overlaps`` and always dissolved (``dissolve_part_overlaps``).
- **B** — two plots with the same NodeID overlap.
- **C** — two plots with different NodeIDs overlap.

B and C are found with ``find_feature_overlaps`` on the written GeoJSON.

Predicates (spec FR-2):

- overlap: interiors intersect in an area, ``a.relate_pattern(b, "2********")``.
  Shared edges and touching vertices are not overlaps.
- containment: ``a.covers(b)`` (b inside a, may touch a's boundary from inside).
- identical: ``a.covers(b) and b.covers(a)``.

Compatibility: Shapely 1.7.0 (QGIS 3.38 macOS) through 2.x. Only the API common
to all of them is used (``relate_pattern``, ``covers``, ``intersection``,
``unary_union``, ``prep``); see the spec's NFR "Compatibility" for what is
excluded. Candidate pairs come from a pure-Python sort-and-sweep on bounding
boxes rather than a spatial index tree.

This module is intentionally free of any QGIS import so it unit-tests without a
QGIS environment. The caller converts QgsGeometry <-> Shapely at the boundary and
supplies an ``area_fn`` that returns m² (EPSG:6933); without one, planar area is
used.
"""

import math
from dataclasses import dataclass
from typing import Any, Optional

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping
from shapely.ops import unary_union
from shapely.prepared import prep

OVERLAP_PATTERN = "2********"

CATEGORY_PARTS = "A"
CATEGORY_SAME_NODE = "B"
CATEGORY_CROSS_NODE = "C"

KIND_PARTIAL = "partial"
KIND_CONTAINMENT = "containment"
KIND_IDENTICAL = "identical"

# Overlaps file (spec FR-11): property order is fixed.
OVERLAP_PROPERTIES = (
    "category",
    "type",
    "feature_a",
    "feature_b",
    "NodeID_a",
    "NodeID_b",
    "PlotID_a",
    "PlotID_b",
    "part_a",
    "part_b",
    "area_m2",
    "pct_of_smaller",
    "below_threshold",
    "action",
)

# Same CRS member the QGIS GeoJSON writer puts in the main output.
_CRS84 = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}


@dataclass(frozen=True)
class PartFinding:
    """Category A: parts ``i`` and ``j`` (0-based, i < j) of one MultiPolygon overlap."""

    i: int
    j: int
    overlap_geom: Any
    area: float
    pct_of_smaller: float
    below_threshold: bool


@dataclass(frozen=True)
class Finding:
    """Category B/C: plots ``index_a`` < ``index_b`` overlap.

    ``container`` / ``contained`` are item indices for containment and identical
    findings (identical: ``index_a`` is the container), otherwise ``None``.
    """

    index_a: int
    index_b: int
    category: str
    kind: str
    container: Optional[int]
    contained: Optional[int]
    overlap_geom: Any
    area: float
    pct_of_smaller: float
    below_threshold: bool


def _planar_area(geom):
    return geom.area


def _polygonal(geom):
    """Keep only the polygonal pieces of an intersection result."""
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    if isinstance(geom, GeometryCollection):
        polys = []
        for g in geom.geoms:
            if isinstance(g, Polygon):
                polys.append(g)
            elif isinstance(g, MultiPolygon):
                polys.extend(g.geoms)
        if len(polys) == 1:
            return polys[0]
        return MultiPolygon(polys)
    return MultiPolygon()


def _first_z(geom):
    """Z of the first vertex of a polygonal geometry (0.0 if it has none)."""
    polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
    for p in polys:
        for c in p.exterior.coords:
            if len(c) > 2 and not math.isnan(c[2]):
                return c[2]
    return 0.0


def _match_z(geom, like):
    """Give ``geom`` the dimension of ``like``.

    A clip creates new vertices where it cuts the boundary, and their Z may be
    missing or NaN. Z here is not used downstream, so with a Z ``like`` every
    vertex keeps its own Z and any missing one takes the first Z of ``like``;
    with a 2D ``like`` the Z is dropped.
    """
    if geom.is_empty:
        return geom
    keep_z = like.has_z
    z = _first_z(like) if keep_z else None

    def ring(coords):
        out = []
        for c in coords:
            if not keep_z:
                out.append((c[0], c[1]))
                continue
            cz = c[2] if len(c) > 2 and not math.isnan(c[2]) else z
            out.append((c[0], c[1], cz))
        return out

    def poly(p):
        return Polygon(ring(p.exterior.coords), [ring(r.coords) for r in p.interiors])

    if isinstance(geom, Polygon):
        return poly(geom)
    return MultiPolygon([poly(p) for p in geom.geoms])


def _pct(area, smaller):
    if smaller <= 0:
        return 100.0
    return area / smaller * 100.0


def _node_key(node_id):
    return "" if node_id is None else str(node_id)


# --------------------------------------------------------------------------- #
# Category A
# --------------------------------------------------------------------------- #


def find_part_overlaps(geom, area_fn=None, min_pct=1.0):
    """Overlapping part pairs of a MultiPolygon whose parts are each valid.

    ``pct_of_smaller`` is relative to the smaller of the two **parts**.
    Returns ``[]`` for a Polygon or anything that isn't a MultiPolygon.
    """
    if not isinstance(geom, MultiPolygon):
        return []
    area_fn = area_fn or _planar_area
    parts = list(geom.geoms)
    areas = [None] * len(parts)
    findings = []
    for i in range(len(parts)):
        pi = parts[i]
        if pi.is_empty:
            continue
        prepared = prep(pi)
        for j in range(i + 1, len(parts)):
            pj = parts[j]
            if pj.is_empty or not prepared.intersects(pj):
                continue
            if not pi.relate_pattern(pj, OVERLAP_PATTERN):
                continue
            if areas[i] is None:
                areas[i] = area_fn(pi)
            if areas[j] is None:
                areas[j] = area_fn(pj)
            if prepared.covers(pj):
                overlap, contained = pj, True
            elif pj.covers(pi):
                overlap, contained = pi, True
            else:
                overlap, contained = _polygonal(pi.intersection(pj)), False
            area = area_fn(overlap)
            pct = 100.0 if contained else _pct(area, min(areas[i], areas[j]))
            findings.append(
                PartFinding(i, j, overlap, area, pct, pct < min_pct)
            )
    return findings


def dissolve_part_overlaps(geom):
    """Dissolve the parts into their union (removes double-counted area)."""
    return unary_union(list(geom.geoms))


# --------------------------------------------------------------------------- #
# Categories B / C
# --------------------------------------------------------------------------- #


def candidate_pairs(bounds):
    """Index pairs ``(i, j)``, ``i < j``, whose bounding boxes intersect.

    Touching boxes count. Pure-Python sort-and-sweep on minx. Entries that are
    not 4-tuples (e.g. ``()`` for an empty geometry) are skipped. The result is
    sorted by ``(i, j)``, so it is deterministic.
    """
    valid = [k for k, b in enumerate(bounds) if b is not None and len(b) == 4]
    order = sorted(valid, key=lambda k: (bounds[k][0], k))
    pairs = []
    for p, i in enumerate(order):
        minx_i, miny_i, maxx_i, maxy_i = bounds[i]
        for q in range(p + 1, len(order)):
            j = order[q]
            minx_j, miny_j, _maxx_j, maxy_j = bounds[j]
            if minx_j > maxx_i:
                break
            if miny_j <= maxy_i and miny_i <= maxy_j:
                pairs.append((i, j) if i < j else (j, i))
    pairs.sort()
    return pairs


def find_feature_overlaps(items, area_fn=None, min_pct=1.0, plot_areas=None, progress=None):
    """Overlapping plot pairs (categories B and C).

    ``items``: sequence of dicts ``{"index", "node_id", "plot_id", "geom"}`` with
    valid Shapely geometries. ``plot_areas``: optional mapping ``index -> area``
    in the same unit as ``area_fn`` (saves recomputing whole-plot areas).
    ``progress``: optional callable ``progress(done, total)``.

    Returns every overlap (below-threshold ones included, flagged), sorted by
    ``(category, index_a, index_b)``.
    """
    area_fn = area_fn or _planar_area
    items = list(items)
    pairs = candidate_pairs([it["geom"].bounds for it in items])
    total = len(pairs)
    step = max(1, total // 100)

    def plot_area(item):
        if plot_areas is not None and item["index"] in plot_areas:
            return plot_areas[item["index"]]
        return area_fn(item["geom"])

    findings = []
    prepared_pos = None
    prepared = None
    for done, (p, q) in enumerate(pairs, start=1):
        if progress is not None and (done % step == 0 or done == total):
            progress(done, total)
        if p != prepared_pos:
            prepared_pos = p
            prepared = prep(items[p]["geom"])
        gp = items[p]["geom"]
        gq = items[q]["geom"]
        if not prepared.intersects(gq):
            continue
        if not gp.relate_pattern(gq, OVERLAP_PATTERN):
            continue

        # Normalise so that a is the item with the lower output index.
        if items[p]["index"] <= items[q]["index"]:
            a, b, ga, gb = items[p], items[q], gp, gq
            a_covers_b = prepared.covers(gq)
            b_covers_a = gq.covers(gp)
        else:
            a, b, ga, gb = items[q], items[p], gq, gp
            a_covers_b = gq.covers(gp)
            b_covers_a = prepared.covers(gq)

        if a_covers_b and b_covers_a:
            kind, container, contained, overlap = KIND_IDENTICAL, a["index"], b["index"], gb
        elif a_covers_b:
            kind, container, contained, overlap = KIND_CONTAINMENT, a["index"], b["index"], gb
        elif b_covers_a:
            kind, container, contained, overlap = KIND_CONTAINMENT, b["index"], a["index"], ga
        else:
            kind, container, contained = KIND_PARTIAL, None, None
            overlap = _polygonal(ga.intersection(gb))

        area = area_fn(overlap)
        if kind == KIND_PARTIAL:
            pct = _pct(area, min(plot_area(a), plot_area(b)))
        else:
            pct = 100.0
        category = (
            CATEGORY_SAME_NODE
            if _node_key(a.get("node_id")) == _node_key(b.get("node_id"))
            else CATEGORY_CROSS_NODE
        )
        findings.append(
            Finding(
                index_a=a["index"],
                index_b=b["index"],
                category=category,
                kind=kind,
                container=container,
                contained=contained,
                overlap_geom=overlap,
                area=area,
                pct_of_smaller=pct,
                below_threshold=pct < min_pct,
            )
        )

    findings.sort(key=lambda f: (f.category, f.index_a, f.index_b))
    return findings


# --------------------------------------------------------------------------- #
# Fixes (categories B / C)
# --------------------------------------------------------------------------- #

ACTION_CLIPPED_A = "clipped_a"
ACTION_CLIPPED_B = "clipped_b"
ACTION_DELETED_A = "deleted_a"
ACTION_DELETED_B = "deleted_b"
ACTION_KEPT = "kept"
ACTION_SKIPPED_Z = "skipped_z"


def _side(finding, index, a_action, b_action):
    return a_action if index == finding.index_a else b_action


def apply_feature_fixes(
    items,
    findings,
    clip_same_node,
    containment_actions,
    cross_node_actions,
    skip_clip=frozenset(),
    plot_areas=None,
):
    """Apply the user's review choices (spec FR-6). Does not truncate.

    Order:

    1. Deletions from ``containment_actions`` (``{(a, b): "delete_contained" |
       "delete_container" | "keep"}``). For identical pairs the contained plot
       is the later one in output order.
    2. Same-NodeID clipping. ``clip_same_node`` is either a bool (True: per
       NodeID, plots sorted by ``(-area, plot_id, index)`` (DEC-5); each plot is
       clipped by every earlier plot in that order it has a partial finding
       with) or a dict ``{(a, b): "keep" | "remove_from_a" | "remove_from_b"}``
       of per-pair choices, applied in that same size order.
    3. Cross-NodeID clipping from ``cross_node_actions`` (``{(a, b): "keep" |
       "remove_from_a" | "remove_from_b"}``) in finding order, against the
       current geometries. Pairs with a deleted plot are skipped.

    Below-threshold findings are never applied. Plots with Z values are
    clipped too; new vertices take an existing Z of the plot (``_match_z``).
    Clips of a plot in ``skip_clip`` are skipped and recorded as ``skipped_z``
    (the plugin passes none). ``plot_areas`` (``index -> area``) orders step 2; planar area
    is used without it.

    Returns ``(new_geoms, deleted, actions)``: ``{index: geom}`` for changed,
    not-deleted plots; the set of deleted indices; ``{(a, b): action}`` for
    every finding acted on (clipped_a/clipped_b/deleted_a/deleted_b/kept/
    skipped_z). Findings not acted on are absent.
    """
    by_index = {it["index"]: it for it in items}
    current = {idx: it["geom"] for idx, it in by_index.items()}
    deleted = set()
    actions = {}
    skip_clip = frozenset(skip_clip)
    fixable = [f for f in findings if not f.below_threshold]

    # 1. Deletions.
    for f in fixable:
        if f.kind == KIND_PARTIAL:
            continue
        choice = containment_actions.get((f.index_a, f.index_b), "keep")
        if choice == "delete_contained":
            target = f.contained
        elif choice == "delete_container":
            target = f.container
        else:
            actions[(f.index_a, f.index_b)] = ACTION_KEPT
            continue
        deleted.add(target)
        actions[(f.index_a, f.index_b)] = _side(f, target, ACTION_DELETED_A, ACTION_DELETED_B)

    def clip(f, target, other):
        if target in skip_clip:
            actions[(f.index_a, f.index_b)] = ACTION_SKIPPED_Z
            return
        clipped = _polygonal(current[target].difference(current[other]))
        current[target] = _match_z(clipped, current[target])
        actions[(f.index_a, f.index_b)] = _side(f, target, ACTION_CLIPPED_A, ACTION_CLIPPED_B)

    # 2. Same-NodeID clipping.
    same_partial = [
        f for f in fixable if f.category == CATEGORY_SAME_NODE and f.kind == KIND_PARTIAL
    ]
    # A dict gives one choice per pair (as for cross-NodeID pairs); a bool
    # clips every pair's smaller plot (True) or keeps both (False).
    same_node_choices = clip_same_node if isinstance(clip_same_node, dict) else None
    if not clip_same_node and same_node_choices is None:
        for f in same_partial:
            actions[(f.index_a, f.index_b)] = ACTION_KEPT
    else:
        def area(idx):
            if plot_areas is not None and idx in plot_areas:
                return plot_areas[idx]
            return by_index[idx]["geom"].area

        def plot_key(idx):
            pid = by_index[idx].get("plot_id")
            return "" if pid is None else str(pid)

        involved = set()
        for f in same_partial:
            involved.update((f.index_a, f.index_b))
        rank = {
            idx: r
            for r, idx in enumerate(
                sorted(involved, key=lambda i: (-area(i), plot_key(i), i))
            )
        }
        # For each pair the lower-ranked (smaller) plot is clipped. Processing
        # pairs by (rank of the clipped plot, rank of the keeper) clips each
        # plot against every larger partner, larger plots first.
        ordered = sorted(
            same_partial,
            key=lambda f: (
                max(rank[f.index_a], rank[f.index_b]),
                min(rank[f.index_a], rank[f.index_b]),
            ),
        )
        for f in ordered:
            if f.index_a in deleted or f.index_b in deleted:
                continue
            if same_node_choices is not None:
                choice = same_node_choices.get((f.index_a, f.index_b), "keep")
                if choice == "remove_from_a":
                    clip(f, f.index_a, f.index_b)
                elif choice == "remove_from_b":
                    clip(f, f.index_b, f.index_a)
                else:
                    actions[(f.index_a, f.index_b)] = ACTION_KEPT
                continue
            if rank[f.index_a] < rank[f.index_b]:
                keeper, target = f.index_a, f.index_b
            else:
                keeper, target = f.index_b, f.index_a
            clip(f, target, keeper)

    # 3. Cross-NodeID clipping.
    for f in fixable:
        if f.category != CATEGORY_CROSS_NODE or f.kind != KIND_PARTIAL:
            continue
        if f.index_a in deleted or f.index_b in deleted:
            continue
        choice = cross_node_actions.get((f.index_a, f.index_b), "keep")
        if choice == "remove_from_a":
            clip(f, f.index_a, f.index_b)
        elif choice == "remove_from_b":
            clip(f, f.index_b, f.index_a)
        else:
            actions[(f.index_a, f.index_b)] = ACTION_KEPT

    new_geoms = {
        idx: geom
        for idx, geom in current.items()
        if idx not in deleted and geom is not by_index[idx]["geom"]
    }
    return new_geoms, deleted, actions


# --------------------------------------------------------------------------- #
# Guard and dialog helpers
# --------------------------------------------------------------------------- #


def residual_overlap_pct(a, b):
    """Overlap area of ``a`` and ``b`` as % of the smaller one (planar ratio).

    Used by the post-fix guard; 0.0 when they don't overlap in an area.
    """
    if a.is_empty or b.is_empty or not a.intersects(b):
        return 0.0
    smaller = min(a.area, b.area)
    if smaller <= 0:
        return 0.0
    return a.intersection(b).area / smaller * 100.0


def would_remove_last_plot(node_counts, node_ids, deletions):
    """Indices in ``deletions`` whose deletion empties their NodeID.

    ``node_counts``: NodeID -> number of plots; ``node_ids``: index -> NodeID;
    ``deletions``: iterable of indices the user chose to delete.
    """
    deletions = set(deletions)
    per_node = {}
    for idx in deletions:
        key = _node_key(node_ids.get(idx))
        per_node.setdefault(key, set()).add(idx)
    counts = {_node_key(k): v for k, v in node_counts.items()}
    marked = set()
    for key, idxs in per_node.items():
        if len(idxs) >= counts.get(key, 0):
            marked |= idxs
    return marked


# --------------------------------------------------------------------------- #
# Overlaps file
# --------------------------------------------------------------------------- #


def _truncate_coords(coords, factor):
    if isinstance(coords, (int, float)):
        return math.trunc(coords * factor) / factor
    return [_truncate_coords(c, factor) for c in coords]


def _geometry_json(geom, decimals):
    if geom is None:
        return None
    if not isinstance(geom, dict):
        if geom.is_empty:
            return None
        geom = mapping(geom)
    factor = 10 ** decimals
    if geom.get("type") == "GeometryCollection":
        return {
            "type": "GeometryCollection",
            "geometries": [_geometry_json(g, decimals) for g in geom["geometries"]],
        }
    return {"type": geom["type"], "coordinates": _truncate_coords(geom["coordinates"], factor)}


def overlaps_feature_collection(records, decimals=6):
    """GeoJSON FeatureCollection for ``<base>_overlaps.geojson`` (spec FR-11).

    Each record is a dict with the ``OVERLAP_PROPERTIES`` keys (missing -> null)
    plus ``"geometry"`` (Shapely geometry or GeoJSON dict). Coordinates are
    truncated to ``decimals``; ``area_m2`` is rounded to 2 decimals and
    ``pct_of_smaller`` to 3.
    """
    features = []
    for rec in records:
        props = {}
        for key in OVERLAP_PROPERTIES:
            value = rec.get(key)
            if key == "area_m2" and value is not None:
                value = round(float(value), 2)
            elif key == "pct_of_smaller" and value is not None:
                value = round(float(value), 3)
            elif key == "below_threshold":
                value = bool(value)
            props[key] = value
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": _geometry_json(rec.get("geometry"), decimals),
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "overlaps",
        "crs": _CRS84,
        "features": features,
    }
