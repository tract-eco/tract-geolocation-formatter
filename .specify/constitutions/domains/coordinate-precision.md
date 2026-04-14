# Domain: Coordinate Precision & Reprojection

Covers coordinate truncation rules and CRS handling.

---

## Coordinate Truncation

- All output coordinates are truncated (not rounded) to **6 decimal places**.
- 6 decimal places in WGS84 gives ~0.11m precision, which aligns with the EU TRACES system format.
- Truncation uses `math.trunc(value * 10^6) / 10^6` — this always moves toward zero, avoiding rounding-induced coordinate drift.
- Truncation is applied **once**, immediately after reprojection and before any validation or repair step.

### Why Truncate Instead of Round

Truncation is deterministic and predictable — `round()` can cause coordinates to shift across boundaries in edge cases. The TRACT platform expects truncated values for consistency with EU TRACES.

## Reprojection

- Input layers may be in any CRS that QGIS supports.
- All geometries are reprojected to **EPSG:4326** (WGS84) before processing.
- If the layer is already in EPSG:4326, no transform is applied.
- Layers with no valid CRS are rejected (error dialog shown to user).
- Reprojection uses `QgsCoordinateTransform` with the project's transform context.

## Area Calculation CRS

- Area calculations require an equal-area projection. The plugin uses **EPSG:6933** (World Cylindrical Equal Area).
- Area transform is applied to a copy of the geometry — the export geometry remains in EPSG:4326.
- Area is computed in square meters, then converted to hectares (`m² / 10000`).

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `COORD_DECIMALS` | `6` | Truncation precision |
| `AREA_CRS` | `EPSG:6933` | Equal-area CRS for area checks |
| `MIN_PLOT_AREA_HA` | `0.05` | Minimum polygon area threshold |
