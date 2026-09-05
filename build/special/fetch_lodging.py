"""
Build special/lodging.json: overnight visitors staying in the map, clustered.

Charleston is a tourist city and most of its visitors never touch the airport --
they drive in. Airport passengers alone therefore capture only a slice of the
inbound travel. This models the rest from where visitors actually sleep.

Lodging comes from OSM (tourism=hotel/motel/guest_house/hostel/apartment) in
the city extract. Room counts use the `rooms` tag where present and the median
for that lodging type otherwise -- downtown is well mapped, the suburbs mostly
are not. Visitors present on an average night are rooms x occupancy x guests
per room.

POIs are then gridded into clusters so tourism is spread across the hotel
districts rather than piled on one node, and anything sitting on top of an
existing beach resort point is dropped so the two do not double-count.

    python special/fetch_lodging.py [path/to/chs.osm.pbf]
"""
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "lodging.json")
DEFAULT_PBF = os.path.join(HERE, os.pardir, "MSN", "msn.osm.pbf")

TOURISM = ["hotel", "motel", "guest_house", "hostel", "apartment"]
FALLBACK_ROOMS = {"hotel": 90, "motel": 45, "guest_house": 4,
                  "hostel": 30, "apartment": 8}
OCCUPANCY = 0.70            # typical annual hotel occupancy
# Room counts for untagged lodging are imputed from the median of the tagged
# ones of the same type -- but only when enough are tagged to be worth
# trusting. OSM tags the big, well-known downtown hotels first, so a thin
# sample skews high: in Madison six tagged hotels gave a median of 129 rooms
# and a metro total of 12,808, against a reality nearer 8-9k. Below this
# threshold the fixed per-type fallbacks are used instead.
MIN_TAGGED_FOR_MEDIAN = 20
GUESTS_PER_ROOM = 1.9
CELL_DEG = 0.012            # ~1.1 km clustering grid
# OSM routinely maps a hotel twice, once as a POI node and once as the building
# outline. Their representative points differ by tens of metres, so an
# exact-coordinate dedup keeps both and doubles the rooms. Collapse same-named
# lodging within this distance, preferring the entry that carries a rooms tag.
DUP_NAME_KM = 0.3
MIN_CLUSTER_VISITORS = 50
# Nothing here duplicates a resort point, unlike the Charleston build.
RESORT_LOCS = []   # Madison has no barrier-island resorts to avoid
RESORT_EXCLUDE_KM = 3.0


def _haversine_km(lon1, lat1, lon2, lat2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    return 2 * r * math.asin(math.sqrt(
        math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


def extract(pbf):
    tmp = tempfile.mkdtemp()
    filt = os.path.join(tmp, "lodging.osm.pbf")
    gj = os.path.join(tmp, "lodging.geojson")
    # Each value needs its own expression; osmium's comma list silently
    # produced an empty file here.
    cmd = ["osmium", "tags-filter", pbf]
    cmd += [f"nwr/tourism={v}" for v in TOURISM]
    cmd += ["-o", filt, "--overwrite"]
    subprocess.run(cmd, check=True, capture_output=True)
    subprocess.run(["osmium", "export", filt, "-o", gj, "--overwrite"],
                   check=True, capture_output=True)

    from shapely.geometry import shape
    rows, seen = [], set()
    with open(gj) as fh:
        for line in fh:
            line = line.strip().rstrip(",")
            if not line.startswith("{"):
                continue
            try:
                f = json.loads(line)
            except ValueError:
                continue
            props = f.get("properties", {})
            name = props.get("name")
            if not name:
                continue
            try:
                c = shape(f["geometry"]).representative_point()
            except Exception:
                continue
            key = (name, round(c.x, 4), round(c.y, 4))
            if key in seen:
                continue
            seen.add(key)
            try:
                rooms = int(props.get("rooms") or props.get("capacity:rooms"))
            except (TypeError, ValueError):
                rooms = None
            rows.append({"name": name, "type": props.get("tourism"),
                         "lon": c.x, "lat": c.y, "rooms": rooms})
    return _dedupe(rows)


def _dedupe(rows):
    """Collapse the same property mapped more than once (node + building)."""
    by_name = {}
    for r in rows:
        by_name.setdefault(r["name"].strip().casefold(), []).append(r)
    out = []
    for group in by_name.values():
        kept = []
        for r in group:
            near = next((k for k in kept
                         if _haversine_km(r["lon"], r["lat"],
                                          k["lon"], k["lat"]) <= DUP_NAME_KM), None)
            if near is None:
                kept.append(r)
            elif r["rooms"] and not near["rooms"]:
                near.update(rooms=r["rooms"], lon=r["lon"], lat=r["lat"])
        out.extend(kept)
    return out


def main(pbf):
    rows = extract(pbf)
    tagged = [r for r in rows if r["rooms"]]
    medians = {}
    for t in TOURISM:
        vals = [r["rooms"] for r in tagged if r["type"] == t]
        medians[t] = (statistics.median(vals)
                      if len(vals) >= MIN_TAGGED_FOR_MEDIAN else None)
    thin = [t for t in TOURISM if medians[t] is None
            and any(r["type"] == t for r in rows)]
    if thin:
        print(f"  too few tagged to impute a median for {', '.join(thin)}; "
              f"using fixed fallbacks")
    print(f"lodging POIs: {len(rows)}   with a rooms tag: {len(tagged)} "
          f"({sum(r['rooms'] for r in tagged):,} rooms)")

    def rooms_of(r):
        if r["rooms"]:
            return r["rooms"]
        m = medians.get(r["type"])
        return int(m) if m else FALLBACK_ROOMS.get(r["type"], 30)

    kept = [r for r in rows
            if min((_haversine_km(r["lon"], r["lat"], x, y) for x, y in RESORT_LOCS),
                   default=99) > RESORT_EXCLUDE_KM]
    print(f"dropped {len(rows) - len(kept)} POIs sitting on an existing resort point")

    cells = {}
    for r in kept:
        key = (round(r["lon"] / CELL_DEG), round(r["lat"] / CELL_DEG))
        c = cells.setdefault(key, {"rooms": 0, "wx": 0.0, "wy": 0.0, "n": 0})
        rm = rooms_of(r)
        c["rooms"] += rm
        c["wx"] += r["lon"] * rm
        c["wy"] += r["lat"] * rm
        c["n"] += 1

    out = []
    for i, c in enumerate(sorted(cells.values(), key=lambda c: -c["rooms"])):
        visitors = int(c["rooms"] * OCCUPANCY * GUESTS_PER_ROOM)
        if visitors < MIN_CLUSTER_VISITORS:
            continue
        out.append({"code": f"L{len(out) + 1:02d}",
                    "lon": round(c["wx"] / c["rooms"], 5),
                    "lat": round(c["wy"] / c["rooms"], 5),
                    "rooms": c["rooms"], "pois": c["n"], "visitors": visitors})

    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote {OUT}")
    print(f"  {len(out)} lodging clusters  {sum(o['rooms'] for o in out):,} rooms  "
          f"{sum(o['visitors'] for o in out):,} overnight visitors")
    for o in out[:8]:
        print(f"    {o['code']}  {o['visitors']:>6,} visitors  {o['rooms']:>5,} rooms "
              f"({o['pois']:>3} POIs)  {o['lat']:.4f},{o['lon']:.4f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PBF)
