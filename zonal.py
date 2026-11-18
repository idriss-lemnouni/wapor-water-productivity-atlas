"""Compute area, cell-centre and point estimates on two WaPOR native grids."""
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.transform import rowcol
import shapely
from shapely.geometry import mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parent
TO_AREA = Transformer.from_crs(4326, 6933, always_xy=True)
FROM_AREA = Transformer.from_crs(6933, 4326, always_xy=True)


def load_zones():
    features = json.loads((ROOT / "data/zones.geojson").read_bytes())["features"]
    zones = {}
    for feature in features:
        zone = shape(feature["geometry"])
        zone_id = feature["properties"]["id"]
        if zone.geom_type != "Polygon" or not zone.is_valid or zone.is_empty or zone_id in zones:
            raise ValueError(f"Invalid or duplicate zone {zone_id}")
        zones[zone_id] = feature["properties"]["name"], transform(TO_AREA.transform, zone)
    return zones


def projected_edges(affine, width, height):
    xs = affine.c + affine.a * np.arange(width + 1)
    ys = affine.f + affine.e * np.arange(height + 1)
    return TO_AREA.transform(xs, np.zeros(len(xs)))[0], TO_AREA.transform(np.zeros(len(ys)), ys)[1]


def aggregate(values, affine, zone, scale):
    height, width = values.shape
    xs, ys = projected_edges(affine, width, height)
    xmin, ymin, xmax, ymax = zone.bounds
    if not (xs[0] <= xmin < xmax <= xs[-1] and ys[-1] <= ymin < ymax <= ys[0]):
        raise ValueError("Zone extends beyond fetched raster window")
    cols = np.flatnonzero((xs[1:] > xmin) & (xs[:-1] < xmax))
    rows = np.flatnonzero((ys[:-1] > ymin) & (ys[1:] < ymax))
    c, r = np.meshgrid(cols, rows)
    r, c = r.ravel(), c.ravel()
    left, bottom, right, top = xs[c], ys[r + 1], xs[c + 1], ys[r]
    cells = shapely.box(left, bottom, right, top)
    area = shapely.area(shapely.intersection(zone, cells))
    data = values[r, c].filled(np.nan)
    valid = np.isfinite(data) & (data >= 0) & (area > 0)
    scaled = data[valid] * scale
    overlap = area[valid]
    cx, cy = (left + right) / 2, (bottom + top) / 2
    centres = shapely.intersects_xy(zone, cx[valid], cy[valid])
    centre = zone.centroid
    point = None
    if zone.covers(centre):
        cy, cx = rowcol(affine, *FROM_AREA.transform(centre.x, centre.y))
        candidate = values[cy, cx]
        if not np.ma.is_masked(candidate) and np.isfinite(candidate) and candidate >= 0:
            point = float(candidate * scale)
    metrics = {
        "valid_cells": int(valid.sum()),
        "coverage": min(1.0, float(overlap.sum() / zone.area)),
        "weighted": float(np.average(scaled, weights=overlap)) if len(scaled) else None,
        "cell_center": float(scaled[centres].mean()) if centres.any() else None,
        "centroid": point,
    }
    pixels = zip(left[valid].tolist(), bottom[valid].tolist(), right[valid].tolist(), top[valid].tolist(), scaled.tolist())
    return metrics, list(pixels)


def collect():
    zones = load_zones()
    raw = ROOT / "data/raw"
    metadata = json.loads((raw / "manifest.json").read_bytes())
    summaries, pixels = [], {}
    for asset in metadata:
        source = raw / asset["file"]
        if sha256(source.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError(f"Window fingerprint changed for {source.name}")
        with rasterio.open(source) as dataset:
            if dataset.crs.to_epsg() != 4326 or dataset.scales[0] != asset["scale"]:
                raise ValueError(f"Unexpected raster units or CRS for {source.name}")
            values = dataset.read(1, masked=True).astype(np.float64)
            for zone_id, (name, zone) in zones.items():
                metrics, cells = aggregate(values, dataset.transform, zone, asset["scale"])
                pixels[zone_id, asset["code"]] = cells
                summaries.append({
                    "zone": zone_id, "name": name, "area_km2": zone.area / 1e6,
                    **{field: asset[field] for field in ("code", "year", "level", "indicator", "unit", "generation")},
                    **metrics,
                })
    return zones, summaries, pixels


def zone_records(zones):
    return [(key, name, json.dumps(mapping(zone))) for key, (name, zone) in zones.items()]
