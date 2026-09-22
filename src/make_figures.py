"""Step 6 - render the maps and charts.

Produces, for a light and a dark surface each:

* ``extent-<glacier>``    mapped clean ice in 1991 and 2021 over the terrain,
* ``area-change``         clean-ice area per epoch, one panel per glacier,
* ``method-comparison``   this study against the 2024 thesis and the
                          published inventory extents,
* ``debris-cover``        what NDSI can and cannot see on Ponkar,
* ``hypsometry``          the elevation distribution of the mapped ice.

    python src/make_figures.py
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict

import matplotlib
import numpy as np
import rasterio

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LightSource, LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Patch, Polygon as MplPolygon, Rectangle  # noqa: E402

import config  # noqa: E402
import geo  # noqa: E402
import terrain as terrain_mod  # noqa: E402
import viz_theme as vt  # noqa: E402

SOURCE_NOTE = (
    "Data: USGS/NASA Landsat 5 TM, 7 ETM+ and 8 OLI (30 m)  ·  SRTM 1-arcsec DEM  "
    "·  Outlines: Randolph Glacier Inventory 6.0"
)


def flat(colour: str) -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list("flat", [colour, colour])


def paint(ax, mask, colour, extent, zorder, alpha=1.0):
    ax.imshow(
        np.where(mask, 1.0, np.nan),
        extent=extent,
        cmap=flat(colour),
        interpolation="nearest",
        zorder=zorder,
        alpha=alpha,
    )


def rings(geometry: dict):
    polygons = (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )
    for polygon in polygons:
        for ring in polygon:
            yield np.asarray(ring)


def draw_outline(ax, geometry, colour, lw=1.2, ls="-", zorder=6):
    for ring in rings(geometry):
        ax.add_patch(
            MplPolygon(ring, closed=True, facecolor="none", edgecolor=colour,
                       linewidth=lw, linestyle=ls, zorder=zorder)
        )


def scale_bar(ax, extent, theme, km):
    west, east, south, north = extent
    metres = km * 1000.0
    x0 = west + (east - west) * 0.05
    y0 = south + (north - south) * 0.05
    height = (north - south) * 0.012
    for i in range(2):
        ax.add_patch(
            Rectangle((x0 + i * metres / 2, y0), metres / 2, height,
                      facecolor=theme.ink if i == 0 else theme.surface,
                      edgecolor=theme.ink, linewidth=0.7, zorder=8)
        )
    ax.text(x0 + metres / 2, y0 + height * 2.0, f"{km:g} km", ha="center", va="bottom",
            fontsize=7, color=theme.ink_secondary, zorder=8)


def north_arrow(ax, extent, theme):
    west, east, south, north = extent
    x = east - (east - west) * 0.06
    y = south + (north - south) * 0.05
    span = (north - south) * 0.07
    ax.annotate("", xy=(x, y + span), xytext=(x, y),
                arrowprops=dict(arrowstyle="-|>", color=theme.ink, linewidth=1.1,
                                mutation_scale=11), zorder=8)
    ax.text(x, y + span * 1.1, "N", ha="center", va="bottom", fontsize=8,
            color=theme.ink, fontweight="bold", zorder=8)


def map_frame(ax, extent, theme):
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_edgecolor(theme.axis)
        spine.set_linewidth(0.8)


def legend(ax, handles, theme, loc="upper right"):
    box = ax.legend(handles=handles, loc=loc, frameon=True, facecolor=theme.surface,
                    edgecolor=theme.axis, fontsize=7.5, labelcolor=theme.ink_secondary,
                    borderpad=0.6, labelspacing=0.5)
    box.get_frame().set_linewidth(0.8)


def titles(fig, theme, title, subtitle, note=SOURCE_NOTE):
    fig.text(0.015, 0.978, title, fontsize=13, fontweight="bold", color=theme.ink, va="top")
    fig.text(0.015, 0.928, subtitle, fontsize=8.5, color=theme.ink_secondary, va="top")
    fig.text(0.015, 0.016, note, fontsize=6.8, color=theme.ink_muted, va="bottom")


def save(fig, stem, theme):
    path = config.MAPS / f"{stem}{vt.suffix(theme)}.png"
    fig.savefig(path)
    plt.close(fig)
    print(f"[ok  ] {path.relative_to(config.ROOT)}")


# --------------------------------------------------------------------------


def load_layers(key: str):
    first = list(config.EPOCHS)[0]
    with rasterio.open(config.stack_path(key, first)) as src:
        shape, transform, crs = src.shape, src.transform, src.crs
        bounds = src.bounds
    dem = terrain_mod.dem_on_grid(shape, transform, crs)
    outline = geo.reproject_geometry(geo.load_outline(key), crs)
    inventory = geo.rasterize(outline, shape, transform)
    masks = {}
    for epoch in config.EPOCHS:
        with rasterio.open(config.DATA / "masks" / f"{key}_{epoch}_ice.tif") as src:
            masks[epoch] = src.read(1).astype(bool)
    extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
    return dem, outline, inventory, masks, extent


def hillshade(ax, dem, extent, theme):
    shaded = LightSource(azdeg=315, altdeg=45).hillshade(
        np.nan_to_num(dem, nan=float(np.nanmin(dem))), vert_exag=2.0,
        dx=config.PIXEL_M, dy=config.PIXEL_M
    )
    ax.imshow(shaded, extent=extent, cmap="gray", vmin=0, vmax=1, zorder=1,
              interpolation="bilinear", alpha=0.85 if theme.name == "light" else 0.55)


def fig_extent(key, theme, summary):
    spec = config.GLACIERS[key]
    dem, outline, inventory, masks, extent = load_layers(key)
    first, last = list(config.EPOCHS)[0], list(config.EPOCHS)[-1]

    width_km = (extent[1] - extent[0]) / 1000
    height_km = (extent[3] - extent[2]) / 1000
    fig, ax = plt.subplots(figsize=(8.0, max(5.4, 8.0 * height_km / width_km * 0.82)))
    fig.subplots_adjust(left=0.04, right=0.96, top=0.855, bottom=0.075)

    hillshade(ax, dem, extent, theme)
    paint(ax, masks[first], theme.series[0], extent, 3, alpha=0.95)
    paint(ax, masks[last] & masks[first], theme.series[2], extent, 4, alpha=0.95)
    paint(ax, masks[last] & ~masks[first], theme.series[1], extent, 5, alpha=0.95)
    draw_outline(ax, outline, theme.ink, lw=1.2, ls=(0, (4, 2)))

    map_frame(ax, extent, theme)
    scale_bar(ax, extent, theme, 2 if width_km < 12 else 5)
    north_arrow(ax, extent, theme)
    legend(ax, [
        Patch(facecolor=theme.series[2], label=f"Ice in both {first} and {last}"),
        Patch(facecolor=theme.series[0], label=f"Ice in {first} only  (lost)"),
        Patch(facecolor=theme.series[1], label=f"Ice in {last} only  (gained)"),
        Patch(facecolor="none", edgecolor=theme.ink, linestyle="--", label="RGI 6.0 outline"),
    ], theme, loc="upper left")

    s = summary[key]
    titles(fig, theme,
           f"{spec['label']}: {s['change_pct']:+.1f}% clean ice, {first}–{last}",
           f"{s['clean_ice_first_km2']:.2f} → {s['clean_ice_last_km2']:.2f} km² "
           f"(±{s['change_uncertainty_km2']:.2f} km²)  ·  {spec['district']} district, Nepal  "
           f"·  NDSI ≥ {config.NDSI_THRESHOLD} within the RGI outline")
    save(fig, f"extent-{key.replace('_', '-')}", theme)


def fig_area_change(theme, summary, rows):
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 4.3))
    fig.subplots_adjust(left=0.085, right=0.975, top=0.80, bottom=0.135, wspace=0.28)

    for ax, (key, spec) in zip(axes, config.GLACIERS.items()):
        series = [r for r in rows if r["glacier"] == spec["label"]]
        years = [int(r["epoch"]) for r in series]
        areas = [float(r["clean_ice_km2"]) for r in series]
        errors = [float(r["uncertainty_km2"]) for r in series]
        colour = theme.series[0] if key == "rikha_samba" else theme.series[1]

        ax.errorbar(years, areas, yerr=errors, color=colour, linewidth=2.0,
                    marker="o", markersize=6, markeredgecolor=theme.surface,
                    markeredgewidth=2.0, capsize=3, elinewidth=1.2, zorder=3)
        for x, y in ((years[0], areas[0]), (years[-1], areas[-1])):
            ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points",
                        xytext=(0, 11), ha="center", fontsize=8,
                        fontweight="bold", color=theme.ink, zorder=4)
        span = max(areas) - min(areas)
        ax.set_ylim(min(areas) - span * 0.9, max(areas) + span * 0.9)
        ax.set_xticks(years)
        ax.set_xlim(years[0] - 3, years[-1] + 3)
        ax.set_title(f"{spec['label']}   {summary[key]['change_pct']:+.1f}%",
                     fontsize=9.5, color=theme.ink, pad=8)
        ax.set_ylabel("Clean-ice area (km²)")
        ax.yaxis.grid(True, color=theme.grid, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        ax.tick_params(length=3, width=0.8, labelsize=8)

    titles(fig, theme, "Both glaciers lost clean ice, 1991–2021",
           "Mapped clean-ice area per epoch with ±0.5-pixel margin uncertainty  ·  "
           "each panel has its own scale; the two are never plotted on one axis")
    save(fig, "area-change", theme)


def fig_comparison(theme, summary, validation):
    fig, ax = plt.subplots(figsize=(8.4, 3.9))
    fig.subplots_adjust(left=0.235, right=0.965, top=0.745, bottom=0.175)

    labels, thesis_vals, ours, lo, hi = [], [], [], [], []
    for key, spec in config.GLACIERS.items():
        t = config.THESIS_AREAS[key]
        labels.append(spec["label"])
        thesis_vals.append(100 * (t["2010s"] - t["1980s"]) / t["1980s"])
        ours.append(summary[key]["change_pct"])
        lo.append(validation[key]["change_pct_min"])
        hi.append(validation[key]["change_pct_max"])

    y = np.arange(len(labels), dtype=float)
    h = 0.26
    ax.barh(y + h * 0.58, thesis_vals, height=h, color=theme.series[7], zorder=3)
    ax.barh(y - h * 0.58, ours, height=h, color=theme.series[0], zorder=3)

    for i in range(len(labels)):
        # Method-variant span, drawn over the bar it belongs to.
        ax.plot([lo[i], hi[i]], [y[i] - h * 0.58] * 2, color=theme.ink,
                linewidth=1.3, solid_capstyle="butt", zorder=5)
        for x in (lo[i], hi[i]):
            ax.plot([x, x], [y[i] - h * 0.58 - h * 0.22, y[i] - h * 0.58 + h * 0.22],
                    color=theme.ink, linewidth=1.3, zorder=5)
        # Labels sit outside the bar tip, in ink, so they read on any surface.
        ax.annotate(f"{thesis_vals[i]:+.1f}%", (thesis_vals[i], y[i] + h * 0.58),
                    textcoords="offset points", xytext=(-7, 0), ha="right", va="center",
                    fontsize=8.5, color=theme.ink, fontweight="bold", zorder=6)
        ax.annotate(f"{ours[i]:+.1f}%", (lo[i], y[i] - h * 0.58),
                    textcoords="offset points", xytext=(-7, 0), ha="right", va="center",
                    fontsize=8.5, color=theme.ink, fontweight="bold", zorder=6)

    ax.axvline(0, color=theme.axis, linewidth=1.0, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_ylim(len(labels) - 0.42, -0.85)
    ax.set_xlabel("Change in glacier area over the study period (%)")
    ax.set_xlim(-52, 4)
    ax.xaxis.grid(True, color=theme.grid, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=3, width=0.8, labelsize=8)
    legend(ax, [
        Patch(facecolor=theme.series[7], label="Jha & Karki (2024) thesis, 1980s–2010s"),
        Patch(facecolor=theme.series[0], label="This study, 1991–2021"),
        plt.Line2D([0], [0], color=theme.ink, linewidth=1.3,
                   label="This study, span of 15 method variants"),
    ], theme, loc="upper left")

    titles(fig, theme, "The thesis overstated both losses several-fold",
           "Bracket spans every combination of domain buffer and NDSI threshold tested  ·  "
           "all 30 variants agree on the sign and the order of magnitude",
           "Thesis figures: Jha & Karki (2024), Kathmandu University.  " + SOURCE_NOTE)
    save(fig, "method-comparison", theme)


def fig_debris(theme, summary):
    key = "ponkar"
    dem, outline, inventory, masks, extent = load_layers(key)
    last = list(config.EPOCHS)[-1]
    ice = masks[last]
    debris = inventory & ~ice

    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    fig.subplots_adjust(left=0.04, right=0.96, top=0.845, bottom=0.075)
    hillshade(ax, dem, extent, theme)
    paint(ax, ice, theme.series[0], extent, 3, alpha=0.95)
    paint(ax, debris, theme.series[3], extent, 4, alpha=0.95)
    draw_outline(ax, outline, theme.ink, lw=1.2, ls=(0, (4, 2)))

    map_frame(ax, extent, theme)
    scale_bar(ax, extent, theme, 5)
    north_arrow(ax, extent, theme)

    s = summary[key]
    inside_km2 = geo.area_km2(inventory)
    hidden = inside_km2 - s["clean_ice_last_km2"]
    legend(ax, [
        Patch(facecolor=theme.series[0],
              label=f"Clean ice mapped by NDSI   {s['clean_ice_last_km2']:.1f} km²"),
        Patch(facecolor=theme.series[3],
              label=f"Inside the outline, invisible to NDSI   {hidden:.1f} km²"),
        Patch(facecolor="none", edgecolor=theme.ink, linestyle="--", label="RGI 6.0 outline"),
    ], theme, loc="upper left")

    titles(fig, theme,
           f"A snow index cannot see {100 * hidden / inside_km2:.0f}% of Ponkar Glacier",
           "Debris-covered ice reflects like the rock that buries it, so NDSI classifies it as "
           "non-ice  ·  any NDSI area for this glacier is its clean-ice part, not its extent")
    save(fig, "debris-cover", theme)


def fig_hypsometry(theme):
    with (config.TABLES / "hypsometry.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    first, last = list(config.EPOCHS)[0], list(config.EPOCHS)[-1]

    fig, axes = plt.subplots(1, 2, figsize=(8.4, 4.6))
    fig.subplots_adjust(left=0.085, right=0.975, top=0.795, bottom=0.135, wspace=0.26)

    for ax, (key, spec) in zip(axes, config.GLACIERS.items()):
        data = defaultdict(dict)
        for r in rows:
            if r["glacier"] == spec["label"]:
                data[r["epoch"]][int(r["elevation_band_m"])] = float(r["area_km2"])
        bands = sorted(set(data[first]) | set(data[last]))
        # The two epochs coincide over most of the range, so the earlier one is
        # drawn heavier and underneath: where only one line shows, they agree.
        for epoch, colour, lw, z in (
            (first, theme.series[0], 3.2, 3), (last, theme.series[1], 1.6, 4)
        ):
            values = [data[epoch].get(b, 0.0) for b in bands]
            ax.step(values, bands, where="mid", color=colour, linewidth=lw, zorder=z,
                    label=epoch)
        ax.set_title(spec["label"], fontsize=9.5, color=theme.ink, pad=8)
        ax.set_xlabel("Clean-ice area per 100 m band (km²)")
        ax.set_ylabel("Elevation (m a.s.l.)")
        ax.xaxis.grid(True, color=theme.grid, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        ax.tick_params(length=3, width=0.8, labelsize=8)
        box = ax.legend(frameon=True, facecolor=theme.surface, edgecolor=theme.axis,
                        fontsize=7.5, labelcolor=theme.ink_secondary, loc="upper right")
        box.get_frame().set_linewidth(0.8)

    titles(fig, theme, "The ice that went was the lowest ice",
           f"Area–elevation distribution of mapped clean ice, {first} against {last}  "
           f"·  100 m elevation bands from the SRTM DEM")
    save(fig, "hypsometry", theme)


def main() -> None:
    summary = json.loads((config.TABLES / "summary.json").read_text(encoding="utf-8"))
    validation = json.loads((config.TABLES / "validation.json").read_text(encoding="utf-8"))
    with (config.TABLES / "glacier_area_change.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    for theme in vt.THEMES:
        with plt.rc_context(vt.rc(theme)):
            for key in config.GLACIERS:
                fig_extent(key, theme, summary)
            fig_area_change(theme, summary, rows)
            fig_comparison(theme, summary, validation)
            fig_debris(theme, summary)
            fig_hypsometry(theme)


if __name__ == "__main__":
    main()
