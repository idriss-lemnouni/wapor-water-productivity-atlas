"""Load a complete PostGIS snapshot and independently verify area statistics."""
from math import isclose
import json
import os
from time import perf_counter

import psycopg
from psycopg.types.json import Jsonb

from zonal import ROOT, collect, zone_records

AREA_CHECK = """
WITH clipped_cells AS (
    SELECT p.value, ST_Area(ST_Intersection(p.geom, z.geom)) AS overlap, ST_Area(z.geom) AS zone_area
    FROM atlas.pixels p JOIN atlas.zones z ON z.id = p.zone
    WHERE p.zone = %s AND p.asset = %s AND ST_Intersects(p.geom, z.geom)
)
SELECT count(*), sum(overlap) / max(zone_area), sum(value * overlap) / sum(overlap)
FROM clipped_cells WHERE overlap > 0;
"""


def connect():
    return psycopg.connect(host="127.0.0.1", port=55413, user="wapor", dbname="wapor",
                           password=os.environ["ATLAS_DB_PASSWORD"], connect_timeout=5)


def load(zones, summaries, pixels):
    with connect() as db:
        with db.cursor() as query:
            query.execute("SELECT pg_advisory_xact_lock(130023)")
            query.execute((ROOT / "schema.sql").read_text(encoding="utf-8"))
            query.execute("TRUNCATE atlas.pixels, atlas.summaries, atlas.zones")
            query.executemany("INSERT INTO atlas.zones VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 6933))",
                              zone_records(zones))
            query.executemany("INSERT INTO atlas.summaries VALUES (%s, %s, %s, %s, %s)",
                              [(r["zone"], r["year"], r["level"], r["indicator"], Jsonb(r)) for r in summaries])
            query.executemany("INSERT INTO atlas.pixels VALUES (%s, %s, ST_MakeEnvelope(%s, %s, %s, %s, 6933), %s)",
                              [(z, asset, *p) for (z, asset), rows in pixels.items() for p in rows])
            query.execute("ANALYZE atlas.pixels")
            elapsed = []
            errors = []
            for record in summaries:
                start = perf_counter()
                query.execute(AREA_CHECK, (record["zone"], record["code"]))
                count, coverage, mean = query.fetchone()
                elapsed.append((perf_counter() - start) * 1000)
                expected = record["weighted"]
                if count != record["valid_cells"] or not isclose(coverage or 0, record["coverage"], abs_tol=1e-8):
                    raise ValueError(f"SQL disagrees on coverage for {record['code']}, {record['zone']}")
                if mean is None or expected is None:
                    if mean is not expected:
                        raise ValueError("SQL and Python disagree about missing data")
                elif not isclose(mean, expected, abs_tol=1e-8):
                    raise ValueError(f"SQL disagrees on weighted mean for {record['code']}, {record['zone']}")
                else:
                    errors.append(abs(mean - expected))
            query.execute("SELECT PostGIS_Lib_Version(), current_setting('server_version')")
            postgis, postgres = query.fetchone()
            query.execute("SELECT count(*), bool_and(ST_SRID(geom) = 6933) FROM atlas.pixels")
            pixel_count, expected_crs = query.fetchone()
            if not expected_crs:
                raise ValueError("Stored pixels have an unexpected spatial reference")
    return {"postgis": postgis, "postgres": postgres, "pixel_rows": pixel_count, "validated_summaries": len(summaries),
            "max_abs_mean_difference": max(errors, default=0), "local_sql_ms": elapsed}


if __name__ == "__main__":
    zones, summaries, pixels = collect()
    proof = load(zones, summaries, pixels)
    out = ROOT / "runs"
    out.mkdir(exist_ok=True)
    for name, data in (("zonal-results.json", summaries), ("postgis-check.json", proof)):
        (out / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(proof, indent=2))
