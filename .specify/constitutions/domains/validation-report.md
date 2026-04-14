# Domain: Validation Report

Covers the CSV validation report generated alongside the GeoJSON output.

---

## Purpose

The validation report provides a per-feature, per-issue log of all geometry checks and repairs applied during processing. It helps users identify which features need manual correction before uploading to the TRACT platform.

## CSV Format

The report is written as a CSV file in the same directory as the GeoJSON output, with the suffix `_validation_report.csv`.

### Columns

| Column | Type | Description |
|--------|------|-------------|
| `feature_id` | Integer | QGIS feature ID (internal, 0-based) |
| `NodeID` | String | NodeID assigned to the feature |
| `PlotID` | String | PlotID assigned to the feature (may be empty) |
| `status` | String | `"WARNING"` (auto-fixed) or `"ERROR"` (manual fix needed) |
| `issue_type` | String | Machine-readable issue category |
| `message` | String | Human-readable description of the issue or repair |

### Issue Types

| `issue_type` | `status` | Meaning |
|--------------|----------|---------|
| `z_values` | WARNING | Z values detected and removed |
| `coordinate_rounding` | WARNING | Coordinates truncated to 6 decimals |
| `duplicate_vertices` | WARNING | Consecutive duplicate vertices removed |
| `invalid_geometry` | WARNING | makeValid() applied successfully |
| `invalid_geometry_unrepaired` | ERROR | makeValid() failed or geometry still invalid |
| `tract_geometry_validation` | ERROR | Failed one or more TRACT geometry checks |
| `small_area` | ERROR | Area below 0.05 ha minimum |
| `polygon_holes` | ERROR | Polygon contains interior holes |

## Report Dialog

After export, a summary report dialog is shown to the user (`_show_report_dialog`). It displays:
- Total features processed
- Features written vs. skipped
- Count of NEEDS_FIX features
- Detailed per-feature repair log

The dialog is scrollable (1000x700px) with a read-only text area.
