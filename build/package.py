"""
Assemble the MSN.zip release archive from the depot build outputs.

The file set follows what depot's own author ships for depot-built maps
(TPA/JAX/DCA in the Railyard registry): both buildings-index forms, the
foundations PMTiles, and the gzipped ocean depth index. Everything is written
flat -- Railyard requires a ZIP with no nested folders, and this builds the
archive entry by entry so no __MACOSX sidecars can sneak in (the 1.0.0 release
shipped one).
"""
import gzip
import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CITY = "MSN"
MAPDIR = os.path.join(HERE, CITY)
DEMANDDIR = os.path.join(HERE, CITY + "_demand")
OUT = os.path.join(HERE, "dist", "MSN.zip")

# (source path, name inside the zip, required?)
# The .railyard_map entries are the special-demand schema; they are the one
# place a nested path is correct, and they match what depot's own author ships.
CONTENTS = [
    (os.path.join(DEMANDDIR, "config.json"), "config.json", True),
    (os.path.join(DEMANDDIR, "demand_data.json"), "demand_data.json", True),
    (os.path.join(DEMANDDIR, ".railyard_map", "special_demand_points.json"),
     ".railyard_map/special_demand_points.json", True),
    (os.path.join(DEMANDDIR, ".railyard_map", "special_demand_types.json"),
     ".railyard_map/special_demand_types.json", True),
    (os.path.join(MAPDIR, f"{CITY}.pmtiles"), f"{CITY}.pmtiles", True),
    (os.path.join(MAPDIR, f"{CITY}_foundations.pmtiles"), f"{CITY}_foundations.pmtiles", False),
    (os.path.join(MAPDIR, "buildings_index.bin.gz"), "buildings_index.bin.gz", True),
    (os.path.join(MAPDIR, "buildings_index.json.gz"), "buildings_index.json.gz", True),
    (os.path.join(MAPDIR, "ocean_depth_index.json.gz"), "ocean_depth_index.json.gz", False),
    (os.path.join(MAPDIR, "ocean_depth_index_contours.json.gz"), "ocean_depth_index_contours.json.gz", False),
    (os.path.join(MAPDIR, "roads.geojson"), "roads.geojson", True),
    (os.path.join(MAPDIR, "runways_taxiways.geojson"), "runways_taxiways.geojson", True),
]


def preflight():
    """
    Refuse to ship a stale or internally inconsistent build. Every check here
    corresponds to something that has actually gone wrong: an archive built
    before the demand file it was meant to contain, a schema accumulating
    duplicate entries from a surgical rebuild, and pops left unrouted.
    """
    problems = []

    demand_path = os.path.join(DEMANDDIR, "demand_data.json")
    with open(demand_path) as f:
        demand = json.load(f)
    pops, points = demand["pops"], demand["points"]

    unrouted = [p for p in pops
                if p.get("drivingSeconds", 0) <= 0 and p["residenceId"] != p["jobId"]]
    if unrouted:
        problems.append(f"{len(unrouted):,} pops have no route "
                        f"(e.g. {unrouted[0]['id']}) -- run the routes stage")

    ids = [p["id"] for p in points]
    if len(ids) != len(set(ids)):
        problems.append(f"{len(ids) - len(set(ids))} duplicate point ids")

    schema_path = os.path.join(DEMANDDIR, ".railyard_map", "special_demand_points.json")
    with open(schema_path) as f:
        schema = json.load(f)["points"]
    sids = [e["point_id"] for e in schema]
    if len(sids) != len(set(sids)):
        problems.append(f"schema has {len(sids) - len(set(sids))} duplicate point_ids "
                        f"-- stale entries from a surgical rebuild")
    live_pops = {p["id"] for p in pops}
    dead = sum(1 for e in schema for pid in e.get("pop_ids", []) if pid not in live_pops)
    if dead:
        problems.append(f"schema references {dead:,} pop_ids that no longer exist")
    live_points = set(ids)
    orphan = [e["point_id"] for e in schema if e["point_id"] not in live_points]
    if orphan:
        problems.append(f"schema names {len(orphan)} points absent from the demand "
                        f"(e.g. {orphan[0]})")

    with open(os.path.join(DEMANDDIR, "config.json")) as f:
        config = json.load(f)
    total = sum(p["size"] for p in pops)
    if config["population"] != total:
        problems.append(f"config population {config['population']:,} != "
                        f"demand total {total:,} -- re-run the config stage")

    if problems:
        raise SystemExit("preflight failed:\n  - " + "\n  - ".join(problems))
    print(f"preflight ok: {len(points):,} points, {len(pops):,} pops, "
          f"{total:,} people, schema clean")


def main():
    missing = [n for src, n, req in CONTENTS if req and not os.path.exists(src)]
    if missing:
        raise SystemExit("missing required build outputs: " + ", ".join(missing))
    preflight()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    included, skipped = [], []
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for src, name, _req in CONTENTS:
            if not os.path.exists(src):
                skipped.append(name)
                continue
            z.write(src, arcname=name)
            included.append((name, os.path.getsize(src)))

    print(f"wrote {OUT}")
    for name, size in included:
        print(f"  {size / 1048576:9.2f} MB  {name}")
    if skipped:
        print("  not produced by this build: " + ", ".join(skipped))

    zsize = os.path.getsize(OUT)
    digest = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    print(f"\narchive: {zsize / 1048576:.2f} MB")
    print(f"sha256 : {digest}")


if __name__ == "__main__":
    sys.exit(main())
