"""Read small windows of FAO WaPOR's public annual COGs at pinned revisions."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from math import ceil, floor
from pathlib import Path
from urllib.request import Request, urlopen

import rasterio
from rasterio.windows import Window, from_bounds

ROOT = Path(__file__).resolve().parent
BUCKET = "https://storage.googleapis.com/fao-gismgr-wapor-3-data/DATA/WAPOR-3/MAPSET"
PRODUCTS = {"AETI": ("mm/year", 0.1), "GBWP": ("kg/m³", 0.001)}
REVISIONS = {
    (2022, "L1", "AETI"): "1778402974569101",
    (2022, "L2", "AETI"): "1778648216114476",
    (2022, "L1", "GBWP"): "1778402957858245",
    (2022, "L2", "GBWP"): "1778651290790042",
    (2023, "L1", "AETI"): "1778403019327541",
    (2023, "L2", "AETI"): "1778610156987195",
    (2023, "L1", "GBWP"): "1778402982873273",
    (2023, "L2", "GBWP"): "1778611389469021",
}
BOUNDS = (-6.322, 34.838, -6.106, 34.956)


def enclosing_window(bounds, transform):
    requested = from_bounds(*bounds, transform)
    left, top = floor(requested.col_off), floor(requested.row_off)
    right = ceil(requested.col_off + requested.width)
    bottom = ceil(requested.row_off + requested.height)
    return Window(left, top, right - left, bottom - top)


def download(key, revision, out):
    year, level, indicator = key
    mapset = f"{level}-{indicator}-A"
    code = f"WAPOR-3.{mapset}.{year}"
    url = f"{BUCKET}/{mapset}/{code}.tif?generation={revision}"
    request = Request(url, headers={"Range": "bytes=0-1023"})
    with urlopen(request, timeout=30) as response:
        if response.status != 206 or response.headers.get("x-goog-generation") != revision:
            raise ValueError(f"Version and ranged access could not be verified for {code}")
        object_size = int(response.headers["content-range"].rsplit("/", 1)[1])
    unit, scale = PRODUCTS[indicator]
    target = out / f"{code}.tif"
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_CONNECTTIMEOUT="10",
                      GDAL_HTTP_TIMEOUT="55", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        with rasterio.open(f"/vsicurl/{url}") as source:
            if (source.crs.to_epsg(), source.count, source.nodata, source.scales[0], source.offsets[0]) != (4326, 1, -9999, scale, 0):
                raise ValueError(f"Unexpected metadata for {code}")
            window = enclosing_window(BOUNDS, source.transform)
            if window.width > 300 or window.height > 300:
                raise ValueError(f"Unexpected grid resolution for {code}")
            pixel_data = source.read(1, window=window)
            profile = {"driver": "GTiff", "crs": source.crs, "transform": source.window_transform(window),
                       "width": window.width, "height": window.height, "nodata": source.nodata,
                       "count": 1, "dtype": pixel_data.dtype, "compress": "deflate"}
            temp = target.with_suffix(".part.tif")
            with rasterio.open(temp, "w", **profile) as subset:
                subset.write(pixel_data, 1)
                subset.scales = (scale,)
                subset.set_band_unit(1, unit)
                subset.update_tags(source=url)
            temp.replace(target)
    print(f"{code} {pixel_data.shape} generation={revision}", flush=True)
    return {"code": code, "year": year, "level": level, "indicator": indicator, "unit": unit, "scale": scale,
            "url": url, "generation": revision, "object_bytes": object_size, "file": target.name,
            "shape": list(pixel_data.shape), "sha256": sha256(target.read_bytes()).hexdigest()}


def main():
    out = ROOT / "data/raw"
    out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(download, key, rev, out) for key, rev in REVISIONS.items()]
        assets = [future.result() for future in futures]
    (out / "manifest.json").write_text(json.dumps(assets, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
