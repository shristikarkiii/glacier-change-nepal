"""Step 3 - map clean ice with NDSI and measure area change.

For every glacier and epoch:

    NDSI = (green - SWIR) / (green + SWIR)

and a pixel is clean glacier ice where NDSI >= 0.40 and NIR reflectance is
above a floor that rejects water and deep shadow. The classification is then
confined to a fixed analysis domain - the RGI outline grown by 500 m, the
same domain in every epoch - and reduced to the connected body that overlaps
the inventory outline, so detached snow patches do not enter the total.

Two things this deliberately does *not* claim:

* NDSI maps *clean* ice. Debris-covered ice has the spectral signature of
  rock and is invisible to any snow index, so on a debris-covered glacier the
  mapped area is the clean-ice part, not the whole glacier.
* A single scene carries seasonal snow that no index can separate from
  glacier ice. Every scene here is mid-October for that reason, and the
  residual is part of why an area carries an uncertainty.

Writes per-epoch masks to ``data/masks/`` and the results table to
``outputs/tables/``.

    python src/delineate.py
"""

from __future__ import annotations

import csv
import json

import numpy as np
import rasterio

import config
import geo

MASKS = config.DATA / "masks"
MASKS.mkdir(parents=True, exist_ok=True)

RESULTS = config.TABLES / "glacier_area_change.csv"
SUMMARY = config.TABLES / "summary.json"

COLUMNS = [
    ("glacier", "Glacier"),
    ("epoch", "Epoch"),
    ("date", "Acquired"),
    ("sensor", "Sensor"),
    ("clean_ice_km2", "Clean ice (km2)"),
    ("uncertainty_km2", "Uncertainty (+/- km2)"),
    ("volume_km3", "Volume (km3)"),
    ("volume_uncertainty_km3", "Volume uncertainty (+/- km3)"),
    ("change_from_first_km2", "Change vs first epoch (km2)"),
    ("change_from_first_pct", "Change vs first epoch (%)"),
]


def ndsi(green: np.ndarray, swir: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return (green - swir) / (green + swir)


def volume_km3(area_km2: float) -> float:
    """Volume-area scaling (Bahr et al. 1997, 2015)."""
    return config.VAS_C * area_km2**config.VAS_GAMMA


def classify(key: str, epoch: str):
    with rasterio.open(config.stack_path(key, epoch)) as src:
        green, swir, nir = src.read(1), src.read(2), src.read(3)
        transform, shape, crs = src.transform, src.shape, src.crs
        tags = src.tags()

    outline = geo.reproject_geometry(geo.load_outline(key), crs)
    inventory = geo.rasterize(outline, shape, transform)
    domain = geo.analysis_domain(inventory, config.DOMAIN_BUFFER_M, config.PIXEL_M)

    index = ndsi(green, swir)
    valid = np.isfinite(index) & np.isfinite(nir)
    ice = valid & (index >= config.NDSI_THRESHOLD) & (nir >= config.NIR_MIN) & domain
    ice = geo.largest_component(ice, inventory)

    path = MASKS / f"{key}_{epoch}_ice.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype="uint8",
        crs=crs,
        transform=transform,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dst:
        dst.write(ice.astype("uint8"), 1)
        dst.update_tags(**tags, ndsi_threshold=config.NDSI_THRESHOLD, nir_min=config.NIR_MIN)

    return ice, inventory, domain


def main() -> None:
    rows = []
    summary = {}

    for key, spec in config.GLACIERS.items():
        attrs = geo.load_attributes(key)
        series = []
        for epoch, meta in config.EPOCHS.items():
            ice, inventory, _ = classify(key, epoch)
            area = geo.area_km2(ice)
            sigma = geo.area_uncertainty_km2(ice)
            series.append(
                {
                    "glacier": spec["label"],
                    "key": key,
                    "epoch": epoch,
                    "date": meta["date"],
                    "sensor": meta["sensor"],
                    "clean_ice_km2": round(area, 3),
                    "uncertainty_km2": round(sigma, 3),
                    "volume_km3": round(volume_km3(area), 4),
                    "volume_uncertainty_km3": round(
                        volume_km3(area) * config.VAS_REL_UNCERTAINTY, 4
                    ),
                }
            )

        first = series[0]["clean_ice_km2"]
        for row in series:
            row["change_from_first_km2"] = round(row["clean_ice_km2"] - first, 3)
            row["change_from_first_pct"] = round(100 * (row["clean_ice_km2"] - first) / first, 2)
        rows.extend(series)

        last = series[-1]
        combined_sigma = float(
            np.hypot(series[0]["uncertainty_km2"], last["uncertainty_km2"])
        )
        change = last["clean_ice_km2"] - first
        summary[key] = {
            "label": spec["label"],
            "district": spec["district"],
            "rgi_id": spec["rgi_id"],
            "rgi_area_km2": attrs["rgi_area_km2"],
            "debris_covered": spec["debris_covered"],
            "first_epoch": series[0]["epoch"],
            "last_epoch": last["epoch"],
            "clean_ice_first_km2": first,
            "clean_ice_last_km2": last["clean_ice_km2"],
            "change_km2": round(change, 3),
            "change_pct": round(100 * change / first, 2),
            "change_uncertainty_km2": round(combined_sigma, 3),
            "significant": bool(abs(change) > 2 * combined_sigma),
            "rate_km2_per_yr": round(change / (int(last["epoch"]) - int(series[0]["epoch"])), 4),
            "volume_first_km3": series[0]["volume_km3"],
            "volume_last_km3": last["volume_km3"],
            "volume_change_km3": round(last["volume_km3"] - series[0]["volume_km3"], 4),
            "clean_ice_fraction_of_rgi": round(
                last["clean_ice_km2"] / attrs["rgi_area_km2"], 3
            ),
        }

    with RESULTS.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[k for k, _ in COLUMNS], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"[ok  ] {RESULTS.relative_to(config.ROOT)}")
    print(f"[ok  ] {SUMMARY.relative_to(config.ROOT)}\n")
    for key, s in summary.items():
        flag = "significant" if s["significant"] else "NOT significant vs uncertainty"
        print(
            f"  {s['label']:22} {s['clean_ice_first_km2']:7.3f} -> {s['clean_ice_last_km2']:7.3f} km2  "
            f"{s['change_km2']:+7.3f} ({s['change_pct']:+6.2f}%)  +/-{s['change_uncertainty_km2']:.3f}  {flag}"
        )
        print(
            f"  {'':22} RGI total {s['rgi_area_km2']:.3f} km2  "
            f"clean-ice fraction {s['clean_ice_fraction_of_rgi']:.2f}"
        )


if __name__ == "__main__":
    main()
