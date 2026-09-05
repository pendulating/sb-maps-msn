"""
Build special/schools.json from NCES data, filtered to the map bbox.

Public schools come from the Common Core of Data via the Urban Institute's
Education Data API. Private schools come from the Private School Universe
Survey, which that API does not carry, so the NCES file is downloaded directly.

Capacity is students plus staff. NCES reports teachers as FTE, not total
employees, so staff is scaled by STAFF_PER_TEACHER -- nationally there are
roughly 6.4M public school employees against 3.1M teachers.

    python special/fetch_schools.py
"""
import csv
import io
import json
import os
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "schools.json")

BBOX = [-89.86, 42.83, -88.99, 43.30]
STAFF_PER_TEACHER = 1.9
CCD_YEAR = 2022          # the 2022-23 school year
CCD_URL = f"https://educationdata.urban.org/api/v1/schools/ccd/directory/{CCD_YEAR}/?fips=55"
PSS_URL = "https://nces.ed.gov/surveys/pss/zip/pss2122_pu_csv.zip"
CLOSED_STATUSES = {2, 6}          # closed, inactive
# CCD `virtual`: 1 = exclusively virtual, 3 = not virtual. A fully virtual
# school has an administrative address and no pupils travelling to it, so it
# must not become a demand point.
VIRTUAL_FULL = 1


def inside(lon, lat):
    return BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]


def fetch_public():
    out = []
    url = CCD_URL
    while url:
        with urllib.request.urlopen(url, timeout=120) as r:
            page = json.load(r)
        for s in page["results"]:
            lat, lon = s.get("latitude"), s.get("longitude")
            if not lat or not lon or not inside(lon, lat):
                continue
            if (s.get("school_status") or 0) in CLOSED_STATUSES:
                continue
            if s.get("virtual") == VIRTUAL_FULL:
                continue
            enrollment = s.get("enrollment") or 0
            if enrollment <= 0:
                continue
            out.append({
                "name": (s["school_name"] or "").strip(),
                # Names are not unique -- school names repeat across districts -- and the point id is built from the code, so
                # without one the second campus overwrites the first.
                "code": f"P{s['ncessch']}",
                "lon": lon, "lat": lat,
                "students": int(enrollment),
                "staff": int(round((s.get("teachers_fte") or 0) * STAFF_PER_TEACHER)),
                "level": s.get("school_level"),
                "sector": "public",
            })
        url = page.get("next")
    return out


def fetch_private():
    with urllib.request.urlopen(PSS_URL, timeout=300) as r:
        blob = r.read()
    zf = zipfile.ZipFile(io.BytesIO(blob))
    name = next(n for n in zf.namelist() if n.endswith(".csv"))
    out = []
    with zf.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="latin-1")
        for row in csv.DictReader(text):
            if (row.get("PSTABB") or "").strip().upper() != "WI":
                continue
            try:
                lat = float(row["LATITUDE22"])
                lon = float(row["LONGITUDE22"])
                students = int(float(row.get("NUMSTUDS") or 0))
                teachers = float(row.get("NUMTEACH") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if students <= 0 or not inside(lon, lat):
                continue
            out.append({
                "name": (row.get("PINST") or "").strip().title() or "Private School",
                "code": f"V{(row.get('PPIN') or '').strip() or len(out)}",
                "lon": lon, "lat": lat,
                "students": students,
                "staff": int(round(teachers * STAFF_PER_TEACHER)),
                "level": None,
                "sector": "private",
            })
    return out


if __name__ == "__main__":
    public = fetch_public()
    print(f"public schools in bbox:  {len(public):>4}")
    private = fetch_private()
    print(f"private schools in bbox: {len(private):>4}")

    schools = public + private
    with open(OUT, "w") as f:
        json.dump(schools, f, indent=1)

    students = sum(s["students"] for s in schools)
    staff = sum(s["staff"] for s in schools)
    print(f"\nwrote {OUT}")
    print(f"  {len(schools)} schools  {students:,} students  {staff:,} staff"
          f"  -> {students + staff:,} people")
