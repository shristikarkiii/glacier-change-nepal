"""Step 4 - sensitivity testing and comparison against published extents.

Two questions a reader is entitled to ask of any remote-sensing area, and
which the analysis has to answer before its numbers mean anything:

1. **How much does the answer depend on the choices?** The domain buffer and
   the NDSI threshold are both judgement calls. This re-runs the whole
   classification across a grid of both and reports the spread.
2. **Does it agree with anyone else?** The mapped areas are put beside the
   RGI inventory, the published extent for Ponkar, and the 2024 thesis
   figures this pipeline was written to re-derive.

    python src/validate.py
"""

from __future__ import annotations

import csv
import json

import numpy as np
import rasterio

import config
import geo
from delineate import ndsi

SENSITIVITY = config.TABLES / "sensitivity.csv"
COMPARISON = config.TABLES / "comparison_with_published.csv"
REPORT = config.TABLES / "validation.json"

NDSI_VARIANTS = (0.35, 0.40, 0.45)


def classify_with(key: str, epoch: str, buffer_m: float, threshold: float) -> float:
    with rasterio.open(config.stack_path(key, epoch)) as src:
        green, swir, nir = src.read(1), src.read(2), src.read(3)
        transform, shape, crs = src.transform, src.shape, src.crs

    outline = geo.reproject_geometry(geo.load_outline(key), crs)
    inventory = geo.rasterize(outline, shape, transform)
    domain = geo.analysis_domain(inventory, buffer_m, config.PIXEL_M)

    index = ndsi(green, swir)
    valid = np.isfinite(index) & np.isfinite(nir)
    ice = valid & (index >= threshold) & (nir >= config.NIR_MIN) & domain
    return geo.area_km2(geo.largest_component(ice, inventory))


def run_sensitivity() -> list[dict]:
    rows = []
    for key, spec in config.GLACIERS.items():
        for buffer_m in config.SENSITIVITY_BUFFERS_M:
            for threshold in NDSI_VARIANTS:
                areas = {
                    epoch: classify_with(key, epoch, buffer_m, threshold)
                    for epoch in config.EPOCHS
                }
                first, last = list(config.EPOCHS)[0], list(config.EPOCHS)[-1]
                rows.append(
                    {
                        "glacier": spec["label"],
                        "domain_buffer_m": int(buffer_m),
                        "ndsi_threshold": threshold,
                        **{f"area_{e}_km2": round(a, 3) for e, a in areas.items()},
                        "change_km2": round(areas[last] - areas[first], 3),
                        "change_pct": round(
                            100 * (areas[last] - areas[first]) / areas[first], 2
                        ),
                    }
                )
    with SENSITIVITY.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[ok  ] {SENSITIVITY.relative_to(config.ROOT)}  ({len(rows)} configurations)")
    return rows


def run_comparison(summary: dict) -> list[dict]:
    with (config.TABLES / "glacier_area_change.csv").open(encoding="utf-8") as fh:
        measured = list(csv.DictReader(fh))

    rows = []
    for key, spec in config.GLACIERS.items():
        ours = {
            r["epoch"]: float(r["clean_ice_km2"])
            for r in measured
            if r["glacier"] == spec["label"]
        }
        for ref in config.REFERENCE_EXTENTS[key]:
            nearest = min(ours, key=lambda e: abs(int(e) - ref["year"]))
            rows.append(
                {
                    "glacier": spec["label"],
                    "reference": ref["source"],
                    "reference_year": ref["year"],
                    "reference_area_km2": ref["area_km2"],
                    "this_study_epoch": nearest,
                    "this_study_km2": ours[nearest],
                    "difference_km2": round(ours[nearest] - ref["area_km2"], 3),
                    "difference_pct": round(
                        100 * (ours[nearest] - ref["area_km2"]) / ref["area_km2"], 2
                    ),
                    "note": (
                        "clean ice only; glacier is debris-covered"
                        if spec["debris_covered"]
                        else ""
                    ),
                }
            )
        thesis = config.THESIS_AREAS[key]
        first_t, last_t = thesis["1980s"], thesis["2010s"]
        rows.append(
            {
                "glacier": spec["label"],
                "reference": "Jha & Karki (2024) thesis, 1980s-2010s change",
                "reference_year": 2024,
                "reference_area_km2": round(last_t - first_t, 3),
                "this_study_epoch": "1991-2021",
                "this_study_km2": summary[key]["change_km2"],
                "difference_km2": round(
                    summary[key]["change_km2"] - (last_t - first_t), 3
                ),
                "difference_pct": round(
                    100 * (last_t - first_t) / first_t, 2
                ),
                "note": "reference column holds the thesis area CHANGE, not an extent",
            }
        )

    with COMPARISON.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[ok  ] {COMPARISON.relative_to(config.ROOT)}")
    return rows


def main() -> None:
    summary = json.loads((config.TABLES / "summary.json").read_text(encoding="utf-8"))
    sensitivity = run_sensitivity()
    run_comparison(summary)

    report = {}
    for key, spec in config.GLACIERS.items():
        subset = [r for r in sensitivity if r["glacier"] == spec["label"]]
        changes = [r["change_pct"] for r in subset]
        areas_last = [r[f"area_{list(config.EPOCHS)[-1]}_km2"] for r in subset]
        report[key] = {
            "label": spec["label"],
            "configurations": len(subset),
            "change_pct_min": min(changes),
            "change_pct_max": max(changes),
            "change_pct_median": round(float(np.median(changes)), 2),
            "area_2021_min_km2": min(areas_last),
            "area_2021_max_km2": max(areas_last),
            "all_configurations_show_loss": all(c < 0 for c in changes),
        }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[ok  ] {REPORT.relative_to(config.ROOT)}\n")

    for key, r in report.items():
        print(
            f"  {r['label']:22} change across {r['configurations']} configurations: "
            f"{r['change_pct_min']:+.2f}% to {r['change_pct_max']:+.2f}% "
            f"(median {r['change_pct_median']:+.2f}%)  "
            f"{'all show loss' if r['all_configurations_show_loss'] else 'SIGN NOT ROBUST'}"
        )


if __name__ == "__main__":
    main()
