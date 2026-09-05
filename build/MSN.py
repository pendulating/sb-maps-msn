"""
Rebuild of the Madison, WI map (MSN) for Subway Builder using depot.

Bounding box: -89.86, 42.83 -> -88.99, 43.30, about 3,722 km2.

Derived rather than eyeballed. It holds all 36 incorporated places in Dane
County, 99% of the county's LODES activity by block group, and Epic's Verona
campus, while dropping the southern and eastern fringe of the 3.0.0 map --
Janesville, Watertown -- which belong to other metros rather than Madison's.
That is 56% of the previous area, and close to the extent that plays well on
the comparable Charleston map.

Run a single stage:   python MSN.py <stage>
Stages: extract | labels | buildings | roads | pmtiles | addlabels | all
"""
import os
import sys

from depot.maps import MapGen

HERE = os.path.dirname(os.path.abspath(__file__))
OSMPBF = os.path.join(HERE, "wisconsin-latest.osm.pbf")

obj = MapGen(
    city="MSN",
    bbox=[-89.86, 42.83, -88.99, 43.30],
    osmpbf=OSMPBF,
    outputdir=HERE,
    # Madison is low-rise outside the isthmus; keep small buildings so the
    # downtown core and the campus stay dense.
    building_index_filter_size=40,
    redownload_buildings=True,
    building_tile_filter_size=None,
    building_index_simplification=1,
    building_tile_simplification=1,
    # The gameplay layers the 3.0.0 tiles lack entirely: that map is a
    # Protomaps basemap with labels bolted on, so it has no ocean_foundations
    # and none of the commercial/industrial/residential zoning layers.
    create_building_foundations=True,
    create_ocean_foundations=True,
    # US label preset from the depot README. No 'island' here -- unlike
    # Charleston, Madison's water is lakes, and the named places are the
    # isthmus neighbourhoods.
    cities=["city", "borough", "town"],
    suburbs=["suburb", "village"],
    neighborhoods=["neighbourhood", "hamlet", "quarter", "locality"],
    maxzoom=15,
    ncores=10,
    RAM=8,
    cleanup_files=False,
    verb=True,
)

STAGES = {
    "extract": obj.extract_base_data,
    "labels": obj.check_labels,
    "buildings": obj.process_buildings,
    "roads": obj.process_roads_and_aeroways,
    "pmtiles": obj.generate_pmtiles,
    "addlabels": obj.add_labels,
    "all": obj.run_all,
}

if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage not in STAGES:
        raise SystemExit(f"unknown stage {stage!r}; pick one of {', '.join(STAGES)}")
    print(f"===== MSN stage: {stage} =====", flush=True)
    STAGES[stage]()
    print(f"===== MSN stage {stage} complete =====", flush=True)
