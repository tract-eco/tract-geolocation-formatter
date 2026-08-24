# TRACT Geolocation Formatter (QGIS Plugin)

A QGIS plugin to **validate, clean, and transform geolocation data** into the **TRACT GeoJSON template**, helping users identify and fix common geometry issues before ingestion into the TRACT platform.

This plugin is designed for GIS practitioners preparing farm or sourcing-area geometries for sustainability, traceability, and deforestation analysis workflows.


## Overview

Geolocation data often contains subtle issues that can break downstream analytics or ingestion pipelines, such as:

- Invalid polygon geometries
- Self-intersections
- Unclosed rings
- Duplicate or overlapping vertices
- Mixed geometry types
- Incorrect attribute schemas

The **TRACT Geolocation Formatter** provides a guided workflow inside QGIS to:

- Detect common geometry and formatting issues
- Standardize geolocation files into TRACT’s expected GeoJSON structure
- Reduce back-and-forth between data providers and platform ingestion

Before validation and processing, the plugin **truncates all geometry X/Y coordinates to six decimal places**. This precision level aligns with the coordinate format used in the EU TRACES system, helping avoid geometry inconsistencies caused by excessive decimal precision. Z (elevation) values are carried through untouched.

The plugin works directly on existing QGIS layers and does **not** require advanced GIS scripting knowledge.


## Key Features

- Adapt geolocation layers to the **TRACT GeoJSON template**
- Add and validate required TRACT attributes, including:
  - Node ID
  - Plot ID
