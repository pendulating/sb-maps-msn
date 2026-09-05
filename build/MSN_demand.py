"""
Build the Madison (MSN) demand data for Subway Builder.

Base demand comes from slurry's US Demand Generator over LODES 2023 for the
Dane County bbox (see ../us-demand/Madison.json), which is regenerated
whenever the map bbox changes. This script layers the special demand on top
with depot, recomputes commutes through a local OSRM server, and writes
config.json.

Special demand lives in special/pois.py. Adding it through depot rather than
by hand is what produces the .railyard_map/special_demand_*.json schema files,
which the 3.0.0 map never shipped -- without them the game has no
type information for these points.

Run a single stage:   python MSN_demand.py <stage>
Stages: seed | special | osrm | routes | routes-new | reschool | tourism | strip-paths | config | all
"""
import json
import os
import shutil
import sys

from depot.demand import DemandData

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from special import pois as POIS

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "MSN_demand")
FDEMAND = os.path.join(OUTDIR, "demand_data.json")
BASE_DEMAND = os.path.join(HERE, os.pardir, "us-demand", "demand_data",
                           "Madison", "demand_data.json")
OSMPBF = os.path.join(HERE, "wisconsin-latest.osm.pbf")
BBOX = [-89.86, 42.83, -88.99, 43.30]
OSRM_PORT = 5050
# Matches the generator's MAXPOPSIZE. Pops larger than a trainload cannot be
# carried, so merging must not produce them.
MAXPOPSIZE = 200

# depot embeds the full polyline of every commute in demand_data.json when it
# routes. It is the single most expensive thing in the shipped map and almost
# nobody else does it: at 43 vertices a pop it made the file 74 MB, 85% of it
# path geometry, or 1.1 KB per pop against a 0.18 KB median across 274 registry
# maps. The game does not read them from here anyway -- it asks for a path one
# pop at a time over map://paths/{cityCode}/{popId}, which Railyard serves.
# Keeping drivingSeconds and drivingDistance, which the simulation does need.
INCLUDE_DRIVING_PATHS = False

os.makedirs(OUTDIR, exist_ok=True)


def stage_seed():
    """Copy the generator's LODES output in as the starting point."""
    shutil.copy(BASE_DEMAND, FDEMAND)
    d = json.load(open(FDEMAND))
    print(f"seeded from {BASE_DEMAND}")
    print(f"  {len(d['points']):,} points  {len(d['pops']):,} pops  "
          f"{sum(p['size'] for p in d['pops']):,} commuters")


def _load():
    dd = DemandData(FDEMAND, map_code="MSN", bbox=BBOX, outputdir=OUTDIR)
    _guard_haversine(dd)
    return dd


def _guard_haversine(dd):
    """
    depot calls self._haversine_travel_time when OSRM reports NoRoute, but only
    a module-level haversine_travel_time exists. One unroutable point would
    raise AttributeError partway through calculate_routes and discard the whole
    pass before save(). Bind the method so the fallback works as intended.
    """
    if not hasattr(dd, "_haversine_travel_time"):
        from depot import demand as _demand
        fn = getattr(_demand, "haversine_travel_time", None)
        if fn is not None:
            type(dd)._haversine_travel_time = staticmethod(fn)


def _prune_schema(removed_ids):
    """
    Drop deleted points from the special-demand schema.

    depot's save_schemas appends to whatever special_demand_points.json is
    already on disk whenever the demand file already contains special demand.
    del_points does not touch it, so a surgical stage leaves every replaced
    point in the schema twice, along with pop_ids for pops that no longer
    exist. Left alone this reached 530 entries for 313 points, with 9,317 dead
    pop_ids, and package.py would have shipped it.
    """
    path = os.path.join(OUTDIR, ".railyard_map", "special_demand_points.json")
    if not os.path.exists(path) or not removed_ids:
        return
    with open(path) as f:
        schema = json.load(f)
    before = len(schema.get("points", []))
    schema["points"] = [p for p in schema.get("points", [])
                        if p.get("point_id") not in set(removed_ids)]
    with open(path, "w") as f:
        json.dump(schema, f, indent=4)
    print(f"pruned {before - len(schema['points'])} stale schema entries")


def _drop_self_loops(dd):
    """
    Remove pops whose residence and job are the same point. They are
    zero-length commutes that generate no travel, they get listed twice in that
    point's popIds, and they are re-routed on every pass. Most come straight
    from the LODES base; a few are created when a merge absorbs two points that
    commuted to each other.
    """
    loops = {p["id"] for p in dd["pops"] if p["residenceId"] == p["jobId"]}
    if not loops:
        return
    dd["pops"] = [p for p in dd["pops"] if p["id"] not in loops]
    dd.update(dd.sanitize(dd))
    print(f"dropped {len(loops):,} self-loop pops")


