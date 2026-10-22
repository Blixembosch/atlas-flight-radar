#!/usr/bin/env python3
"""Atlas Radar - SQL Veritabanı ve data Dalı Ayrımı Test Paketi.

Bu test paketi:
1. SQLite veritabanının düz metin SQL dökümüne (`dump_sql`) dönüştürülmesini
2. SQL dökümünden SQLite veritabanının atomik olarak kurulmasını (`restore_sql`)
3. `data` dalında hem `db/radar.db` hem de `db/radar.sql` dosyalarının senkronizasyonunu
4. Yalnızca SQL dökümü mevcut olduğunda açılışta otomatik geri yüklemeyi (`sql_ok`)
5. `scripts/manage_db.py` yönetim aracının (status, dump, restore) doğruluğunu
test eder.
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import radar_db as R
from fakes import FakeGH

FAILS = []
def ck(name, cond, info=""):
  msg = ("OK   " if cond else "FAIL ") + name
  if info and not cond:
    msg += f" [{info}]"
  print(msg)
  if not cond:
    FAILS.append(name)


def main():
  print("== test_sql_db_sync (Düz Metin SQL DB ve data Dalı Senkronizasyonu)")

  # 1. dump_sql doğrulaması
  d = tempfile.mkdtemp()
  db_file = os.path.join(d, "test.db")
  db = R.RadarDB(db_file)
  db.meta_set(project="Atlas_Flight", version="0.4.9")
  db.upsert_fids([{
      "key": "arr_1",
      "direction": "ARR",
      "number": "HV 5001",
      "callsign": "TRA5001",
      "airline": "Transavia",
      "sched_local": "2026-10-23T10:00",
      "status": "expected",
  }], "2026-10-23T09:00")
  db.record_sightings([{
      "day": "2026-10-23",
      "icao24": "485123",
      "callsign": "TRA5001",
      "airline": "Transavia",
      "type_code": "B738",
      "type_name": "Boeing 737-800",
      "dist_km": 2.1,
      "alt_ft": 1800,
  }], "2026-10-23T10:05")

  sql_text = R.dump_sql(db)
  ck("dump_sql içerik üretir", bool(sql_text) and len(sql_text) > 100)
  ck("dump_sql CREATE TABLE içerir", "CREATE TABLE" in sql_text)
  ck("dump_sql fids_flights tablosu var", "fids_flights" in sql_text)
  ck("dump_sql sightings tablosu var", "sightings" in sql_text)
  ck("dump_sql kayıtlar aktarılmış", "TRA5001" in sql_text and "Atlas_Flight" in sql_text)
  ck("dump_sql idx_sightings_last_seen içerir", "idx_sightings_last_seen" in sql_text)

  # 2. restore_sql doğrulaması
  db_restored_file = os.path.join(d, "restored.db")
  ok = R.restore_sql(sql_text, db_restored_file)
  ck("restore_sql başarılı döner", ok is True)
  ck("restored.db dosyası oluştu", os.path.exists(db_restored_file))

  db2 = R.RadarDB(db_restored_file)
  ck("geri yüklenen meta değeri doğru", db2.meta_get("project") == "Atlas_Flight")
  ck("geri yüklenen fids kaydı doğru", len(db2.fids_between("ARR", "2000", "2100")) == 1)
  st2 = db2.sighting_stats("2026-10-23", "2026-10-16")
  ck("geri yüklenen gözlem defteri doğru", st2["today"] == 1 and st2["top_airline"][0] == "Transavia")

  # Bozuk SQL reddedilmeli
  bad_file = os.path.join(d, "bad.db")
  ck("bozuk SQL reddedilir", R.restore_sql("NOT VALID SQL STATEMENT", bad_file) is False)
  ck("boş SQL reddedilir", R.restore_sql("", bad_file) is False)

  # 3. GitHub data Dalı: SQLite DB + SQL Dökümü Birlikte Yüklenir
  gh = FakeGH(branch=False)
  git_store = R.GitStore("tok", "o/r", branch="data", path="db/radar.db", sql_path="db/radar.sql", http=gh)
  db3 = R.RadarDB(os.path.join(d, "db3.db"), git=git_store)
  db3.startup_sync()
  db3.meta_set(test_push=1)
  pushed = db3.maybe_push(force=True, wait=True)
  ck("data dalına push başarılı", pushed is True)
  ck("FakeGH data dalı açıldı", gh.branch is True)
  ck("data dalında radar.db mevcut", "db/radar.db" in gh.files or (gh.data and gh.data.startswith(R.SQLITE_MAGIC)))
  ck("data dalında radar.sql dökümü mevcut", "db/radar.sql" in gh.files)
  if "db/radar.sql" in gh.files:
    sql_raw = gh.files["db/radar.sql"][0].decode("utf-8")
    ck("data dalındaki SQL geçerli", "CREATE TABLE" in sql_raw and "test_push" in sql_raw)

  # 4. Yalnızca SQL Dökümü Varken Açılışta Otomatik Kurulum (sql_ok modu)
  gh_sql_only = FakeGH(branch=True)
  # db/radar.db 404, db/radar.sql mevcut
  gh_sql_only.files["db/radar.sql"] = (sql_text.encode("utf-8"), "sha_sql_1")
  git_sql_only = R.GitStore("tok", "o/r", branch="data", path="db/radar.db", sql_path="db/radar.sql", http=gh_sql_only)
  db_sql_only = R.RadarDB(os.path.join(d, "from_sql_only.db"), git=git_sql_only)
  sync_res = db_sql_only.startup_sync()
  ck("yalnızca SQL varken startup_sync ok döner", sync_res == "ok")
  ck("SQL'den ayağa kalkan DB meta okur", db_sql_only.meta_get("project") == "Atlas_Flight")

  # 5. scripts/manage_db.py Komut Satırı Testi
  proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
  manage_py = os.path.join(proj_root, "scripts", "manage_db.py")

  # status
  res_stat = subprocess.run([sys.executable, manage_py, "status", "--db", db_file],
                            capture_output=True, text=True, cwd=proj_root)
  ck("manage_db.py status komutu çalışır", res_stat.returncode == 0 and "ATLAS RADAR" in res_stat.stdout)

  # dump
  out_sql = os.path.join(d, "cli_dump.sql")
  res_dump = subprocess.run([sys.executable, manage_py, "dump", "--db", db_file, "--out", out_sql],
                            capture_output=True, text=True, cwd=proj_root)
  ck("manage_db.py dump komutu çalışır", res_dump.returncode == 0 and os.path.exists(out_sql))

  # restore
  cli_db = os.path.join(d, "cli_restored.db")
  res_rest = subprocess.run([sys.executable, manage_py, "restore", "--db", cli_db, "--in", out_sql],
                            capture_output=True, text=True, cwd=proj_root)
  ck("manage_db.py restore komutu çalışır", res_rest.returncode == 0 and os.path.exists(cli_db))

  print("\nBAŞARISIZ:", FAILS if FAILS else "yok")
  return 1 if FAILS else 0


if __name__ == "__main__":
  sys.exit(main())