- Ensure consistent schema structure across all features
- Standardize coordinate precision by truncating X/Y coordinates to six decimal places
- Preserve **Z (elevation) values** — TRACT accepts 3D coordinates, so Z is carried from input to output unchanged
- Validate polygon geometries (e.g. self-intersections, invalid rings)
- Report approximate latitude/longitude coordinates of detected boundary self-intersections so they can be located and fixed in QGIS
- Remove consecutive duplicate vertices
- Repair invalid geometries using makeValid
- Detect polygons containing interior holes, and **optionally fix them** by filling them in or cutting them open (see [Fixing Polygon Holes](#fixing-polygon-holes-optional))
- Validate minimum polygon area requirements
- Automatically reproject geometries to EPSG:4326
- Identify intersecting or overlapping line segments
- Detect and flag common geometry issues before export
- Export ready-to-upload GeoJSON files for the TRACT platform
- Optionally generate a populated **Master Data XLSX** file (Farms or Farmer Groups) alongside the GeoJSON, with one row per unique NodeID and a user-selected country — ready for TRACT ingestion without manual template filling
- Optionally **split the clean GeoJSON output into 2–10 smaller files** so large datasets upload to TRACT under its size limit — features sharing a NodeID always stay together in one file, and feature counts are balanced across files
- Scrollable dialog so OK / Cancel buttons stay reachable on small / laptop screens
- Compatible with both **QGIS 3.x** and **QGIS 4** from a single codebase
- Works with common GIS formats (GeoJSON, Shapefile, GeoPackage)

The plugin attempts to automatically fix some geometry issues where possible. However, certain issues may require manual correction by the user in QGIS before the dataset can be fully validated.

Designed to be:
- Lightweight
- Reproducible
- Easy to integrate into existing GIS workflows


## Fixing Polygon Holes (optional)

Interior holes ("donut" polygons) are a common reason a plot boundary fails TRACT validation. The plugin detects them and, when any are found, asks **once per run** how to handle the whole file:

| Choice | What it does | Effect on plot area |
|--------|--------------|---------------------|
| **Fill holes** | Removes the interior ring so the polygon becomes solid | **Grows** by the area of the hole |
| **Cut holes** | Opens each hole with a thin slit to the nearest point on the outer boundary | **Preserved**, apart from the negligible slit |
| **Leave as-is** | Keeps the hole and flags the feature as `NEEDS_FIX` | Unchanged |

Because Fill and Cut both rewrite the boundary you supplied, choosing either one brings up a confirmation step:

> Filling holes alters the original plot boundary. You are responsible for verifying that the result accurately represents the plot, and for retaining the source data.

Choosing **Cancel** there leaves every hole untouched for that run, and the affected features are flagged as `NEEDS_FIX` instead. Cancel is the default, so holes are never altered without a deliberate confirmation.

Details worth knowing:

- The choice applies to **every holed polygon in that run** — it is not asked per feature.
- Holes are fixed **before** the TRACT geometry checks, the minimum-area check and hole detection run, so a feature whose only problem was a hole is re-evaluated and comes out `READY`.
- If a hole cannot be resolved — or if the fix would be lost to the six-decimal coordinate precision — the original geometry is kept and the feature is flagged, rather than written out mangled.
- Cutting only ever removes the sliver of area taken by the slit — it never adds area, unlike filling.
- The summary report shows how many holed features were fixed and how many were left flagged.


## Output Files

The plugin produces up to three outputs (the third is opt-in); a fourth option splits the first output into several files:

1. GeoJSON file structured according to the TRACT geolocation template

This file contains:

- Standardized attributes (NodeID, PlotID)
- X/Y coordinates truncated to six decimal places, with any Z values preserved
- Reprojected geometries (EPSG:4326)
- Geometry fixes applied where possible, including optional hole filling / cutting

Depending on the detected issues, the output may contain:
- A fully valid dataset ready for upload, or
- A dataset where some features still require manual correction.

Features that could not be automatically repaired may be skipped or flagged during validation.

2. Validation report

A CSV validation report summarizing geometry checks and fixes applied during processing.

The report includes:
- Feature identifiers
- NodeID and PlotID values
- Validation status (Warning or Error)
- Issue type
- Descriptive messages explaining detected issues or applied repairs — including approximate latitude/longitude of boundary self-intersections when detected, so problem locations can be jumped to directly in QGIS

This report helps users quickly identify and correct problematic geometries before submitting data.

3. Master Data XLSX file (optional)

When "Generate Master Data file" is enabled in the dialog, the plugin also writes a populated TRACT Master Data template alongside the GeoJSON, with the filename `<basename>_master_data_farms.xlsx` or `<basename>_master_data_farmer_groups.xlsx` depending on the selected type.

The user picks:
- Type: **Farms** or **Farmer Groups**
- Country: a single value applied to every row (selected from TRACT's published country list)

The plugin populates one row per unique NodeID, with the name and Node_ID fields both set to the NodeID, leaving all other template columns untouched. The output preserves the TRACT template structure — all sheets, branding and headers — so it can be uploaded to TRACT without any further manual editing. Note that the country drop-down list itself is not carried into the generated file; the selected country is written directly into every row instead, so the drop-down is not needed.

### Split output (optional)

When "Split clean output into multiple files" is enabled, the plugin divides the clean GeoJSON into **2–10** smaller sibling files so each one uploads to TRACT under its size limit. Files are named by inserting a hyphen-index before the extension:

```
plots.geojson  →  plots-1.geojson, plots-2.geojson, plots-3.geojson
```

Splitting guarantees:

- **NodeIDs are never divided** — every feature sharing a NodeID stays together in exactly one file (an indivisible group).
- **Balanced sizes** — feature counts are balanced across the files (subject to the NodeID constraint) so the files are of similar size.
- **Faithful subsets** — each split file is an exact byte-subset of the combined output (same header, CRS, and coordinates); together they contain every feature exactly once.

You cannot request more files than there are unique NodeIDs — a NodeID cannot be split across files. If you do, the plugin shows an error stating the maximum and leaves the combined output untouched so you can reduce the count and run again. On a successful split, the combined file is replaced by the split files, which are each auto-loaded into QGIS. The Master Data XLSX and validation report are always single files and are unaffected by splitting.


## Typical Use Cases

- Preparing plot boundaries for ingestion into the TRACT platform
- Producing a matched pair of geolocation GeoJSON + Master Data XLSX for one-step TRACT upload
- Splitting a large geolocation dataset into several smaller files so each uploads to TRACT under its size limit
- Adapting customer-provided geolocation data to the TRACT GeoJSON template
- Resolving "donut" polygons with interior holes that TRACT would otherwise reject
- Validating and cleaning polygons prior to deforestation analysis
- Pre-checking geolocation data for EUDR-related due diligence workflows
- Identifying geometry issues that could affect land-use change or forest-loss assessments
- General-purpose polygon validation for sustainability and environmental monitoring applications




## Installation

### Option 1: QGIS Plugin Repository (not ready yet)

Once published, the plugin will be available directly from the QGIS Plugin Repository.

Steps:
1. Open QGIS
2. Go to **Plugins → Manage and Install Plugins**
3. Search for **TRACT Geolocation Formatter**
4. Click **Install**


### Option 2: Manual Installation (Development)

1. Clone or download this repository:

   git clone https://github.com/tract-eco/tract-geolocation-formatter.git

2. Copy the plugin folder (tract_geolocation_formatter) into your local QGIS plugins directory:

   macOS  
   ~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/

   Linux  
   ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/

   Windows  
   %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\

3. Restart QGIS.

4. Enable the plugin:
   - Open QGIS
   - Go to Plugins → Manage and Install Plugins
   - Enable TRACT Geolocation Formatter



## Development

This repository is structured as a development project, plus a deployable QGIS plugin folder.

- Repo root: development tooling (`pyproject.toml`, `poetry.lock`, tests, etc.)
- Plugin folder: `tract_geolocation_formatter/` (contains `metadata.txt`, `__init__.py`, plugin code)

### Prerequisites

- QGIS 3.x or QGIS 4 (with its bundled Python — the plugin runs on both)
- Python 3 (for development tooling; the exact version should match `pyproject.toml`)
- Poetry

### Setup (Poetry)

Clone the repository and install development dependencies:

```bash
git clone <REPO_URL>
cd tract-geolocation-formatter
poetry install
```


## License

This project is licensed under Apache 2.0. You are free to use, modify, and distribute this software in accordance with the license terms of Apache 2.0. Contributions to this repository are subject to a separate Contributor License Agreement.
