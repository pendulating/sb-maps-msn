# Madison, WI — Subway Builder map

Map of Madison, Wisconsin for [Subway Builder](https://subwaybuildermodded.com).
Originally by **muffintime** (crumpetime); this fork rebuilds the map data with
[depot](https://github.com/Subway-Builder-Modded/depot) and builds out the
special demand.

The playable area is `-89.86, 42.83 → -88.99, 43.30`, about 3,722 km². It was
derived rather than eyeballed: it holds all 36 incorporated places in Dane
County, 99% of the county's LODES activity by block group, and Epic's Verona
campus. The 3.0.0 map ran to 6,616 km², reaching south and east into
Janesville and Watertown, which belong to other metros rather than Madison's.

## What changed from 3.0.0

**The tiles were a Protomaps basemap with labels added.** They carried
`version 2` but none of the game's own layers — no `ocean_foundations`, and no
`commercial`, `hospital`, `industrial` or `residential` zoning. Rebuilt with
depot, they now have the full set, plus a building foundations layer the map
never had.

**Special demand was eight points**: the university, the airport, the technical
college and five entertainment sites. No schools, no hospitals, no state
government, and `AIR_KMSN` had 6,600 jobs against zero residents — a city with
departures and nobody arriving. It is now ~250 points.

**Pop granularity.** 48,129 pops for 327,350 people is 6.8 people per pop,
half the 13.8 median across the 50 US LODES maps in the registry, and the
simulation iterates pops rather than people.

| | 3.0.0 | this build |
| --- | --- | --- |
| extent | 6,616 km² | 3,722 km² |
| points | 2,101 | 1,565 |
| pops | 48,129 | 19,511 |
| people | 327,350 | 454,229 |
| people per pop | 6.8 | 23.3 |
| special demand points | 8 | ~250 |
| `MSN.pmtiles` | 43.8 MB | 26.6 MB |
| foundations layer | — | 13.6 MB |
| buildings index | 73 MB JSON | 36 MB binary |
| ocean depth | 4.2 MB uncompressed | 0.5 MB gz |
| archive | 66.7 MB | 63.3 MB |

## What ships

Release assets are a flat `MSN.zip` plus a `manifest.json` sidecar — Railyard
reads the sidecar to resolve game compatibility without downloading the
archive, and the 3.0.0 release had none.

| File | Purpose |
| --- | --- |
| `MSN.pmtiles` | Basemap tiles: water, landuse, roads, buildings, ocean foundations |
| `MSN_foundations.pmtiles` | Building foundations layer |
| `buildings_index.bin.gz` | Packed building collision index — what Railyard actually loads |
| `buildings_index.json.gz` | JSON form of the same index |
| `roads.geojson` | Road network |
| `runways_taxiways.geojson` | Aeroway geometry |
| `ocean_depth_index.json.gz` | Lake bathymetry — gates underwater track building |
| `ocean_depth_index_contours.json.gz` | Depth contours |
| `demand_data.json` | Population, jobs and commutes |
| `config.json` | Map metadata |
| `.railyard_map/special_demand_*.json` | Special demand type and point schema |

## Special demand

`build/special/pois.py` holds every point. Two conventions govern the numbers.

`merge_within` folds the nearby LODES block point into the special point, and
belongs wherever the site is a workplace LODES already counts. `residential_split`
is the share that *lives* at the point and travels out — how inbound travel is
modelled.

So capacity should be the trips LODES never sees. Campuses carry students, not
faculty. Hospitals carry patients, not nurses. Employers carry almost nothing
on top of the merge, because their whole workforce is already in LODES — what
makes them worth adding is that the merge gives the site a labelled, correctly
typed point instead of an anonymous block.

| Category | Points | Notes |
| --- | --- | --- |
| Schools | 220 | NCES CCD and PSS: real per-school enrolment, staff at teacher FTE × 1.9, pupils placed by 3/5/8-mile attendance zone |
| Lodging | 54 | OSM lodging, rooms × 70% occupancy × 1.9 guests, carrying the airport arrivals bound for each |
| Universities | 4 | UW-Madison at 45,000 students and a 0.17 residential split; Madison College Truax and South; Edgewood |
| Hospitals | 7 | Patients and visitors at ~2.5 per licensed bed |
| Employers | 5 | Epic, American Family, University Research Park, Exact Sciences, Promega |
| State government | 4 | Capitol, GEF complex, Hill Farms, City-County Building |
| Parks and lakes | 7 | Memorial Union Terrace, Olbrich, Vilas, Tenney, James Madison, Warner, Brittingham |
| Sport and events | 4 | Camp Randall, Kohl Center, Alliant Energy Center, Monona Terrace |
| Retail | 4 | West Towne, East Towne, Hilldale, South Towne |
| Culture | 5 | Overture, MMoCA, Chazen, Children's Museum, Vilas Zoo |
| Airport | 1 | ~6,000 daily passengers, split evenly, arrivals routed to hotels |

Madison is a college town and a state capital, and both show. UW-Madison is
the largest single thing on the map, and the state's own workforce is large
enough that leaving the Capitol as an unlabelled downtown block understates
what the isthmus is for.

### Why schools don't use the gravity model

depot places special demand by gravity, weighting a residential node by
`residents / distance ** exponent`. For schools that breaks down: distances are
metres and the default school exponent is 2.5, so a node 0.5 km out outweighs
one at 5 km by 316×, and a school collapses onto its one or two closest nodes,
which then ship more children than they have residents.

Schools are the one category whose destination has a legally defined catchment,
so every residential node inside the zone is passed as a `required_locs` entry
in proportion to its residents. Wisconsin districts are municipal rather than
county-wide, so the radii are 3/5/8 miles — tighter than the Charleston build.
Schools are placed largest-first against a running per-node budget so
overlapping catchments cannot oversubscribe a node, and that budget is measured
against LODES residents rather than the node's current count.

Staff are drawn metro-wide, since teachers are not zoned, but through the same
seat-capped allocation rather than depot's gravity draw — that draw has no
notion of capacity and will hand a three-resident node a whole pop.

## Building it

`depot/` and `us-demand/` are cloned in and gitignored.

```bash
cd us-demand                              # base LODES demand for the bbox
python create_US_demand_file.py Madison.json

cd ../build
python MSN.py all           # extract → buildings → roads → pmtiles → labels
python simplify_ocean.py    # shrink the lake depth index
python MSN_demand.py all    # seed → special demand → OSRM → commutes → config
python package.py           # assemble dist/MSN.zip
```

`package.py` runs a preflight that refuses to build an archive with unrouted
pops, duplicate point ids, a stale or duplicated special-demand schema, or a
config population that disagrees with the demand.

### Toolchain

depot needs `node`, `mapshaper`, `osmium`, `java`, `tippecanoe`, `tile-join`,
`sqlite3`, `jq`, `pmtiles`, `planetiler.jar` on `PATH`, plus `ogr2ogr` (GDAL),
which depot uses but does not check for. Docker is needed only for the demand
step's local OSRM server. `scikit-learn` and the `h2` extra on `httpx` are
imported by depot but missing from its `environment.yml`.

`DemandData.prepare_osrm` publishes `-p <port>:<port>`, but `osrm-routed`
listens on 5000 inside the container, so a non-default port never reaches it.
On macOS the AirPlay Receiver holds 5000, so start the router by hand:

```bash
docker run --name MSN -d -p 5050:5000 \
  -v "$PWD/MSN_demand:/data" ghcr.io/project-osrm/osrm-backend \
  osrm-routed --algorithm ch /data/MSN.osrm
```

### Inputs

- OSM: `wisconsin-latest.osm.pbf` from [Geofabrik](https://download.geofabrik.de/north-america/us/wisconsin.html)
- Buildings: Overture Maps, fetched by depot
- Bathymetry: GEBCO 2026 sub-ice grid, via CEDA OPeNDAP
- Demand: LODES 2023 origin-destination pairs via the US Demand Generator
- Schools: NCES Common Core of Data and Private School Universe Survey
- Lodging: OSM `tourism=hotel/motel/guest_house/hostel/apartment`. Only 6 of
  112 Madison entries carry a rooms tag, and OSM tags the big downtown hotels
  first, so `fetch_lodging.py` refuses to impute a median from fewer than 20
  samples — the six here gave a median of 129 rooms and a metro total of
  12,808, against a reality nearer 9,000.
- Boundaries: Census TIGER counties and block groups, for deriving the bbox

## Credits

Map by muffintime. Demand from slurry's
[US Demand Generator](https://github.com/rslurry/subwaybuilder-US-demand-data).
Schools from NCES. Rebuilt with
[depot](https://github.com/Subway-Builder-Modded/depot). Map data ©
OpenStreetMap contributors, Overture Maps Foundation, and GEBCO.
