CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS atlas;
CREATE TABLE IF NOT EXISTS atlas.zones (
    id text PRIMARY KEY,
    name text NOT NULL,
    geom geometry(Polygon, 6933) NOT NULL CHECK (ST_IsValid(geom))
);
CREATE INDEX IF NOT EXISTS zones_geom ON atlas.zones USING gist (geom);
CREATE TABLE IF NOT EXISTS atlas.summaries (
    zone text REFERENCES atlas.zones,
    year integer NOT NULL,
    level text NOT NULL CHECK (level IN ('L1', 'L2')),
    indicator text NOT NULL CHECK (indicator IN ('AETI', 'GBWP')),
    metrics jsonb NOT NULL,
    PRIMARY KEY (year, level, indicator, zone)
);
CREATE TABLE IF NOT EXISTS atlas.pixels (
    zone text REFERENCES atlas.zones,
    asset text NOT NULL,
    geom geometry(Polygon, 6933) NOT NULL,
    value double precision NOT NULL CHECK (value >= 0)
);
CREATE INDEX IF NOT EXISTS pixels_geom ON atlas.pixels USING gist (geom);
CREATE INDEX IF NOT EXISTS pixels_asset_zone ON atlas.pixels (asset, zone);
