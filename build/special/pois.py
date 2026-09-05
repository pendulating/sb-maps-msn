"""
Special demand definitions for the Madison (MSN) map.

Every entry is a depot `DemandData.add_points` POI. Two conventions govern the
numbers, and they are the same ones the Charleston build settled on:

`merge_within` (metres) folds the nearby LODES block points into the special
point. It belongs wherever the site is a workplace LODES already counts -- a
hospital, a campus, a mall, an office campus -- otherwise its staff are counted
twice, once in the block point and once here. Skip it only where the demand is
people LODES never saw.

`residential_split` is the share of capacity that *lives* at the point and
travels out rather than in. It is how inbound travel is modelled: an arriving
air passenger, a student in a dorm, a guest in a hotel is a resident of that
point for the day.

So a point's capacity should be the trips LODES never sees. Campuses carry
students, not faculty. Hospitals carry patients, not nurses. Employers carry
almost nothing on top of the merge, because their whole workforce is already in
LODES -- what makes them worth adding is that the merge gives the site a
labelled, correctly typed point instead of an anonymous block.

The 3.0.0 map had eight special demand points in total: the university, the
airport, the technical college and five entertainment sites. There were no
schools, no hospitals, no state government, no Epic, and the airport had 6,600
jobs against zero residents -- a city with departures and no arrivals.

Coordinates are from OpenStreetMap in the map extract.
"""
import json
import math
import os
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# The map extent. POIs carry real coordinates and are filtered against this
# rather than hand-pruned, so changing the bbox cannot silently leave a point
# off the edge of the map, where depot would place it and the game would never
# reach it.
BBOX = [-89.86, 42.83, -88.99, 43.30]


def in_bbox(location):
    return (BBOX[0] <= location[0] <= BBOX[2]
            and BBOX[1] <= location[1] <= BBOX[3])


# --- Airport -----------------------------------------------------------------
# Dane County Regional handles roughly 2.2M passengers a year, about 6,000 a
# day across both directions. The 3.0.0 map gave it 6,600 jobs and no residents
# at all, so nobody ever arrived in Madison by air.
AIRPORT_LOC = [-89.3377, 43.1421]
DAILY_PASSENGERS = 6000
ARRIVALS = DAILY_PASSENGERS // 2
# Share of arrivals who are visitors heading for a hotel. The rest are
# residents coming home, students returning to campus, people staying with
# family; they disperse by gravity.
ARRIVALS_TO_LODGING = 0.60
# Of the hotel-bound, the share going to the downtown/isthmus hotels rather
# than the airport strip and the Beltline. Madison's visitor draw is the
# Capitol square, the campus and the lakes, all downtown.
DOWNTOWN_SHARE = 0.70
DOWNTOWN_BBOX = (-89.42, 43.06, -89.36, 43.09)

_lodging_bound = int(ARRIVALS * ARRIVALS_TO_LODGING)
_dispersing = ARRIVALS - _lodging_bound
_departures = DAILY_PASSENGERS - ARRIVALS

AIRPORT = [
    dict(type="airport", name="Dane County Regional Airport", code="MSN",
         location=AIRPORT_LOC,
         total_capacity=_departures + _dispersing,
         pop_size=50,
         residential_split=_dispersing / (_departures + _dispersing),
         merge_within=900),
]

# --- Universities ------------------------------------------------------------
# UW-Madison is the single largest thing on this map. Enrolment is about 50,000
# with roughly 8,000 in university housing, so capacity is students and the
# split is the on-campus share. 3.0.0 modelled it at 19,400 jobs / 2,800
# residents, which understates both the size and how residential the campus is.
# merge_within is wide because the campus runs a mile along the lake and its
# ~24,000 staff sit in several LODES blocks.
UNIVERSITIES = [
    dict(type="university", name="University of Wisconsin-Madison", code="UW",
         location=[-89.4310, 43.0803], total_capacity=45000, pop_size=100,
         residential_split=0.17, merge_within=1200),
    dict(type="university", name="Madison College - Truax Campus", code="MATC",
         location=[-89.3305, 43.1203], total_capacity=10000, pop_size=50,
         residential_split=0.0, merge_within=700),
    dict(type="university", name="Madison College - South Campus", code="MATCS",
         location=[-89.3954, 43.0412], total_capacity=1800, pop_size=25,
         residential_split=0.0, merge_within=400),
    dict(type="university", name="Edgewood College", code="EDGE",
         location=[-89.4204, 43.0565], total_capacity=1800, pop_size=25,
         residential_split=0.35, merge_within=400),
]

