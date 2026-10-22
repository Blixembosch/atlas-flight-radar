#!/usr/bin/env python3
"""Atlas Radar - SQL Veritabanı ve `data` Dalı Yönetim Aracı.

Bu araç, `main` kod dalını veriden tamamen bağımsız tutarak, SQLite veritabanının
ve düz metin SQL dökümünün (`db/radar.sql` ve `db/radar.db`) GitHub deposunun
özel `data` dalında saklanmasını ve yönetilmesini sağlar.

Kullanım:
  python3 scripts/manage_db.py status             # Yerel DB ve data dalı durumu
  python3 scripts/manage_db.py dump [--out DOSYA] # Yerel DB'yi SQL dökümüne aktar
  python3 scripts/manage_db.py restore [--in DOSYA]# SQL dökümünden yerel DB'yi kur
  python3 scripts/manage_db.py pull               # data dalındaki son DB'yi çek
  python3 scripts/manage_db.py push               # DB ve SQL dökümünü data dalına yükle
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import radar_db

DEFAULT_DB_FILE = ROOT / "db" / "radar.db"
DEFAULT_SQL_FILE = ROOT / "db" / "radar.sql"


def load_secrets() -> dict:
  """Streamlit secrets.toml veya ortam değişkenlerinden GitHub ayarlarını yükler."""
  cfg = {}
  secrets_file = ROOT / ".streamlit" / "secrets.toml"
  if secrets_file.exists():
    try:
      # Basit TOML anahtar-değer ayrıştırıcısı (ek bağımlılık gerektirmez)
      for line in secrets_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
          continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        cfg[k] = v
    except Exception as e:
      print(f"⚠️ secrets.toml okunurken uyarı: {e}")

  # Ortam değişkenleri secrets.toml'ı ezebilir
  for k in ("GITHUB_TOKEN", "GITHUB_REPO", "DATA_BRANCH", "DATA_DB_PATH", "DATA_SQL_PATH"):
    if os.environ.get(k):
      cfg[k] = os.environ[k]

  cfg.setdefault("GITHUB_REPO", "Blixembosch/atlasradar")
  cfg.setdefault("DATA_BRANCH", "data")
  cfg.setdefault("DATA_DB_PATH", "db/radar.db")
  cfg.setdefault("DATA_SQL_PATH", "db/radar.sql")
  return cfg


def cmd_status(args):
  cfg = load_secrets()
  print("=" * 60)
  print("🛫 ATLAS RADAR · SQL VERİTABANI VE DATA DALI DURUMU")
  print("=" * 60)

  # 1. Yerel Dosya Durumu
  db_path = Path(args.db or DEFAULT_DB_FILE)
  sql_path = Path(args.sql or DEFAULT_SQL_FILE)

  print(f"\n📂 Yerel Dosyalar:")
  if db_path.exists():
    size_kb = db_path.stat().st_size / 1024
    print(f"  • SQLite DB : {db_path} ({size_kb:.1f} KB) ✅ Mevcut")
  else:
    print(f"  • SQLite DB : {db_path} ⚠️ Yok (ilk çalıştırmada oluşturulur)")

  if sql_path.exists():
    size_kb = sql_path.stat().st_size / 1024
    lines = len(sql_path.read_text(encoding="utf-8").splitlines())
    print(f"  • SQL Döküm : {sql_path} ({size_kb:.1f} KB, {lines} satır) ✅ Mevcut")
  else:
    print(f"  • SQL Döküm : {sql_path} ℹ️ Yok ('dump' komutuyla üretilebilir)")

  # 2. Veritabanı İçerik Özeti
  if db_path.exists():
    try:
      db = radar_db.RadarDB(db_path)
      with db.tx(write=False) as con:
        one = lambda q: con.execute(q).fetchone()[0]
        n_sight = one("SELECT COUNT(*) FROM sightings")
        n_fids = one("SELECT COUNT(*) FROM fids_flights")
        n_usage = one("SELECT COUNT(*) FROM api_usage")
        n_days = one("SELECT COUNT(DISTINCT day) FROM sightings")
      print(f"\n📊 Veri İstatistikleri:")
      print(f"  • Gözlem Defteri (sightings) : {n_sight} kayıt ({n_days} farklı gün)")
      print(f"  • Uçuş Tarifesi (fids)       : {n_fids} uçuş")
      print(f"  • Harici API Kota Sayaçları  : {n_usage} sağlayıcı/ay")
    except Exception as e:
      print(f"  ⚠️ Tablolar okunurken hata: {e}")

  # 3. GitHub data Dalı Durumu
  print(f"\n☁️ GitHub 'data' Dalı Yapılandırması:")
  print(f"  • Depo   : {cfg.get('GITHUB_REPO')}")
  print(f"  • Dal    : {cfg.get('DATA_BRANCH')}")
  print(f"  • DB Yolu: {cfg.get('DATA_DB_PATH')}")
  print(f"  • SQL Yol: {cfg.get('DATA_SQL_PATH')}")
  if cfg.get("GITHUB_TOKEN"):
    print(f"  • Token  : Tanımlı (***{cfg.get('GITHUB_TOKEN')[-4:]}) ✅")
  else:
    print("  • Token  : ⚠️ Tanımlı DEĞİL (yalnızca yerel mod)")
  print("=" * 60)
  return 0


def cmd_dump(args):
  db_path = Path(args.db or DEFAULT_DB_FILE)
  sql_path = Path(args.out or DEFAULT_SQL_FILE)

  if not db_path.exists():
    print(f"❌ Hata: Kaynak veritabanı bulunamadı: {db_path}")
    return 1

  print(f"⏳ Veritabanı dökümü alınıyor: {db_path} -> {sql_path}...")
  sql_text = radar_db.dump_sql(db_path)
  if not sql_text:
    print("❌ Döküm alınamadı (boş veri).")
    return 1

  sql_path.parent.mkdir(parents=True, exist_ok=True)
  sql_path.write_text(sql_text, encoding="utf-8")
  size_kb = sql_path.stat().st_size / 1024
  lines = len(sql_text.splitlines())
  print(f"✅ Başarılı! {sql_path} yazıldı ({size_kb:.1f} KB, {lines} satır).")
  return 0


def cmd_restore(args):
  sql_path = Path(args.input or DEFAULT_SQL_FILE)
  db_path = Path(args.db or DEFAULT_DB_FILE)

  if not sql_path.exists():
    print(f"❌ Hata: SQL döküm dosyası bulunamadı: {sql_path}")
    return 1

  print(f"⏳ SQL dökümünden veritabanı kuruluyor: {sql_path} -> {db_path}...")
  sql_text = sql_path.read_text(encoding="utf-8")
  ok = radar_db.restore_sql(sql_text, db_path)
  if not ok:
    print("❌ Geri yükleme başarısız! SQL sözdizimi veya veritabanı hatası.")
    return 1

  print(f"✅ Başarılı! {db_path} veritabanı yeniden kuruldu.")
  return 0


def cmd_pull(args):
  cfg = load_secrets()
  if not cfg.get("GITHUB_TOKEN"):
    print("❌ Hata: GitHub'dan çekmek için GITHUB_TOKEN gereklidir.")
    return 1

  db_path = Path(args.db or DEFAULT_DB_FILE)
  print(f"☁️ GitHub '{cfg['DATA_BRANCH']}' dalından veritabanı çekiliyor...")
  db = radar_db.open_db(lambda k, d="": cfg.get(k, d), path=db_path, background=False)
  status = db.startup_sync()
  sync = db.sync_status()

  if sync["ok"]:
    print(f"✅ Çekme başarılı! Sonuç: {status}")
    # Otomatik yerel SQL dökümünü de güncelle
    sql_path = Path(args.sql or DEFAULT_SQL_FILE)
    cmd_dump(args)
    return 0
  else:
    print(f"❌ Çekme başarısız: {sync.get('error') or status}")
    return 1


def cmd_push(args):
  cfg = load_secrets()
  if not cfg.get("GITHUB_TOKEN"):
    print("❌ Hata: GitHub'a yüklemek için GITHUB_TOKEN gereklidir.")
    return 1

  db_path = Path(args.db or DEFAULT_DB_FILE)
  if not db_path.exists():
    print(f"❌ Hata: Yüklenecek veritabanı bulunamadı: {db_path}")
    return 1

  print(f"⏳ Önce güncel SQL dökümü üretiliyor...")
  cmd_dump(args)

  print(f"☁️ GitHub '{cfg['DATA_BRANCH']}' dalına SQLite DB + SQL dökümü yükleniyor...")
  db = radar_db.open_db(lambda k, d="": cfg.get(k, d), path=db_path, background=False)
  pushed = db.maybe_push(force=True, wait=True)
  sync = db.sync_status()

  if sync["ok"]:
    print(f"✅ Başarıyla GitHub '{cfg['DATA_BRANCH']}' dalına yüklendi! (başlatıldı={pushed})")
    return 0
  else:
    print(f"❌ Yükleme başarısız: {sync.get('error')}")
    return 1


def main():
  base_p = argparse.ArgumentParser(add_help=False)
  base_p.add_argument("--db", help=f"SQLite dosya yolu (varsayılan: {DEFAULT_DB_FILE})")
  base_p.add_argument("--sql", help=f"SQL döküm dosya yolu (varsayılan: {DEFAULT_SQL_FILE})")

  p = argparse.ArgumentParser(parents=[base_p], description="Atlas Radar SQL Veritabanı ve data Dalı Yöneticisi")
  sub = p.add_subparsers(dest="command")

  sub.add_parser("status", parents=[base_p], help="Yerel DB ve data dalı durumunu incele")

  p_dump = sub.add_parser("dump", parents=[base_p], help="Yerel DB'den SQL dökümü oluştur")
  p_dump.add_argument("--out", help="Çıktı SQL dosya yolu")

  p_rest = sub.add_parser("restore", parents=[base_p], help="SQL dökümünden yerel DB'yi kur")
  p_rest.add_argument("--in", dest="input", help="Girdi SQL dosya yolu")

  sub.add_parser("pull", parents=[base_p], help="GitHub data dalındaki veritabanını çek")
  sub.add_parser("push", parents=[base_p], help="Yerel DB ve SQL dökümünü GitHub data dalına yükle")

  args = p.parse_args()
  cmd = args.command or "status"

  handlers = {
      "status": cmd_status,
      "dump": cmd_dump,
      "restore": cmd_restore,
      "pull": cmd_pull,
      "push": cmd_push,
  }
  return handlers[cmd](args)


if __name__ == "__main__":
  sys.exit(main())
