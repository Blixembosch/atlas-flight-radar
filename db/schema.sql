-- Atlas'ın Uçak Gözlem Kulesi · SQLite şeması (radar_db.py içindeki SCHEMA ile aynıdır)
-- Veritabanı dosyası (radar.db) `data` dalında tutulur; ana dala eklenmez.
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- Havalimanı tarifesi (varış/kalkış) önbelleği
CREATE TABLE IF NOT EXISTS fids_flights (
  key          TEXT PRIMARY KEY,
  direction    TEXT NOT NULL CHECK (direction IN ('ARR','DEP')),
  number       TEXT,
  callsign     TEXT,
  airline      TEXT,
  airline_iata TEXT,
  airline_icao TEXT,
  other_iata   TEXT,
  other_icao   TEXT,
  other_city   TEXT,
  other_cc     TEXT,
  sched_local  TEXT NOT NULL,
  est_local    TEXT,
  actual_local TEXT,
  status       TEXT,
  terminal     TEXT,
  gate         TEXT,
  aircraft     TEXT,
  reg          TEXT,
  first_seen   TEXT,
  updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_fids_dir_sched ON fids_flights (direction, sched_local);

-- Bahçeden görülen uçaklar (Gözlem Defteri)
CREATE TABLE IF NOT EXISTS sightings (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  day          TEXT NOT NULL,
  icao24       TEXT NOT NULL,
  callsign     TEXT NOT NULL DEFAULT '',
  airline      TEXT,
  airline_key  TEXT,
  airline_iata TEXT,
  type_code    TEXT,
  type_name    TEXT,
  reg          TEXT,
  direction    TEXT,
  origin_iata  TEXT,
  origin_city  TEXT,
  dest_iata    TEXT,
  dest_city    TEXT,
  first_seen   TEXT NOT NULL,
  last_seen    TEXT NOT NULL,
  min_dist_km  REAL,
  max_alt_ft   INTEGER,
  UNIQUE (day, icao24, callsign)
);
CREATE INDEX IF NOT EXISTS idx_sightings_day ON sightings (day);

-- Harici API kota sayacı (ay bazında)
CREATE TABLE IF NOT EXISTS api_usage (
  month    TEXT NOT NULL,
  provider TEXT NOT NULL,
  calls    INTEGER NOT NULL DEFAULT 0,
  units    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (month, provider)
);

-- Tarife çekme günlüğü
CREATE TABLE IF NOT EXISTS fetch_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT NOT NULL,
  provider  TEXT NOT NULL,
  win_from  TEXT,
  win_to    TEXT,
  ok        INTEGER NOT NULL,
  n_arr     INTEGER DEFAULT 0,
  n_dep     INTEGER DEFAULT 0,
  note      TEXT
);
