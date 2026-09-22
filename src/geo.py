"""Geometry, masking and area helpers.

rasterio bundles GDAL, which covers the raster I/O, the remote reads, the
coordinate transforms and the polygon rasterisation, so the project needs
neither geopandas nor shapely.
"""

from __future__ import annotations

import json

import numpy as np
import rasterio.features
import rasterio.warp
from scipy import ndimage

import config


def load_outline(key: str) -> dict:
    """The RGI glacier polygon as a GeoJSON geometry in EPSG:4326."""
    with config.outline_path(key).open(encoding="utf-8") as fh:
        return json.load(fh)["features"][0]["geometry"]


def load_attributes(key: str) -> dict:
    with (config.DATA / "rgi_attributes.json").open(encoding="utf-8") as fh:
        return json.load(fh)[key]


def reproject_geometry(geometry: dict, dst_crs) -> dict:
    return rasterio.warp.transform_geom("EPSG:4326", dst_crs, geometry)


def geometry_bounds(geometry: dict) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []

    def walk(node) -> None:
        if isinstance(node[0], (int, float)):
            xs.append(node[0])
            ys.append(node[1])
        else:
            for child in node:
                walk(child)

    walk(geometry["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def padded_bounds(geometry: dict, pad: float):
    west, south, east, north = geometry_bounds(geometry)
    return west - pad, south - pad, east + pad, north + pad


def rasterize(geometry: dict, shape, transform) -> np.ndarray:
    """Boolean array, True where a pixel centre falls inside the polygon."""
    return rasterio.features.geometry_mask(
        [geometry], out_shape=shape, transform=transform, invert=True
    )


def disk(radius_px: int) -> np.ndarray:
    r = int(radius_px)
    y, x = np.ogrid[-r : r + 1, -r : r + 1]
    return (x * x + y * y) <= r * r


def analysis_domain(outline_mask: np.ndarray, buffer_m: float, pixel_m: float) -> np.ndarray:
    """The outline grown by a circular buffer.

    Change detection needs a domain that is fixed across epochs and a little
    larger than the glacier's present outline, so an epoch when the glacier
    was bigger is not silently clipped at its own margin.
    """
    radius = int(round(buffer_m / pixel_m))
    if radius < 1:
        return outline_mask
    return ndimage.binary_dilation(outline_mask, structure=disk(radius))


def largest_component(mask: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """The connected blob of ``mask`` that overlaps ``seed`` most.

    Keeps the glacier body and drops detached snow patches inside the domain.
    """
    labels, count = ndimage.label(mask)
    if count == 0:
        return np.zeros_like(mask, dtype=bool)
    overlaps = ndimage.sum(seed, labels, index=np.arange(1, count + 1))
    if overlaps.max() == 0:
        sizes = ndimage.sum(mask, labels, index=np.arange(1, count + 1))
        return labels == (int(np.argmax(sizes)) + 1)
    return labels == (int(np.argmax(overlaps)) + 1)


def perimeter_px(mask: np.ndarray) -> int:
    """Count of boundary pixels - the edge the area uncertainty rides on."""
    eroded = ndimage.binary_erosion(mask, structure=np.ones((3, 3), bool), border_value=0)
    return int((mask & ~eroded).sum())


def area_km2(mask: np.ndarray, pixel_m: float = config.PIXEL_M) -> float:
    return float(mask.sum()) * pixel_m * pixel_m / 1e6


def area_uncertainty_km2(mask: np.ndarray, pixel_m: float = config.PIXEL_M) -> float:
    """Half-pixel positional error applied along the mapped margin.

    The standard treatment for a pixel-based glacier outline: each boundary
    pixel can fall either side of the true margin by up to half its width,
    and those errors are assumed independent, so they add in quadrature.
    """
    n_edge = perimeter_px(mask)
    return float(np.sqrt(n_edge) * 0.5 * pixel_m * pixel_m / 1e6)
