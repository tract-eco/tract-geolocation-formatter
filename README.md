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

Before validation and processing, the plugin **rounds all geometry coordinates to six decimal places**. This precision level aligns with the coordinate format used in the EU TRACES system, helping avoid geometry inconsistencies caused by excessive decimal precision.

The plugin works directly on existing QGIS layers and does **not** require advanced GIS scripting knowledge.


## Key Features

- Adapt geolocation layers to the **TRACT GeoJSON template**
- Add and validate required TRACT attributes, including:
  - Node ID
  - Plot ID
- Ensure consistent schema structure across all features
- Standardize coordinate precision by rounding geometries to six decimal places
- Validate polygon geometries (e.g. self-intersections, invalid rings)
- Report approximate latitude/longitude coordinates of detected boundary self-intersections so they can be located and fixed in QGIS
- Remove consecutive duplicate vertices
- Repair invalid geometries using makeValid
- Detect polygons containing interior holes
- Validate minimum polygon area requirements
- Automatically reproject geometries to EPSG:4326
- Identify intersecting or overlapping line segments
- Detect and flag common geometry issues before export
- Export ready-to-upload GeoJSON files for the TRACT platform
- Optionally generate a populated **Master Data XLSX** file (Farms or Farmer Groups) alongside the GeoJSON, with one row per unique NodeID and a user-selected country — ready for TRACT ingestion without manual template filling
- Scrollable dialog so OK / Cancel buttons stay reachable on small / laptop screens
- Compatible with both **QGIS 3.x** and **QGIS 4** from a single codebase
- Works with common GIS formats (GeoJSON, Shapefile, GeoPackage)

The plugin attempts to automatically fix some geometry issues where possible. However, certain issues may require manual correction by the user in QGIS before the dataset can be fully validated.

Designed to be:
- Lightweight
- Reproducible
- Easy to integrate into existing GIS workflows

## Output Files

The plugin produces up to three outputs (the third is opt-in):

1. GeoJSON file structured according to the TRACT geolocation template

This file contains:

- Standardized attributes (NodeID, PlotID)
- Rounded coordinate precision
- Reprojected geometries (EPSG:4326)
- Geometry fixes applied where possible

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

The plugin populates one row per unique NodeID, with the name and reference fields both set to the NodeID, leaving all other template columns untouched. The output preserves the complete TRACT template structure — all sheets, branding, headers, and validation rules — so it can be uploaded to TRACT without any further manual editing.


## Typical Use Cases

- Preparing plot boundaries for ingestion into the TRACT platform
- Producing a matched pair of geolocation GeoJSON + Master Data XLSX for one-step TRACT upload
- Adapting customer-provided geolocation data to the TRACT GeoJSON template
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
