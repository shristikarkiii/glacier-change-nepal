"""Step 2 - clip the Landsat scenes and the SRTM DEM to the two glaciers.

Each Landsat scene is a ~7900 x 7900 px tile on public storage. Rather than
download four of them, GDAL's /vsicurl driver reads only the window covering
each glacier and this writes a small three-band stack per glacier per epoch:

    band 1  green    top-of-atmosphere reflectance
    band 2  swir     top-of-atmosphere reflectance
    band 3  nir      top-of-atmosphere reflectance

Digital numbers are converted with the scene's own rescaling coefficients and
corrected for solar elevation, which is what makes an index comparable across
sensors and across four decades.

    python src/fetch_imagery.py [--force]
"""

from __future__ import annotations

import argparse
import gzip
import re
import urllib.request

import numpy as np
import rasterio
from rasterio.windows import from_bounds

import config
import geo

GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    GDAL_HTTP_MULTIPLEX="YES",
    GDAL_HTTP_VERSION="2",
    VSI_CACHE="TRUE",
    VSI_CACHE_SIZE=100_000_000,
)

STACK_BANDS = ("green", "swir", "nir")


def read_mtl(epoch: str) -> dict[str, float]:
    """Radiometric rescaling coefficients and sun elevation for one scene."""
    text = urllib.request.urlopen(config.scene_mtl_url(epoch), timeout=120).read().decode(
        "utf-8", "replace"
    )
    values = {}
    for key, raw in re.findall(r"(\w+)\s*=\s*([-\d.E+]+)\s*\n", text):
        try:
            values[key] = float(raw)
        except ValueError:
            continue
    return values


def to_reflectance(dn: np.ndarray, band_code: str, mtl: dict[str, float]) -> np.ndarray:
    """DN -> top-of-atmosphere reflectance, corrected for solar elevation."""
    n = band_code.lstrip("B")
    mult = mtl[f"REFLECTANCE_MULT_BAND_{n}"]
    add = mtl[f"REFLECTANCE_ADD_BAND_{n}"]
    sun = np.deg2rad(mtl["SUN_ELEVATION"])
    reflectance = (dn.astype("float32") * mult + add) / np.sin(sun)
    # DN 0 is scene fill, not a dark surface.
    return np.where(dn == 0, np.nan, reflectance).astype("float32")


def clip_epoch(key: str, epoch: str, force: bool) -> None:
    dest = config.stack_path(key, epoch)
    if dest.exists() and not force:
        print(f"[skip] {dest.name}")
        return

    meta = config.EPOCHS[epoch]
    codes = config.BANDS[meta["sensor"]]
    mtl = read_mtl(epoch)
    outline = geo.load_outline(key)

    stack = []
    profile = None
    for band in STACK_BANDS:
        url = "/vsicurl/" + config.scene_band_url(epoch, band)
        with rasterio.open(url) as src:
            if profile is None:
                utm_outline = geo.reproject_geometry(outline, src.crs)
                bounds = geo.padded_bounds(utm_outline, config.WINDOW_PAD_M)
                window = from_bounds(*bounds, src.transform).round_lengths().round_offsets()
            data = src.read(1, window=window)
            if profile is None:
                profile = src.profile | {
                    "count": len(STACK_BANDS),
                    "dtype": "float32",
                    "height": data.shape[0],
                    "width": data.shape[1],
                    "transform": src.window_transform(window),
                    "compress": "deflate",
                    "predictor": 3,
                    "tiled": True,
                    "blockxsize": 256,
                    "blockysize": 256,
                    "nodata": float("nan"),
                    "driver": "GTiff",
                }
        stack.append(to_reflectance(data, codes[band], mtl))

    with rasterio.open(dest, "w", **profile) as dst:
        for i, (band, array) in enumerate(zip(STACK_BANDS, stack), start=1):
            dst.write(array, i)
            dst.set_band_description(i, band)
        dst.update_tags(
            sensor=meta["sensor"],
            acquired=meta["date"],
            scene=meta["prefix"].rsplit("/", 1)[-1],
            cloud_pct=meta["cloud_pct"],
            sun_elevation=mtl["SUN_ELEVATION"],
            product="top-of-atmosphere reflectance",
        )
    print(
        f"[ok  ] {dest.name}  {profile['width']}x{profile['height']} px  "
        f"{meta['sensor']} {meta['date']}  {dest.stat().st_size / 1e6:.2f} MB"
    )


def fetch_dem(force: bool) -> None:
    for tile in config.SRTM_TILES:
        dest = config.DEM_DIR / f"{tile}.hgt"
        if dest.exists() and not force:
            print(f"[skip] {dest.name}")
            continue
        url = config.SRTM_URL.format(ns=tile[:3], tile=tile)
        print(f"[get ] {url}")
        with urllib.request.urlopen(url, timeout=300) as resp:
            dest.write_bytes(gzip.decompress(resp.read()))
        print(f"[ok  ] {dest.name}  {dest.stat().st_size / 1e6:.1f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    fetch_dem(args.force)
    with rasterio.Env(**GDAL_ENV):
        for key in config.GLACIERS:
            for epoch in config.EPOCHS:
                clip_epoch(key, epoch, args.force)


if __name__ == "__main__":
    main()
