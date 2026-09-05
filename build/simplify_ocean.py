"""
Shrink ocean_depth_index.json.gz by simplifying its depth polygons.

The file is the single largest thing the game parses for this map -- 79 MB
uncompressed -- and 98% of it is polygon geometry. Almost all of that is the
shallowest band: depot patches -5 m with `water_gaps`, "everywhere OSM says
there is water but GEBCO left a gap", and GEBCO's global grid is about 450 m,
so every tidal creek and marsh channel in the Lowcountry arrives as
hand-detailed shoreline. That came to 81,134 polygons and 3.07M vertices for
the -5 band alone.

The detail is far finer than anything that consumes it. The index addresses
water through a grid of 0.0027 degree cells, about 250 m on a side, so
shoreline resolved to a metre buys nothing. Simplifying at ~9 m and rounding
coordinates to ~1 m keeps every polygon and its holes -- so water stays water
and no marsh turns into buildable land -- while removing most of the vertices.

Polygon count and order are deliberately preserved: the `cells` array indexes
into `depths` by position, so dropping or reordering entries would silently
mis-address every cell that referenced anything after the gap.

    python simplify_ocean.py [--tolerance 0.0001] [--check]
"""
import argparse
import gzip
import json
import os

from shapely.geometry import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "MSN", "ocean_depth_index.json.gz")
CONTOURS = os.path.join(HERE, "MSN", "ocean_depth_index_contours.json.gz")

# ~9 m at this latitude, against a ~250 m collision grid.
DEFAULT_TOLERANCE = 0.0001
# ~1.1 m, comfortably finer than the tolerance above.
PRECISION = 5


def _ring(coords):
    return [[round(x, PRECISION), round(y, PRECISION)] for x, y in coords]


def simplify_entry(entry, tol):
    """Simplify one depth polygon, keeping its holes. Falls back to the
    original ring whenever simplification would degrade it to nothing."""
    rings = entry["p"]
    if not rings:
        return entry, 0
    shell, holes = rings[0], rings[1:]
    if len(shell) < 4:
        return entry, sum(len(r) for r in rings)
    try:
        poly = Polygon(shell, [h for h in holes if len(h) >= 4])
        if not poly.is_valid:
            poly = poly.buffer(0)
        simple = poly.simplify(tol, preserve_topology=True)
        if simple.is_empty or simple.geom_type != "Polygon":
            raise ValueError("degenerate")
        new_shell = _ring(simple.exterior.coords)
        new_holes = [_ring(h.coords) for h in simple.interiors]
        if len(new_shell) < 4:
            raise ValueError("degenerate shell")
    except Exception:
        new_shell, new_holes = _ring(shell), [_ring(h) for h in holes]
        simple = None

    out = dict(entry)
    out["p"] = [new_shell] + new_holes
    if simple is not None:
        out["b"] = [round(v, PRECISION) for v in simple.bounds]
    else:
        out["b"] = [round(v, PRECISION) for v in entry["b"]]
    return out, len(new_shell) + sum(len(h) for h in new_holes)


def process(path, tol, key="depths"):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    before_bytes = os.path.getsize(path)
    before_raw = len(json.dumps(data, separators=(",", ":")))
    entries = data[key]
    before_verts = sum(len(r) for e in entries for r in e["p"])

    out, verts = [], 0
    for e in entries:
        new, n = simplify_entry(e, tol)
        out.append(new)
        verts += n
    data[key] = out

    assert len(data[key]) == len(entries), "entry count changed; cells index would break"
    after_raw = len(json.dumps(data, separators=(",", ":")))
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(data, f, separators=(",", ":"))

    print(f"{os.path.basename(path)}")
    print(f"  polygons {len(entries):,} (unchanged)   "
          f"vertices {before_verts:,} -> {verts:,} ({1 - verts/before_verts:.0%} fewer)")
    print(f"  raw  {before_raw/1048576:>6.1f} MB -> {after_raw/1048576:>6.1f} MB "
          f"({1 - after_raw/before_raw:.0%} smaller)")
    print(f"  gz   {before_bytes/1048576:>6.1f} MB -> "
          f"{os.path.getsize(path)/1048576:>6.1f} MB")


def check(path):
    """Verify the cells index still addresses valid depth entries."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        d = json.load(f)
    n = len(d["depths"])
    bad = [c for c in d["cells"] if any(i >= n or i < 0 for i in c[2:])]
    empty = [i for i, e in enumerate(d["depths"]) if not e["p"] or len(e["p"][0]) < 4]
    print(f"cells referencing out-of-range depth entries: {len(bad)}")
    print(f"depth entries with a degenerate outer ring   : {len(empty)}")
    return not bad and not empty


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        raise SystemExit(0 if check(PATH) else 1)
    process(PATH, a.tolerance)
    if os.path.exists(CONTOURS):
        process(CONTOURS, a.tolerance)
    print()
    check(PATH)
