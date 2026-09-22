"""Study design, paths and constants.

Everything that defines *what* is measured lives here, so the choices are
auditable in one place rather than buried in the processing steps.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RGI_DIR = DATA / "rgi"
SCENES = DATA / "scenes"
DEM_DIR = DATA / "dem"
OUTPUTS = ROOT / "outputs"
MAPS = OUTPUTS / "maps"
TABLES = OUTPUTS / "tables"

for _d in (RGI_DIR, SCENES, DEM_DIR, MAPS, TABLES):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Glaciers
#
# Both are identified by their Randolph Glacier Inventory 6.0 ID rather than
# by a hand-drawn box, so the analysis domain is a published, citable outline
# that anyone can re-fetch. Rikha Samba is named in RGI; Ponkar is not, and
# was matched on position and form - see docs/glacier-identification.md.

GLACIERS = {
    "rikha_samba": {
        "label": "Rikha Samba Glacier",
        "rgi_id": "RGI60-15.04847",
        "district": "Mustang",
        "debris_covered": False,
    },
    "ponkar": {
        "label": "Ponkar Glacier",
        "rgi_id": "RGI60-15.04541",
        "district": "Manang",
        "debris_covered": True,
    },
}

# --------------------------------------------------------------------------
# Imagery
#
# One Landsat footprint - WRS-2 path 142, row 040 - covers both glaciers, so
# every epoch compares the two under identical acquisition conditions.
#
# Scene selection rule, applied in select_scenes.py and frozen here:
#   * acquisition in October or November (post-monsoon, end of the ablation
#     season) so seasonal snow is at its annual minimum. Mapping glaciers on a
#     winter scene is the single most common way to inflate their area;
#   * Tier 1 only (terrain-corrected, best geolocation);
#   * lowest available scene cloud cover;
#   * no Landsat 7 after 2003-05-31, when the scan line corrector failed.
# The four scenes below are all mid-October, cloud <= 3%.

WRS_PATH_ROW = ("142", "040")
GCS_LANDSAT = "https://storage.googleapis.com/gcp-public-data-landsat"

EPOCHS = {
    "1991": {
        "sensor": "LT05",
        "date": "1991-10-12",
        "prefix": "LT05/01/142/040/LT05_L1TP_142040_19911012_20170125_01_T1",
        "cloud_pct": 1.0,
    },
    "1999": {
        "sensor": "LE07",
        "date": "1999-10-10",
        "prefix": "LE07/01/142/040/LE07_L1TP_142040_19991010_20170216_01_T1",
        "cloud_pct": 3.0,
    },
    "2011": {
        "sensor": "LT05",
        "date": "2011-10-19",
        "prefix": "LT05/01/142/040/LT05_L1TP_142040_20111019_20161005_01_T1",
        "cloud_pct": 2.0,
    },
    "2021": {
        "sensor": "LC08",
        "date": "2021-10-14",
        "prefix": "LC08/01/142/040/LC08_L1TP_142040_20211014_20211019_01_T1",
        "cloud_pct": 1.5,
    },
}

# Band numbers per sensor. NDSI needs GREEN and SHORTWAVE INFRARED - not
# green and red. NIR is carried to screen water and deep shadow.
BANDS = {
    "LT05": {"green": "B2", "red": "B3", "nir": "B4", "swir": "B5"},  # TM
    "LE07": {"green": "B2", "red": "B3", "nir": "B4", "swir": "B5"},  # ETM+
    "LC08": {"green": "B3", "red": "B4", "nir": "B5", "swir": "B6"},  # OLI
}

PIXEL_M = 30.0

# --------------------------------------------------------------------------
# Classification thresholds

# NDSI = (green - swir) / (green + swir); >= 0.4 is the long-standing
# threshold for snow and ice (Dozier 1989; Hall et al. 1995).
NDSI_THRESHOLD = 0.40
# Water and deep shadow can also return a high NDSI. Requiring a minimum NIR
# reflectance removes both.
NIR_MIN = 0.11

# The analysis domain is the RGI outline itself. Growing it was tried first,
# to let an epoch when the glacier was larger show through, and rejected:
# both glaciers sit in connected ice, so a buffer of a few hundred metres
# bridges the divide onto neighbouring glaciers and inflates the total. With
# no buffer, the 1999 clean-ice area of Rikha Samba lands within 0.05% of the
# RGI inventory area for the same nominal date. See sensitivity.py - the
# absolute area depends on this choice, the relative change barely does.
DOMAIN_BUFFER_M = 0.0
SENSITIVITY_BUFFERS_M = (0.0, 100.0, 200.0, 300.0, 500.0)

# Padding around the outline when cutting the window out of the Landsat scene.
WINDOW_PAD_M = 1500.0

# --------------------------------------------------------------------------
# Volume

# Volume-area scaling, V = c * A**gamma, with V in km3 and A in km2
# (Bahr et al. 1997; Bahr, Pfeffer & Kaser 2015). This replaces multiplying
# area by a surface-elevation range, which does not estimate ice volume.
# Scaling carries roughly +/-30% uncertainty on an individual glacier and is
# reported as such.
VAS_C = 0.0348
VAS_GAMMA = 1.36
VAS_REL_UNCERTAINTY = 0.30

# --------------------------------------------------------------------------
# Terrain

SRTM_TILES = ("N28E083", "N28E084")
SRTM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/skadi/{ns}/{tile}.hgt.gz"

# --------------------------------------------------------------------------
# Published extents used for validation (area in km2, with the nominal date).

REFERENCE_EXTENTS = {
    "rikha_samba": [
        {"source": "RGI 6.0 (RGI60-15.04847)", "year": 2000, "area_km2": 6.504},
    ],
    "ponkar": [
        {"source": "RGI 6.0 (RGI60-15.04541)", "year": 2000, "area_km2": 31.267},
        {"source": "Thapa (2019)", "year": 2019, "area_km2": 28.509},
    ],
}

# The 2024 thesis figures this pipeline was written to re-derive, kept so the
# comparison is explicit rather than implied.
THESIS_AREAS = {
    "rikha_samba": {"1980s": 8.495, "1990s": 8.334, "2000s": 7.892, "2010s": 5.648},
    "ponkar": {"1980s": 49.225, "1990s": 29.752, "2000s": 29.356, "2010s": 28.509},
}


def scene_band_url(epoch: str, band: str) -> str:
    """Public URL of one Landsat band for one epoch."""
    meta = EPOCHS[epoch]
    scene_id = meta["prefix"].rsplit("/", 1)[-1]
    code = BANDS[meta["sensor"]][band]
    return f"{GCS_LANDSAT}/{meta['prefix']}/{scene_id}_{code}.TIF"


def scene_mtl_url(epoch: str) -> str:
    meta = EPOCHS[epoch]
    scene_id = meta["prefix"].rsplit("/", 1)[-1]
    return f"{GCS_LANDSAT}/{meta['prefix']}/{scene_id}_MTL.txt"


def outline_path(key: str) -> Path:
    return DATA / f"{key}_rgi.geojson"


def stack_path(key: str, epoch: str) -> Path:
    return SCENES / f"{key}_{epoch}.tif"
