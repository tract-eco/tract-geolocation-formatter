"""
Land cover test fixtures (SPEC-landcover-overlap), generated at test time with GDAL.

Nothing binary is committed: ``make_fixture(directory)`` writes small classified
GeoTIFFs and returns their paths together with a plots FeatureCollection whose
expected pixel counts are known exactly.

Main raster (``classes_4326.tif``): EPSG:4326, 20×20 pixels of 0.0001°, upper-left
corner (10.0, 50.0), Byte, nodata 0. Row r / column c covers
lon 10 + c·0.0001 … +0.0001, lat 50 − r·0.0001 … −0.0001.

    rows 0–4, all columns          80 (water)
    row 5, columns 0–9              0 (nodata)
    rows 10–14, columns 10–14      50 (built-up)
    everything else                10

Plots (index: name → expected counts on the main raster):

    0 lake      rows 0–3, cols 0–19            {80: 80}
    1 village   rows 10–14, cols 10–14         {50: 25}
    2 mixed     rows 2–7, cols 0–3             {80: 12, NODATA: 4, 10: 8}  → water 50 %
    3 outside   lon 20, lat 50                 {}                         → not assessed
    4 multi     rows 0–1 cols 15–19 + rows 12–13 cols 10–11   {80: 10, 50: 4}
    5 point     a Point feature (not a plot; must be skipped)

Variants: ``three_band`` (band 1 all 10, band 2 = 7 on the water rows, band 3 = 7 on the
village block), ``coarse`` (0.001° pixels, all 80), ``utm`` (EPSG:32632, 40×40 pixels of
10 m, left half 80, right half 10) and ``outside`` (same as main, moved to lon 30).
"""

import os

from osgeo import gdal, osr

ORIGIN_X = 10.0
ORIGIN_Y = 50.0
PIXEL = 0.0001
SIZE = 20

UTM_EPSG = 32632
UTM_ORIGIN = (571600.0, 5538800.0)
UTM_PIXEL = 10.0
UTM_SIZE = 40

EXPECTED = {
    0: {80: 80},
    1: {50: 25},
    2: {80: 12, "NODATA": 4, 10: 8},
    3: {},
    4: {80: 10, 50: 4},
}


def _main_value(r, c):
    if r <= 4:
        return 80
    if r == 5 and c <= 9:
        return 0
    if 10 <= r <= 14 and 10 <= c <= 14:
        return 50
    return 10


def _srs_wkt(epsg):
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    return srs.ExportToWkt()


def _write(path, epsg, origin, pixel, width, height, bands, nodata=0):
    """``bands``: list of functions (r, c) → byte value."""
    ds = gdal.GetDriverByName("GTiff").Create(path, width, height, len(bands), gdal.GDT_Byte)
    ds.SetGeoTransform((origin[0], pixel, 0, origin[1], 0, -pixel))
    ds.SetProjection(_srs_wkt(epsg))
    for i, fn in enumerate(bands, start=1):
        data = bytes(fn(r, c) for r in range(height) for c in range(width))
        band = ds.GetRasterBand(i)
        band.WriteRaster(0, 0, width, height, data)
        if nodata is not None:
            band.SetNoDataValue(nodata)
    ds.FlushCache()
    ds = None
    return path


def _cell_rect(r0, r1, c0, c1):
    """Ring covering rows r0..r1 and columns c0..c1 (inclusive) of the main raster."""
    x0 = round(ORIGIN_X + c0 * PIXEL, 6)
    x1 = round(ORIGIN_X + (c1 + 1) * PIXEL, 6)
    y1 = round(ORIGIN_Y - r0 * PIXEL, 6)
    y0 = round(ORIGIN_Y - (r1 + 1) * PIXEL, 6)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def _feature(geometry, name):
    return {"type": "Feature", "properties": {"name": name}, "geometry": geometry}


def plots_feature_collection():
    return {
        "type": "FeatureCollection",
        "features": [
            _feature({"type": "Polygon", "coordinates": [_cell_rect(0, 3, 0, 19)]}, "lake"),
            _feature({"type": "Polygon", "coordinates": [_cell_rect(10, 14, 10, 14)]}, "village"),
            _feature({"type": "Polygon", "coordinates": [_cell_rect(2, 7, 0, 3)]}, "mixed"),
            _feature({"type": "Polygon", "coordinates": [[[20, 50], [20.001, 50], [20.001, 50.001],
                                                          [20, 50.001], [20, 50]]]}, "outside"),
            _feature({"type": "MultiPolygon", "coordinates": [[_cell_rect(0, 1, 15, 19)],
                                                              [_cell_rect(12, 13, 10, 11)]]}, "multi"),
            _feature({"type": "Point", "coordinates": [10.0005, 49.9995]}, "point"),
        ],
    }


def make_fixture(directory):
    """Write every raster variant into ``directory``; return a dict of paths + plots."""
    os.makedirs(directory, exist_ok=True)
    paths = {}
    paths["main"] = _write(
        os.path.join(directory, "classes_4326.tif"), 4326, (ORIGIN_X, ORIGIN_Y), PIXEL,
        SIZE, SIZE, [_main_value],
    )
    paths["three_band"] = _write(
        os.path.join(directory, "classes_3band.tif"), 4326, (ORIGIN_X, ORIGIN_Y), PIXEL,
        SIZE, SIZE,
        [
            lambda r, c: 10,
            lambda r, c: 7 if r <= 4 else 10,
            lambda r, c: 7 if (10 <= r <= 14 and 10 <= c <= 14) else 10,
        ],
        nodata=None,
    )
    paths["coarse"] = _write(
        os.path.join(directory, "classes_coarse.tif"), 4326, (ORIGIN_X, ORIGIN_Y), 0.001,
        2, 2, [lambda r, c: 80],
    )
    paths["outside"] = _write(
        os.path.join(directory, "classes_outside.tif"), 4326, (30.0, ORIGIN_Y), PIXEL,
        SIZE, SIZE, [_main_value],
    )
    paths["utm"] = _write(
        os.path.join(directory, "classes_utm.tif"), UTM_EPSG, UTM_ORIGIN, UTM_PIXEL,
        UTM_SIZE, UTM_SIZE, [lambda r, c: 80 if c < UTM_SIZE // 2 else 10],
    )
    paths["plots"] = plots_feature_collection()
    return paths


def utm_rect(x0, y0, x1, y1):
    """Closed ring in UTM metres (helper for the reprojection test)."""
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