# --- State government --------------------------------------------------------
# Madison is the state capital and Wisconsin is one of its largest employers.
# Those jobs are covered employment and therefore already in LODES, so the
# merge is doing the real work here: it gives the Capitol and the agency
# complexes labelled points instead of anonymous downtown blocks. Capacity on
# top is only the visiting public -- Capitol tours, hearings, DMV, licensing.
GOVERNMENT = [
    dict(type="government_facility", name="Wisconsin State Capitol", code="CAP",
         location=[-89.3839, 43.0744], total_capacity=1800, pop_size=25,
         merge_within=450),
    dict(type="government_facility", name="GEF State Office Complex", code="GEF",
         location=[-89.3862, 43.0693], total_capacity=700, pop_size=25,
         merge_within=400),
    dict(type="government_facility", name="Hill Farms State Office Building", code="HILL",
         location=[-89.4400, 43.0700], total_capacity=600, pop_size=25,
         merge_within=400),
    dict(type="government_facility", name="Dane County City-County Building", code="CCB",
         location=[-89.3823, 43.0721], total_capacity=900, pop_size=25,
         merge_within=300),
]

# --- Major private employers -------------------------------------------------
# Epic in Verona is the case that most needs a point: about 13,000 people on one
# isolated campus eight miles from downtown, which as a bare LODES block is just
# a number in a field. American Family's east-side headquarters is the same
# shape of thing. Both workforces are in LODES and arrive through the merge, so
# capacity here is only the visitors on top -- Epic in particular runs a heavy
# year-round stream of customer and training traffic.
EMPLOYERS = [
    dict(type="custom", name="Epic Systems", code="EPIC",
         location=[-89.5699, 43.0002], total_capacity=1200, pop_size=50,
         merge_within=1500),
    dict(type="custom", name="American Family Insurance", code="AMFAM",
         location=[-89.2932, 43.1583], total_capacity=400, pop_size=25,
         merge_within=1000),
    dict(type="custom", name="University Research Park", code="URP",
         location=[-89.4762, 43.0541], total_capacity=300, pop_size=25,
         merge_within=800),
    dict(type="custom", name="Exact Sciences", code="EXAS",
         location=[-89.4899, 43.0511], total_capacity=250, pop_size=25,
         merge_within=600),
    dict(type="custom", name="Promega", code="PRMG",
         location=[-89.4183, 43.0044], total_capacity=200, pop_size=25,
         merge_within=800),
]

# --- Hospitals ---------------------------------------------------------------
# Staff are in LODES and arrive through the merge, so capacity is patients and
# visitors at ~2.5 daily arrivals per licensed bed. Bed counts are OSM `beds`
# tags where present; the rest use published counts and are marked est.
HOSPITALS = [
    dict(type="hospital", name="UW Health University Hospital", code="UWH",
         location=[-89.4320, 43.0764], total_capacity=1250, pop_size=50,
         merge_within=500),                                    # 505 beds
    dict(type="hospital", name="UnityPoint Health - Meriter", code="MER",
         location=[-89.4017, 43.0660], total_capacity=1120, pop_size=50,
         merge_within=400),                                    # 448 beds
    dict(type="hospital", name="SSM Health St. Mary's Hospital", code="STM",
         location=[-89.4043, 43.0586], total_capacity=1100, pop_size=50,
         merge_within=400),                                    # ~440 beds, est.
    dict(type="hospital", name="American Family Children's Hospital", code="AFCH",
         location=[-89.4334, 43.0768], total_capacity=280, pop_size=25,
         merge_within=300),                                    # ~111 beds, est.
    dict(type="hospital", name="William S. Middleton VA Hospital", code="VA",
         location=[-89.4313, 43.0747], total_capacity=400, pop_size=25,
         merge_within=300),                                    # 86 beds + clinics
    dict(type="hospital", name="UW Health East Madison Hospital", code="EAST",
         location=[-89.3010, 43.1549], total_capacity=350, pop_size=25,
         merge_within=500),
    dict(type="hospital", name="Stoughton Hospital", code="STO",
         location=[-89.2110, 42.9208], total_capacity=90, pop_size=25,
         merge_within=400),                                    # 35 beds
]

