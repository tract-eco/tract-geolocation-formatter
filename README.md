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
- Remove consecutive duplicate vertices
- Repair invalid geometries using makeValid
- Detect polygons containing interior holes
- Validate minimum polygon area requirements
- Automatically reproject geometries to EPSG:4326
- Identify intersecting or overlapping line segments
- Detect and flag common geometry issues before export
- Export ready-to-upload GeoJSON files for the TRACT platform
- Works with common GIS formats (GeoJSON, Shapefile, GeoPackage)

Designed to be:
- Lightweight
- Reproducible
- Easy to integrate into existing GIS workflows

## Output Files

The plugin produces two outputs:

1. Clean GeoJSON file

A TRACT-compatible GeoJSON file containing validated and standardized geometries ready for upload to the TRACT platform.

2. Validation report

A CSV validation report summarizing geometry checks and fixes applied during processing.

The report includes:
- Feature identifiers
- NodeID and PlotID values
- Validation status (Warning or Error)
- Issue type
- Descriptive messages explaining detected issues or applied repairs

This report helps users quickly identify and correct problematic geometries before submitting data.


## Typical Use Cases

- Preparing plot boundaries for ingestion into the TRACT platform
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

- QGIS 3.x (with its bundled Python)
- Python 3 (for development tooling; the exact version should match `pyproject.toml`)
- Poetry

### Setup (Poetry)

Clone the repository and install development dependencies:

```bash
git clone <REPO_URL>
cd tract-geolocation-formatter
poetry install