def _resync_schema_popids(dd):
    """
    Rebuild each special point's pop_ids from the demand as it now stands.

    add_points snapshots pop_ids at the moment it places a point, and
    save_schemas writes that snapshot out. Anything that touches pops
    afterwards -- dropping self-loops, merging identical commutes, re-splitting
    at MAXPOPSIZE -- leaves the snapshot describing pops that no longer exist,
    and misses the ones that replaced them. sanitize has already recomputed
    every point's popIds from the pops, so take them from there rather than
    trying to track each mutation.
    """
    by_id = {p["id"]: p for p in dd["points"]}
    fixed = 0
    for poi in getattr(dd, "added_special_demand_points", []):
        pid = poi.get("point_id")
        point = by_id.get(pid)
        if point is None:
            continue
        # sanitize appends a pop id once per endpoint, so de-duplicate.
        seen, ids = set(), []
        for i in point.get("popIds", []):
            if i not in seen:
                seen.add(i)
                ids.append(i)
        if poi.get("pop_ids") != ids:
            poi["pop_ids"] = ids
            fixed += 1
    if fixed:
        print(f"resynced pop_ids for {fixed} special points")


def _floor_durations(dd):
    """
    Give every routed pop at least one second of travel.

    OSRM returns a real route for an origin and destination a few hundred
    metres apart, but `int(duration)` rounds it to zero -- a pupil living 290 m
    from their school here. A zero-second commute is indistinguishable from an
    unrouted one downstream, and it implies infinite speed to anything that
    divides by it.
    """
    fixed = 0
    for p in dd["pops"]:
        if p["residenceId"] == p["jobId"]:
            continue
        if p.get("drivingSeconds", 0) <= 0 and p.get("drivingDistance", 0) > 0:
            p["drivingSeconds"] = 1
            fixed += 1
    if fixed:
        print(f"floored {fixed:,} sub-second commutes to 1s")


def _base_points(dd):
    return [p for p in dd["points"] if p["id"].startswith("merged")]


def _resident_baseline():
    """LODES residents per point, before any special demand moved people in."""
    d = json.load(open(BASE_DEMAND))
    return {p["id"]: p["residents"] for p in d["points"]}


def stage_special():
    dd = _load()
    before_pts, before_pops = len(dd["points"]), len(dd["pops"])
    before_size = sum(p["size"] for p in dd["pops"])

    # Order matters. The airport goes in on its own first, because the lodging
    # clusters' required_locs must resolve to an AIR_CHS that already exists --
    # add_points only merges its new points into the list once it returns, so a
    # combined call would bind them to the nearest base node instead, silently.
    print("adding the airport")
    dd.add_points(POIS.AIRPORT)

    other = POIS.non_school_pois()
    print(f"adding {len(other)} other non-school special demand points")
    dd.add_points(other)

    lod = POIS.lodging()
    print(f"adding {len(lod)} lodging clusters")
    dd.add_points(lod)

    # Schools last: the merges above delete the LODES points they absorb, and
    # catchments have to be drawn against the point list that survives.
    sch = POIS.schools(_base_points(dd), _resident_baseline())
    print(f"adding {len(sch)} school points")
    dd.add_points(sch)

    _drop_self_loops(dd)

    # The allocators hand a residence node several pops bound for the same
    # school or hotel; those are one commute, not several. Merging them takes a
    # size-weighted mean of the route, then the split puts anything over a
    # trainload back into separate pops.
    before_merge = len(dd["pops"])
    dd.merge_identical_commutes()
    dd.enforce_max_pop_size(MAXPOPSIZE)
    dd.update(dd.sanitize(dd))
    print(f"merged identical commutes: {before_merge:,} -> {len(dd['pops']):,} pops")

    _resync_schema_popids(dd)
    dd.save()

    after_size = sum(p["size"] for p in dd["pops"])
    print(f"\npoints {before_pts:,} -> {len(dd['points']):,}"
          f"   pops {before_pops:,} -> {len(dd['pops']):,}"
          f"   people {before_size:,} -> {after_size:,}")


def stage_reschool():
    """Replace just the school points, leaving every other point's routes intact."""
    dd = _load()
    old = [p["id"] for p in dd["points"] if p["id"].startswith("SCH_")]
    if old:
        print(f"removing {len(old)} existing school points")
        dd.del_points(point_ids=old)
        _prune_schema(old)
        # del_points drops the pops but leaves each point's jobs/residents
        # totals stale, and the catchment allocator sizes against residents.
        # Without this the old intake still inflates them.
        dd.update(dd.sanitize(dd))
    sch = POIS.schools(_base_points(dd), _resident_baseline())
    print(f"adding {len(sch)} school points on attendance-zone catchments")
    dd.add_points(sch)
    dd.save()
    print(f"points {len(dd['points']):,}  pops {len(dd['pops']):,}  "
          f"people {sum(p['size'] for p in dd['pops']):,}")