# --- Sport and events --------------------------------------------------------
# Camp Randall seats 80,000 and the Kohl Center 17,000. These are the largest
# single-moment loads anywhere on the map. Averaged over a season they are not
# 80,000 a day, so capacity is a typical event-day draw rather than capacity.
SPORTS = [
    dict(type="sports_facility", name="Camp Randall Stadium", code="RANDALL",
         location=[-89.4126, 43.0701], total_capacity=11000, pop_size=100,
         merge_within=300),
    dict(type="sports_facility", name="Kohl Center", code="KOHL",
         location=[-89.3974, 43.0693], total_capacity=3500, pop_size=50,
         merge_within=250),
    dict(type="events", name="Alliant Energy Center", code="ALLIANT",
         location=[-89.3800, 43.0437], total_capacity=2500, pop_size=50,
         merge_within=600),
    dict(type="convention_center", name="Monona Terrace", code="MONONA",
         location=[-89.3800, 43.0717], total_capacity=1200, pop_size=25,
         merge_within=250),
]

# --- Retail ------------------------------------------------------------------
SHOPPING = [
    dict(type="shopping_center", name="West Towne Mall", code="WTOWNE",
         location=[-89.5064, 43.0571], total_capacity=2000, pop_size=50,
         merge_within=500),
    dict(type="shopping_center", name="East Towne Mall", code="ETOWNE",
         location=[-89.3046, 43.1246], total_capacity=1900, pop_size=50,
         merge_within=500),
    dict(type="shopping_center", name="Hilldale Mall", code="HILLDALE",
         location=[-89.4524, 43.0730], total_capacity=1100, pop_size=25,
         merge_within=400),
    dict(type="shopping_center", name="South Towne", code="STOWNE",
         location=[-89.3507, 43.0450], total_capacity=700, pop_size=25,
         merge_within=400),
]

# --- Culture -----------------------------------------------------------------
ATTRACTIONS = [
    dict(type="cultural_center", name="Overture Center for the Arts", code="OVERTURE",
         location=[-89.3888, 43.0740], total_capacity=1400, pop_size=25,
         merge_within=200),
    dict(type="museum", name="Madison Museum of Contemporary Art", code="MMOCA",
         location=[-89.3889, 43.0745], total_capacity=500, pop_size=25,
         merge_within=150),
    dict(type="museum", name="Chazen Museum of Art", code="CHAZEN",
         location=[-89.3989, 43.0740], total_capacity=400, pop_size=25,
         merge_within=150),
    dict(type="museum", name="Madison Children's Museum", code="MCM",
         location=[-89.3845, 43.0770], total_capacity=350, pop_size=25,
         merge_within=150),
    dict(type="zoo", name="Henry Vilas Zoo", code="VILASZOO",
         location=[-89.4091, 43.0597], total_capacity=2200, pop_size=50,
         merge_within=250),
]

