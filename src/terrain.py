"""Step 5 - terrain context and the elevation distribution of the mapped ice.

The SRTM tiles are warped onto each glacier's Landsat grid, then used for:

* **slope and aspect** within the inventory outline - the terrain setting the
  thesis described qualitatively, here as distributions;
* **hypsometry** - how the mapped clean ice is distributed with elevation in
  each epoch, and how its median elevation moves. A glacier that is retreating
  loses its lowest ice first, so the median elevation of the mapped ice rises.
  That is a far better retreat indicator than the minimum elevation of a
  scene window, which mostly tracks where the window was drawn.

    python src/terrain.py
"""

from __future__ import annotations

import csv
import json
import math

import numpy as np
import rasterio
import rasterio.warp
from rasterio.enums import Resampling

import config
import geo

HYPSOMETRY = config.TABLES / "hypsometry.csv"
TERRAIN = config.TABLES / "terrain.json"
BAND_M = 100  # elevation bin width


def dem_on_grid(shape, transform, crs) -> np.ndarray:
    """SRTM warped onto one glacier's Landsat grid."""
    destination = np.full(shape, np.nan, dtype="float32")
    for tile in config.SRTM_TILES:
        path = config.DEM_DIR / f"{tile}.hgt"
        with rasterio.open(path) as src:
            patch = np.full(shape, np.nan, dtype="float32")
            rasterio.warp.reproject(
                source=rasterio.band(src, 1),
                destination=patch,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=crs,
                resampling=Resampling.bilinear,
                src_nodata=-32768,
                dst_nodata=np.nan,
            )
        destination = np.where(np.isnan(destination), patch, destination)
    return destination


def slope_aspect(dem: np.ndarray, pixel_m: float):
    """Horn-style slope and aspect in degrees from a projected DEM."""
    dz_dy, dz_dx = np.gradient(dem, pixel_m)
    slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
    aspect = np.degrees(np.arctan2(-dz_dx, dz_dy)) % 360.0
    return slope, aspect


def compass_sector(aspect_deg: np.ndarray) -> np.ndarray:
    """Eight-point compass sector index for an aspect array."""
    return (np.floor(((aspect_deg + 22.5) % 360.0) / 45.0)).astype(int)


SECTORS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def main() -> None:
    hyps_rows = []
    report = {}

    for key, spec in config.GLACIERS.items():
        first_epoch = list(config.EPOCHS)[0]
        with rasterio.open(config.stack_path(key, first_epoch)) as src:
            shape, transform, crs = src.shape, src.transform, src.crs

        dem = dem_on_grid(shape, transform, crs)
        outline = geo.reproject_geometry(geo.load_outline(key), crs)
        inventory = geo.rasterize(outline, shape, transform)
        slope, aspect = slope_aspect(dem, config.PIXEL_M)

        inside = inventory & np.isfinite(dem)
        sectors = compass_sector(aspect)
        sector_share = {
            name: round(100 * float((inside & (sectors == i)).sum()) / float(inside.sum()), 1)
            for i, name in enumerate(SECTORS)
        }

        entry = {
            "label": spec["label"],
            "elevation_min_m": round(float(np.nanmin(dem[inside])), 0),
            "elevation_max_m": round(float(np.nanmax(dem[inside])), 0),
            "elevation_median_m": round(float(np.nanmedian(dem[inside])), 0),
            "slope_mean_deg": round(float(np.nanmean(slope[inside])), 1),
            "slope_median_deg": round(float(np.nanmedian(slope[inside])), 1),
            "aspect_sector_share_pct": sector_share,
            "dominant_aspect": max(sector_share, key=sector_share.get),
            "ice_median_elevation_m": {},
            "ice_min_elevation_m": {},
        }

        for epoch in config.EPOCHS:
            with rasterio.open(config.DATA / "masks" / f"{key}_{epoch}_ice.tif") as src:
                ice = src.read(1).astype(bool)
            valid = ice & np.isfinite(dem)
            elevations = dem[valid]
            entry["ice_median_elevation_m"][epoch] = round(float(np.median(elevations)), 0)
            # 5th percentile rather than the absolute minimum: one stray pixel
            # should not define the lower limit of a glacier.
            entry["ice_min_elevation_m"][epoch] = round(float(np.percentile(elevations, 5)), 0)

            lo = int(math.floor(elevations.min() / BAND_M) * BAND_M)
            hi = int(math.ceil(elevations.max() / BAND_M) * BAND_M)
            edges = np.arange(lo, hi + BAND_M, BAND_M)
            counts, _ = np.histogram(elevations, bins=edges)
            for band_low, count in zip(edges[:-1], counts):
                if count:
                    hyps_rows.append(
                        {
                            "glacier": spec["label"],
                            "epoch": epoch,
                            "elevation_band_m": int(band_low),
                            "area_km2": round(
                                count * config.PIXEL_M**2 / 1e6, 4
                            ),
                        }
                    )

        first, last = list(config.EPOCHS)[0], list(config.EPOCHS)[-1]
        entry["median_elevation_rise_m"] = round(
            entry["ice_median_elevation_m"][last] - entry["ice_median_elevation_m"][first], 0
        )
        entry["lower_limit_rise_m"] = round(
            entry["ice_min_elevation_m"][last] - entry["ice_min_elevation_m"][first], 0
        )
        report[key] = entry

    with HYPSOMETRY.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(hyps_rows[0]))
        writer.writeheader()
        writer.writerows(hyps_rows)
    TERRAIN.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[ok  ] {HYPSOMETRY.relative_to(config.ROOT)}")
    print(f"[ok  ] {TERRAIN.relative_to(config.ROOT)}\n")
    for entry in report.values():
        print(
            f"  {entry['label']:22} {entry['elevation_min_m']:.0f}-{entry['elevation_max_m']:.0f} m  "
            f"slope {entry['slope_mean_deg']}deg  dominant aspect {entry['dominant_aspect']}"
        )
        print(
            f"  {'':22} median ice elevation {entry['ice_median_elevation_m']}  "
            f"rise {entry['median_elevation_rise_m']:+.0f} m"
        )


if __name__ == "__main__":
    main()
