# -*- coding: utf-8 -*-
"""
Polygon hole fixing (SPEC-fix-holes) — pure Shapely, no QGIS.

Two ways to remove interior rings (holes):

- ``fill_holes``  — drop the interior rings, keep the exterior. Area **grows** by
  the hole.
- ``cut_holes``   — open each hole with a thin **slit** to the nearest boundary,
  turning it into a concave notch. The result stays a single valid polygon (same
  feature, fields preserved) and area is **preserved** except for the negligible
  slit strip. Iterates over multiple holes.

Why a slit and not a straight split into two halves: two adjacent halves that
cover the donut must share the cut edge, which is an **invalid** OGC MultiPolygon
(parts may only touch at points). A thin slit avoids that and keeps a single valid
polygon. The slit width defaults to just above the plugin's 6-decimal coordinate
precision so it survives truncation.

This module is intentionally free of any QGIS import so it unit-tests without a
QGIS environment. The caller converts QgsGeometry <-> Shapely at the boundary.
"""

import math

from shapely.geometry import MultiPolygon, Polygon, LineString
from shapely.ops import nearest_points

_MAX_CUT_ITERATIONS = 200

# Slit half-width. buffer() doubles it, giving a ~2e-6 deg (~0.2 m) channel — just
# above the 6-decimal (~0.11 m) coordinate precision so truncation can't re-close
# it. Negligible area loss (width x short slit length).
_SLIT_WIDTH = 1e-6


def has_holes(geom):
    """True if a Polygon/MultiPolygon has any interior ring."""
    if isinstance(geom, Polygon):
        return len(geom.interiors) > 0
    if isinstance(geom, MultiPolygon):
        return any(len(part.interiors) > 0 for part in geom.geoms)
    return False


def fill_holes(geom):
    """Drop interior rings, keep exteriors. Returns (new_geom, notes)."""
    notes = []
    if isinstance(geom, Polygon):
        if geom.interiors:
            notes.append("filled {0} hole(s)".format(len(geom.interiors)))
        return Polygon(geom.exterior), notes
    if isinstance(geom, MultiPolygon):
        parts = []
        holes = 0
        for part in geom.geoms:
            holes += len(part.interiors)
            parts.append(Polygon(part.exterior))
        if holes:
            notes.append("filled {0} hole(s)".format(holes))
        combined = parts[0] if len(parts) == 1 else MultiPolygon(parts)
        return combined, notes
    return geom, notes


def _interior_count(geom):
    if isinstance(geom, Polygon):
        return len(geom.interiors)
    if isinstance(geom, MultiPolygon):
        return sum(len(p.interiors) for p in geom.geoms)
    return 0


def cut_holes(geom, width=_SLIT_WIDTH):
    """Open every hole with a thin slit to the nearest boundary.

    Returns (new_geom, parts_count, notes). Iterates over holes: each pass opens
    one hole by removing a thin channel from the nearest exterior point to the
    hole, turning the hole into a concave notch. A donut becomes a single valid
    hole-free Polygon; area is preserved except the negligible slit strip. If a
    hole cannot be opened, that polygon is left unchanged (caller flags it via
    ``has_holes``).
    """
    if not isinstance(geom, (Polygon, MultiPolygon)):
        return geom, 0, []

    notes = []
    done = []
    work = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
    iterations = 0
    while work:
        iterations += 1
        if iterations > _MAX_CUT_ITERATIONS:
            notes.append("hole opening aborted after too many iterations")
            done.extend(work)
            break

        poly = work.pop()
        if not poly.interiors:
            done.append(poly)
            continue

        hole_ring = poly.interiors[0]
        p_ext, p_hole = nearest_points(poly.exterior, hole_ring)
        # Extend the connector beyond both ends so the channel fully crosses the
        # exterior wall and reaches into the hole void — a channel that merely
        # touches the rings can leave a hairline and fail to open the hole.
        dx, dy = (p_hole.x - p_ext.x), (p_hole.y - p_ext.y)
        length = math.hypot(dx, dy)
        if length == 0:
            notes.append("degenerate hole connector; could not open a hole")
            done.append(poly)
            continue
        ux, uy = dx / length, dy / length
        ext = width * 10  # ~10x the slit half-width; crosses the rings with margin
        start = (p_ext.x - ux * ext, p_ext.y - uy * ext)
        end = (p_hole.x + ux * ext, p_hole.y + uy * ext)
        channel = LineString([start, end]).buffer(width, cap_style=2)
        opened = poly.difference(channel)

        made_progress = (
            not opened.is_empty
            and isinstance(opened, (Polygon, MultiPolygon))
            and _interior_count(opened) < len(poly.interiors)
        )
        if not made_progress:
            notes.append("could not open a hole cleanly")
            done.append(poly)  # leave as-is; has_holes() will flag it
            continue

        if isinstance(opened, Polygon):
            work.append(opened)
        else:
            work.extend(opened.geoms)

    result = done[0] if len(done) == 1 else MultiPolygon(done)
    parts = len(result.geoms) if isinstance(result, MultiPolygon) else 1
    return result, parts, notes


def fix_holes(geom, method):
    """Fix holes by ``method`` ('fill' or 'cut').

    Returns (new_geom, parts_count, notes, resolved). ``resolved`` is False when
    holes remain or the result is invalid — the caller then keeps the original
    geometry and flags the feature (DEC-H4).
    """
    if method == "fill":
        new_geom, notes = fill_holes(geom)
        parts = len(new_geom.geoms) if isinstance(new_geom, MultiPolygon) else 1
    elif method == "cut":
        new_geom, parts, notes = cut_holes(geom)
    else:
        return geom, 0, ["unknown fix method: {0}".format(method)], False

    resolved = (not has_holes(new_geom)) and new_geom.is_valid
    return new_geom, parts, notes, resolved