# --- Lakes and parks ---------------------------------------------------------
# Madison is the City of Four Lakes and the shoreline parks are where the city
# actually goes. None of this is in LODES: a swimmer at Olbrich Beach or a
# terrace regular is not a covered job anywhere. Seasonal in reality, modelled
# as an average day, and no merge -- these sit inside residential blocks whose
# own commuters should stay their own points.
PARKS = [
    dict(type="park", name="Memorial Union Terrace", code="TERRACE",
         location=[-89.3996, 43.0767], total_capacity=3000, pop_size=50),
    dict(type="park", name="Olbrich Botanical Gardens and Park", code="OLBRICH",
         location=[-89.3345, 43.0917], total_capacity=1800, pop_size=50),
    dict(type="park", name="Henry Vilas Park", code="VILAS",
         location=[-89.4147, 43.0596], total_capacity=1400, pop_size=25),
    dict(type="park", name="Tenney Park", code="TENNEY",
         location=[-89.3674, 43.0919], total_capacity=900, pop_size=25),
    dict(type="park", name="James Madison Park", code="JAMESMAD",
         location=[-89.3821, 43.0795], total_capacity=800, pop_size=25),
    dict(type="park", name="Warner Park", code="WARNER",
         location=[-89.3697, 43.1296], total_capacity=1100, pop_size=25),
    dict(type="park", name="Brittingham Park", code="BRITT",
         location=[-89.3936, 43.0644], total_capacity=600, pop_size=25),
]


def _haversine_m(lon, lat, lons, lats):
    r = 6371008.8
    p1 = math.radians(lat)
    p2 = np.radians(lats)
    dphi = p2 - p1
    dlam = np.radians(lons - lon)
    h = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(h))


def _largest_remainder(weights, total):
    """Apportion `total` whole pops across `weights` without drift."""
    exact = weights * total
    alloc = np.floor(exact).astype(int)
    short = total - int(alloc.sum())
    if short > 0:
        for k in np.argsort(-(exact - alloc))[:short]:
            alloc[k] += 1
    return alloc


def _weighted_seat_sample(weights, seats, npops, seed):
    """
    Draw `npops` pops at random in proportion to `weights`, never exceeding a
    candidate's `seats`.

    Sampling rather than apportioning, because apportionment degenerates over a
    metro-wide pool: `_largest_remainder` floors almost every share to zero and
    then hands the pops to the highest-weight candidates, which under a distance
    decay means the nearest ones. Seeded, so a rebuild is reproducible.
    """
    rng = np.random.default_rng(seed)
    w = np.asarray(weights, dtype=float).copy()
    room = np.asarray(seats, dtype=int).copy()
    w[room <= 0] = 0.0
    alloc = np.zeros(w.size, dtype=int)
    for _ in range(int(npops)):
        total = w.sum()
        if total <= 0:
            break
        i = int(rng.choice(w.size, p=w / total))
        alloc[i] += 1
        if alloc[i] >= room[i]:
            w[i] = 0.0
    return alloc


def _seat_alloc(weights, seats, npops):
    """Apportion `npops` pops by `weights`, never exceeding `seats`."""
    npops = min(int(npops), int(seats.sum()))
    alloc = np.zeros(weights.size, dtype=int)
    left = npops
    while left > 0:
        room = seats - alloc
        open_ = room > 0
        if not open_.any():
            break
        w = weights * open_
        if w.sum() <= 0:
            break
        give = np.minimum(_largest_remainder(w / w.sum(), left), room)
        if give.sum() == 0:
            give[np.flatnonzero(open_)[:left]] = 1
        alloc += give
        left -= int(give.sum())
    return alloc


# --- Schools -----------------------------------------------------------------
# Wisconsin districts are municipal rather than county-wide, so attendance
# zones are tighter than the Charleston build's 5/8/12 miles.
MILE_M = 1609.344
CATCHMENT_M = {1: round(3 * MILE_M), 2: round(5 * MILE_M), 3: round(8 * MILE_M)}
CATCHMENT_DEFAULT_M = round(5 * MILE_M)
SCHOOL_POP_SIZE = 15
# Teachers are not zoned. Calibrated against the LODES commutes in the base
# demand, which are the real thing for this metro.
STAFF_EXPONENT = 0.8
# Ceiling on the share of a node's LODES residents that may be sent to school.
NODE_CAP = 0.75