def stage_tourism():
    """Rescale the airport onto real passenger traffic and add lodging."""
    dd = _load()
    have = {p["id"] for p in dd["points"]}
    stale = [i for i in have if i == "AIR_CHS" or i.startswith("RST_L")]
    if stale:
        print(f"removing {len(stale)} existing tourism points")
        dd.del_points(point_ids=stale)
        _prune_schema(stale)
        dd.update(dd.sanitize(dd))
    # Two calls, not one: add_points only merges its new points into the list
    # at the end of the call, so the lodging clusters' required_locs would not
    # resolve to AIR_CHS if they went in together -- they would silently bind
    # to whatever base node sits nearest the airport instead.
    print("adding the airport")
    dd.add_points(POIS.AIRPORT)
    lod = POIS.lodging()
    print(f"adding {len(lod)} lodging clusters")
    dd.add_points(lod)
    dd.save()
    print(f"points {len(dd['points']):,}  pops {len(dd['pops']):,}  "
          f"people {sum(p['size'] for p in dd['pops']):,}")


def stage_routes_new():
    """Route only pops that have no route yet -- i.e. the ones just added."""
    dd = _load()
    todo = sum(1 for p in dd["pops"] if p.get("drivingSeconds", 0) <= 0)
    print(f"{todo:,} of {len(dd['pops']):,} pops need routing")
    dd.calculate_routes(routing_method="osrm", osrm_port=OSRM_PORT,
                        recalculate_routes=False,
                        include_driving_paths=INCLUDE_DRIVING_PATHS)
    _floor_durations(dd)
    dd.save()
    dd.print_stats()


def stage_osrm():
    """
    depot's prepare_osrm publishes -p <port>:<port>, but osrm-routed listens on
    5000 inside the container, so only the default port ever connects. Do the
    extract and preprocessing through depot, then start the router by hand.
    """
    dd = _load()
    dd.prepare_osrm(OSMPBF, bbox=BBOX, port=OSRM_PORT, force_recreate=True)


def stage_routes():
    dd = _load()
    dd.print_stats()
    dd.calculate_routes(routing_method="osrm", osrm_port=OSRM_PORT,
                        recalculate_routes=True,
                        include_driving_paths=INCLUDE_DRIVING_PATHS)
    _floor_durations(dd)
    dd.save()
    dd.print_stats()


def stage_strip_paths():
    """Drop embedded drivingPath geometry from an already-routed demand file."""
    with open(FDEMAND) as f:
        d = json.load(f)
    before = os.path.getsize(FDEMAND)
    n = sum(1 for p in d["pops"] if "drivingPath" in p)
    for p in d["pops"]:
        p.pop("drivingPath", None)
    with open(FDEMAND, "w") as f:
        json.dump(d, f, separators=(",", ":"))
    after = os.path.getsize(FDEMAND)
    print(f"stripped drivingPath from {n:,} pops")
    print(f"  demand_data.json {before/1048576:.1f} MB -> {after/1048576:.1f} MB "
          f"({(before-after)/before:.0%} smaller)")


def stage_config():
    dd = _load()
    dd.create_config(
        name="Madison",
        bbox=BBOX,
        description="Build rail lines down the bustling Madison isthmus to "
                    "serve the City of Four Lakes with quality public "
                    "transport.",
        creator="muffintime",
        version="4.0.0",
        country="US",
        initial_view_state=[-89.382706, 43.077164],
    )
    # create_config hardcodes zoom 12, which is what 3.0.0 opened at anyway,
    # so the author's framing is already what comes out. Set it explicitly so
    # a depot change cannot move it silently.
    fconfig = os.path.join(OUTDIR, "config.json")
    config = json.load(open(fconfig))
    config["initialViewState"]["zoom"] = 12
    json.dump(config, open(fconfig, "w"), indent=4)
    print(f"set initialViewState.zoom to 12 in {fconfig}")


STAGES = {"seed": stage_seed, "special": stage_special, "osrm": stage_osrm,
          "routes": stage_routes, "routes-new": stage_routes_new,
          "reschool": stage_reschool, "tourism": stage_tourism,
          "strip-paths": stage_strip_paths, "config": stage_config}
STAGES["all"] = lambda: [s() for s in (stage_seed, stage_special, stage_osrm,
                                       stage_routes, stage_config)]

if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage not in STAGES:
        raise SystemExit(f"unknown stage {stage!r}; pick one of {', '.join(STAGES)}")
    print(f"===== MSN demand stage: {stage} =====", flush=True)
    STAGES[stage]()
    print(f"===== MSN demand stage {stage} complete =====", flush=True)
