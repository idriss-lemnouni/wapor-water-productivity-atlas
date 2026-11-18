"""Serve the atlas and its PostGIS-backed GeoJSON endpoint on loopback."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import parse_qs, urlsplit

import psycopg

from load_atlas import connect
from zonal import ROOT

QUERY = """
SELECT ST_AsGeoJSON(ST_Transform(z.geom, 4326))::json AS geometry, s.metrics AS properties
FROM atlas.summaries s JOIN atlas.zones z ON z.id = s.zone
WHERE year = %s AND level = %s AND indicator = %s ORDER BY z.id;
"""


def parse_filters(query):
    values = parse_qs(query, keep_blank_values=True)
    fields = {"year": {"2022", "2023"}, "level": {"L1", "L2"}, "indicator": {"AETI", "GBWP"}}
    if values.keys() != fields.keys() or any(len(values[key]) != 1 or values[key][0] not in allowed
                                             for key, allowed in fields.items()):
        raise ValueError("Select year 2022/2023, level L1/L2 and indicator AETI/GBWP.")
    return int(values["year"][0]), values["level"][0], values["indicator"][0]


class AtlasHandler(SimpleHTTPRequestHandler):
    def json_response(self, value, status=200):
        encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        target = urlsplit(self.path)
        if target.path != "/api/zones":
            return super().do_GET()
        try:
            filters = parse_filters(target.query)
        except ValueError as error:
            return self.json_response({"error": str(error)}, 400)
        try:
            with connect() as db:
                rows = db.execute(QUERY, filters).fetchall()
        except (KeyError, psycopg.Error):
            return self.json_response({"error": "The atlas database is unavailable."}, 503)
        features = [{"type": "Feature", "geometry": geometry, "properties": properties}
                    for geometry, properties in rows]
        return self.json_response({"type": "FeatureCollection", "features": features})


if __name__ == "__main__":
    handler = partial(AtlasHandler, directory=ROOT / "web")
    with ThreadingHTTPServer(("127.0.0.1", 8043), handler) as server:
        print("WaPOR atlas available at http://127.0.0.1:8043", flush=True)
        server.serve_forever()
