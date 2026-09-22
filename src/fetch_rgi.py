"""Step 1 - pull the two glacier outlines out of the Randolph Glacier Inventory.

RGI is only distributed as one 421 MB global archive, and inside it sits a
15 MB regional zip holding a shapefile. Downloading the lot to read two
polygons is wasteful, so this walks the outer zip's central directory over
HTTP range requests and pulls just the South Asia East member.

Writes ``data/<key>_rgi.geojson`` for each glacier plus the inventory
attributes used later for validation.

    python src/fetch_rgi.py
"""

from __future__ import annotations

import io
import json
import struct
import urllib.request
import zipfile
import zlib

import shapefile

import config

RGI_ARCHIVE = "https://cluster.klima.uni-bremen.de/~oggm/rgi/rgi62.zip"
REGION_MEMBER = "15_rgi62_SouthAsiaEast.zip"
SHP_STEM = "15_rgi62_SouthAsiaEast"


def _range(url: str, start: int, end: int) -> bytes:
    request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
    return urllib.request.urlopen(request, timeout=120).read()


def _content_length(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD")
    return int(urllib.request.urlopen(request, timeout=60).headers["Content-Length"])


def _central_directory(url: str) -> list[tuple]:
    """(name, compression, compressed size, uncompressed size, header offset)."""
    size = _content_length(url)
    tail = _range(url, max(0, size - 66_000), size - 1)
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise RuntimeError("no zip end-of-central-directory found")
    cd_size, cd_offset = struct.unpack("<II", tail[eocd + 12 : eocd + 20])
    blob = _range(url, cd_offset, cd_offset + cd_size - 1)

    entries: list[tuple] = []
    pos = 0
    while pos < len(blob) and blob[pos : pos + 4] == b"PK\x01\x02":
        name_len, extra_len, comment_len = struct.unpack("<HHH", blob[pos + 28 : pos + 34])
        compression = struct.unpack("<H", blob[pos + 10 : pos + 12])[0]
        comp_size, raw_size = struct.unpack("<II", blob[pos + 20 : pos + 28])
        offset = struct.unpack("<I", blob[pos + 42 : pos + 46])[0]
        name = blob[pos + 46 : pos + 46 + name_len].decode()
        entries.append((name, compression, comp_size, raw_size, offset))
        pos += 46 + name_len + extra_len + comment_len
    return entries


def fetch_region_zip() -> bytes:
    local = config.RGI_DIR / REGION_MEMBER
    if local.exists():
        print(f"[skip] {REGION_MEMBER} already present")
        return local.read_bytes()

    entry = next(
        (e for e in _central_directory(RGI_ARCHIVE) if e[0].endswith(REGION_MEMBER)), None
    )
    if entry is None:
        raise RuntimeError(f"{REGION_MEMBER} not found in {RGI_ARCHIVE}")
    _, compression, comp_size, _, offset = entry

    header = _range(RGI_ARCHIVE, offset, offset + 29)
    name_len, extra_len = struct.unpack("<HH", header[26:30])
    start = offset + 30 + name_len + extra_len

    print(f"[get ] {REGION_MEMBER} ({comp_size / 1e6:.1f} MB of a {_content_length(RGI_ARCHIVE) / 1e6:.0f} MB archive)")
    payload = _range(RGI_ARCHIVE, start, start + comp_size - 1)
    data = zlib.decompress(payload, -15) if compression == 8 else payload
    local.write_bytes(data)
    return data


def extract_shapefile(region_zip: bytes) -> None:
    if (config.RGI_DIR / f"{SHP_STEM}.shp").exists():
        print(f"[skip] {SHP_STEM}.shp already extracted")
        return
    with zipfile.ZipFile(io.BytesIO(region_zip)) as archive:
        archive.extractall(config.RGI_DIR)
    print(f"[ok  ] {SHP_STEM}.shp extracted")


def export_outlines() -> None:
    reader = shapefile.Reader(str(config.RGI_DIR / SHP_STEM))
    wanted = {spec["rgi_id"]: key for key, spec in config.GLACIERS.items()}
    attributes = {}

    for index, record in enumerate(reader.records()):
        fields = record.as_dict()
        key = wanted.get(fields["RGIId"])
        if key is None:
            continue
        geometry = reader.shape(index).__geo_interface__
        feature = {
            "type": "Feature",
            "properties": {
                "key": key,
                "label": config.GLACIERS[key]["label"],
                "rgi_id": fields["RGIId"],
                "rgi_area_km2": fields["Area"],
                "zmin_m": fields["Zmin"],
                "zmax_m": fields["Zmax"],
                "zmed_m": fields["Zmed"],
                "slope_deg": fields["Slope"],
                "aspect_deg": fields["Aspect"],
                "length_m": fields["Lmax"],
            },
            "geometry": geometry,
        }
        path = config.outline_path(key)
        path.write_text(
            json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8"
        )
        attributes[key] = feature["properties"]
        print(
            f"[ok  ] {path.name}  {fields['RGIId']}  "
            f"{fields['Area']} km2  {fields['Zmin']}-{fields['Zmax']} m"
        )

    missing = set(config.GLACIERS) - set(attributes)
    if missing:
        raise SystemExit(f"[fail] no RGI outline found for: {', '.join(sorted(missing))}")
    (config.DATA / "rgi_attributes.json").write_text(
        json.dumps(attributes, indent=2), encoding="utf-8"
    )


def main() -> None:
    extract_shapefile(fetch_region_zip())
    export_outlines()


if __name__ == "__main__":
    main()