def lodging():
    """
    Overnight visitors, clustered by where they sleep (special/lodging.json,
    built by fetch_lodging.py from OSM).

    Each cluster also carries the arriving air passengers heading for it, as
    `required_locs` entries pointing back at the airport, so those pops take the
    airport as their residence and the hotel as their destination. It has to be
    written from this end: required_locs only shapes a point's inbound job pops,
    never its outbound residents.
    """
    path = os.path.join(HERE, "lodging.json")
    if not os.path.exists(path):
        return []
    clusters = [c for c in json.load(open(path)) if in_bbox([c["lon"], c["lat"]])]
    if not clusters:
        return []

    def downtown(c):
        x0, y0, x1, y1 = DOWNTOWN_BBOX
        return x0 <= c["lon"] <= x1 and y0 <= c["lat"] <= y1

    core = [c for c in clusters if downtown(c)]
    rest = [c for c in clusters if not downtown(c)]
    core_pool = int(_lodging_bound * DOWNTOWN_SHARE)
    arrivals = {}
    for group, pool in ((core, core_pool), (rest, _lodging_bound - core_pool)):
        total = sum(c["visitors"] for c in group) or 1
        for c in group:
            arrivals[c["code"]] = int(pool * c["visitors"] / total)

    arrival_pop = 25
    codes = [c["code"] for c in clusters]
    weights = np.array([max(arrivals.get(k, 0), 0) for k in codes], dtype=float)
    npops = int(round(sum(arrivals.values()) / arrival_pop))
    pops_by_code = (dict(zip(codes, _largest_remainder(weights / weights.sum(), npops)))
                    if weights.sum() > 0 and npops > 0 else {k: 0 for k in codes})

    out = []
    for c in clusters:
        nreq = int(pops_by_code.get(c["code"], 0))
        capacity = c["visitors"] + nreq * arrival_pop
        out.append(dict(
            type="resort", name=f"Madison lodging {c['code']}", code=c["code"],
            location=[c["lon"], c["lat"]],
            total_capacity=capacity,
            required_locs=[list(AIRPORT_LOC)] * nreq,
            pop_size=25,
            pop_size_req=arrival_pop,
            pop_size_remain=25,
            residential_split=(c["visitors"] / capacity) if capacity else 0.0,
            exponent=1.5,
        ))
    return out


