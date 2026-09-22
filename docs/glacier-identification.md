# Which glaciers these are

Both study glaciers are pinned to a Randolph Glacier Inventory 6.0 entry rather
than to a hand-drawn box, so the analysis domain is a published outline anyone
can re-fetch and check. One was straightforward; the other was not.

## Rikha Samba Glacier — `RGI60-15.04847`

Named in RGI, so there is nothing to argue about.

| | RGI 6.0 | This study (SRTM + Landsat) |
|---|---|---|
| Area | 6.504 km² | 6.507 km² (1999) |
| Elevation range | 5380–6513 m | 5375–6515 m |
| Mean slope | 16.2° | 17.3° |
| Aspect | 176° (S) | S (22.9% of pixels) |

Independently derived from a different DEM path and a different image, the
agreement is close enough to treat the outline as correctly matched.

## Ponkar Glacier — `RGI60-15.04541`

**Ponkar is not named in RGI 6.0**, so it had to be matched on evidence. The
thesis gives its position as 84°28′14″ E, 28°37′49″ N (84.4706, 28.6303). No
large glacier sits at that centroid — the biggest glacier whose *centroid* is
within 0.05° of it is 0.862 km², against the ~28.5 km² the thesis reports.

The match is `RGI60-15.04541`, and the thesis coordinate is its **terminus**,
not its centre:

| Evidence | Thesis / literature | `RGI60-15.04541` |
|---|---|---|
| Area | 28.509 km² (Thapa 2019) | 31.267 km² |
| Position | terminus at 84.471 E, 28.630 N | polygon spans 84.401–84.489 E, 28.633–28.767 N — the thesis point sits on its southern tip |
| Setting | Bhimthang valley, headwaters of the Dudh Khola, Marsyangdi sub-basin | valley glacier draining south into the Dudh Khola headwaters |
| Form | long, debris-covered valley glacier | 17.9 km long, lowest ice at 3734 m — far below any clean-ice limit in this range, which is what a debris-covered tongue looks like |
| Elevation range | 3703–3947 m minimum reported | 3734 m minimum |

It is the only glacier in the Manang search box that is both the right size and
the right shape, and the thesis coordinate falls on it. The identification is
recorded here rather than asserted silently because it is an inference, not a
lookup.

One number does not reconcile: the thesis reports a maximum elevation of
7096 m for Ponkar, where RGI and SRTM both give 6508–6509 m. A 7096 m summit
exists in the wider Larkya massif but not within this glacier's outline, which
suggests the thesis elevation statistics were taken over a rectangular scene
window rather than over the glacier itself. That would also explain why its
reported minimum elevation moves between epochs in a way a glacier terminus
does not.

## How to re-derive both

```bash
python src/fetch_rgi.py
```

The script pulls the South Asia East region out of the global RGI archive and
writes `data/rikha_samba_rgi.geojson` and `data/ponkar_rgi.geojson`. To check a
different candidate, change `rgi_id` in `src/config.py` and re-run.
