#!/usr/bin/env python3
"""GitHub Actions arka plan görev betiği: Eindhoven Airport (EHEH) tarifesini çeker ve `data` dalındaki db/radar.db'yi günceller."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import radar_db
import radar_fids as fids


def main():
  adb_key = os.environ.get("AERODATABOX_KEY", "").strip()
  gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
  repo = os.environ.get("GITHUB_REPO", "").strip() or os.environ.get("GITHUB_REPOSITORY", "Blixembosch/atlas-flight-radar")
  host = os.environ.get("AERODATABOX_HOST", "").strip() or fids.ADB_HOST
  try:
    monthly = int(float(os.environ.get("ADB_MONTHLY_UNITS", str(fids.DEFAULT_MONTHLY_UNITS))))
  except (TypeError, ValueError):
    monthly = fids.DEFAULT_MONTHLY_UNITS

  if not adb_key:
    print("ℹ️ AERODATABOX_KEY tanımlı değil (GitHub Settings -> Secrets -> Actions altına ekleyebilirsiniz). Atlanıyor.")
    return 0
  if not gh_token:
    print("⚠️ GITHUB_TOKEN tanımlı değil. Atlanıyor.")
    return 0

  cfg = {
      "GITHUB_TOKEN": gh_token,
      "GITHUB_REPO": repo,
      "DATA_BRANCH": os.environ.get("DATA_BRANCH", "data"),
      "DATA_DB_PATH": os.environ.get("DATA_DB_PATH", "db/radar.db"),
      "DATA_SQL_PATH": os.environ.get("DATA_SQL_PATH", "db/radar.sql"),
      "DB_PUSH_MIN": "1",
  }
  db = radar_db.open_db(lambda k, d="": cfg.get(k, d), background=False)
  now = fids.now_local()
  bs = fids.budget_state(db, now, monthly)
  print(f"📊 Kota durumu: {bs['used']}/{bs['cap']} birim kullanıldı · kalan: {bs['remaining']} · aralık: {bs['interval_h']:.1f} sa")

  res = fids.refresh(db, adb_key, now, host=host, monthly_units=monthly)
  print(f"🔄 Tarife çekme sonucu: fetched={res.get('fetched')} · reason={res.get('reason')} · calls={res.get('calls')} · error={res.get('error')}")

  if res.get("fetched") or db.dirty:
    pushed = db.maybe_push(force=True, wait=True)
    sync = db.sync_status()
    print(f"☁️ GitHub '{sync['branch']}' dalına yedekleme: başlatıldı={pushed} · ok={sync['ok']} · hata={sync['error'] or 'yok'}")
    return 0 if sync["ok"] else 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