def schools(base_points, resident_baseline=None):
    """
    Schools from the NCES Common Core of Data (public) and Private School
    Universe Survey (private), filtered to the map bbox.

    Pupils are placed by attendance zone rather than by depot's gravity model.
    The gravity weight is residents / distance**exponent, and at the default
    school exponent of 2.5 over metres a node 0.5 km out outweighs one at 5 km
    by 316x, so a school collapses onto its one or two closest residential
    nodes -- which then ship more children than they have residents. Instead
    every residential node inside the catchment is passed as a `required_locs`
    entry in proportion to its residents.

    Schools are taken largest first against a running per-node budget, so a node
    inside several overlapping catchments cannot be oversubscribed by the
    combination, and the budget is measured against each node's LODES residents
    rather than its current count -- by the time schools are added the other
    special demand has already moved workers in.

    Staff are drawn metro-wide, since teachers are not zoned, but through the
    same seat-capped allocation rather than depot's gravity draw, which has no
    notion of capacity and would hand a three-resident node a whole pop.
    """
    path = os.path.join(HERE, "schools.json")
    if not os.path.exists(path):
        return []
    entries = [s for s in json.load(open(path))
               if s["students"] + s["staff"] >= 40 and in_bbox([s["lon"], s["lat"]])]

    resident_baseline = resident_baseline or {}
    locs = np.array([p["location"] for p in base_points], dtype=float)
    residents = np.array(
        [float(resident_baseline.get(p["id"], p["residents"])) for p in base_points],
        dtype=float)
    remaining = residents * NODE_CAP

    out = []
    for s in sorted(entries, key=lambda x: (-x["students"], x.get("code") or x["name"])):
        students, staff = s["students"], s["staff"]
        seed_key = str(s.get("code") or s["name"])
        level = s.get("level")
        radius = CATCHMENT_M.get(level if level in CATCHMENT_M else None,
                                 CATCHMENT_DEFAULT_M)
        psize = SCHOOL_POP_SIZE
        dist = _haversine_m(s["lon"], s["lat"], locs[:, 0], locs[:, 1])
        dist = np.where(dist == 0, 1e9, dist)
        required_locs = []

        npops = max(2, round(students / psize))
        mask = None
        for mult in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0):
            mask = (dist <= radius * mult) & (remaining >= psize)
            if int((remaining[mask] // psize).sum()) >= npops:
                break
        idx = np.flatnonzero(mask)
        n_pupil_pops = 0
        if idx.size:
            seats = (remaining[idx] // psize).astype(int)
            alloc = _seat_alloc(remaining[idx], seats, npops)
            n_pupil_pops = int(alloc.sum())
            for i, n in zip(idx, alloc):
                required_locs.extend([[float(locs[i][0]), float(locs[i][1])]] * int(n))
            remaining[idx] = np.maximum(0.0, remaining[idx] - alloc * psize)

        nstaff = int(round(staff / psize))
        if nstaff:
            sidx = np.flatnonzero(remaining >= psize)
            if sidx.size:
                w = residents[sidx] / dist[sidx] ** STAFF_EXPONENT
                w = np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0)
                w[dist[sidx] > 200000] = 0.0
                if w.sum() > 0:
                    seats = (remaining[sidx] // psize).astype(int)
                    alloc = _weighted_seat_sample(
                        w, seats, nstaff, seed=zlib.crc32(seed_key.encode()))
                    for i, n in zip(sidx, alloc):
                        required_locs.extend([[float(locs[i][0]), float(locs[i][1])]] * int(n))
                    remaining[sidx] = np.maximum(0.0, remaining[sidx] - alloc * psize)

        if not required_locs:
            continue
        out.append(dict(
            type="school", name=s["name"], location=[s["lon"], s["lat"]],
            code=s.get("code"),
            _n_pupil_pops=n_pupil_pops,
            total_capacity=psize * len(required_locs),
            required_locs=required_locs,
            pop_size=psize,
            pop_size_req=psize,
            pop_size_remain=psize,
            exponent=STAFF_EXPONENT,
            residential_split=0.0,
        ))
    return out


# Everything except the airport, lodging and schools. Applied first: several
# carry merge_within, which deletes the LODES points they absorb, and school
# catchments must be drawn against the point list that survives. The airport
# goes in on its own beforehand and lodging afterwards, because lodging's
# required_locs have to resolve to an AIR_MSN that already exists.
def non_school_pois():
    pois = []
    for g in (HOSPITALS, UNIVERSITIES, GOVERNMENT, EMPLOYERS, SPORTS,
              SHOPPING, ATTRACTIONS, PARKS):
        pois.extend(p for p in g if in_bbox(p["location"]))
    return pois


if __name__ == "__main__":
    import sys
    demand = sys.argv[1] if len(sys.argv) > 1 else "MSN_demand/demand_data.json"
    pts = []
    if os.path.exists(demand):
        pts = [p for p in json.load(open(demand))["points"] if p["id"].startswith("merged")]
    groups = [
        ("airport", AIRPORT), ("university", UNIVERSITIES), ("government", GOVERNMENT),
        ("employers", EMPLOYERS), ("hospital", HOSPITALS), ("sports/events", SPORTS),
        ("shopping", SHOPPING), ("culture", ATTRACTIONS), ("parks", PARKS),
        ("lodging", lodging()), ("school", schools(pts) if pts else []),
    ]
    print(f"{'group':<15}{'points':>8}{'capacity':>12}{'residents':>11}{'jobs':>10}")
    total = 0
    for name, g in groups:
        cap = sum(p["total_capacity"] for p in g)
        res = sum(int(p["total_capacity"] * p.get("residential_split", 0.0)) for p in g)
        print(f"{name:<15}{len(g):>8}{cap:>12,}{res:>11,}{cap - res:>10,}")
        total += cap
    print(f"{'TOTAL':<15}{sum(len(g) for _, g in groups):>8}{total:>12,}")
