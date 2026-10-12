"""
Atlas'ın Uçak Gözlem Kulesi - veritabanı katmanı.

* SQLite dosyası: db/radar.db
* Streamlit Cloud'da dosya sistemi kalıcı olmadığı için veritabanı, GitHub deposunun
  `data` dalında (db/radar.db) saklanır. Uygulama açılırken oradan çekilir, değişince
  belirli aralıklarla (varsayılan 20 dk) arka planda geri yüklenir. `data` dalına yazmak
  uygulamanın yeniden dağıtılmasını (redeploy) tetiklemez.
* GITHUB_TOKEN tanımlı değilse yalnızca yerel dosya kullanılır.

Güvenlik kuralı: ilk çekme (pull) başarılı olmadan uzaktaki veritabanının üzerine ASLA yazılmaz.
"""
from __future__ import annotations

import base64
import os
import sqlite3
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1
SQLITE_MAGIC = b"SQLite format 3\x00"
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "db" / "radar.db"
GITHUB_API = "https://api.github.com"

SCHEMA = """
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
"""

FIDS_COLS = (
    "key", "direction", "number", "callsign", "airline", "airline_iata", "airline_icao",
    "other_iata", "other_icao", "other_city", "other_cc", "sched_local", "est_local",
    "actual_local", "status", "terminal", "gate", "aircraft", "reg",
)
# Yeni veri boşsa eski değer korunsun (ör. kapı bilgisi sonradan kaybolmasın)
_KEEP_OLD = {"callsign", "airline_iata", "airline_icao", "other_iata", "other_icao", "other_city",
             "other_cc", "actual_local", "terminal", "gate", "aircraft", "reg"}
_IDENTITY = {"key", "direction", "sched_local"}

SIGHT_COLS = (
    "day", "icao24", "callsign", "airline", "airline_key", "airline_iata", "type_code", "type_name",
    "reg", "direction", "origin_iata", "origin_city", "dest_iata", "dest_city",
)


class GitError(Exception):
  """GitHub API hatası (mesajda token asla yer almaz)."""


# =============================================================================
# GitHub `data` dalı
# =============================================================================
class GitStore:
  """Tek bir dosyayı (db/radar.db) GitHub deposunun `data` dalında saklar."""

  def __init__(self, token, repo, branch="data", path="db/radar.db", http=None, extra_files=None):
    if http is None:
      import requests as http  # noqa: PLC0415 (testlerde stdlib ile çalışsın diye geç yüklenir)
    self.http = http
    self.extra_files = dict(extra_files or {})   # yalnızca dal ilk kurulurken eklenir (ör. db/schema.sql)
    self._token = token
    self.repo = repo
    self.branch = branch
    self.path = path
    self.sha = None            # uzaktaki dosyanın blob sha'sı
    self.branch_exists = False
    self.synced_ok = False     # ilk çekme başarıyla bitmeden push YOK
    self.last_error = ""

  # ---- düşük seviye
  def _api(self, method, path, **kw):
    headers = {
        "Authorization": f"Bearer {self._token}",
        "Accept": kw.pop("accept", "application/vnd.github+json"),
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "atlas-radar",
    }
    try:
      return self.http.request(method, GITHUB_API + path, headers=headers, timeout=20, **kw)
    except Exception as e:  # ağ hatası; token içermesin diye yalnızca sınıf adı
      raise GitError(f"GitHub'a ulaşılamadı ({type(e).__name__})") from None

  @staticmethod
  def _explain(r):
    code = r.status_code
    if code in (401, 403):
      return f"GitHub yetki hatası ({code}): token geçersiz ya da 'Contents: read & write' izni yok"
    if code == 404:
      return "GitHub 404: depo adı yanlış ya da token bu depoya erişemiyor"
    return f"GitHub hata kodu {code}"

  def _contents(self, raw=False):
    return self._api("GET", f"/repos/{self.repo}/contents/{self.path}",
                     params={"ref": self.branch},
                     accept="application/vnd.github.raw+json" if raw else "application/vnd.github+json")

  # ---- çekme
  def pull(self):
    """('ok', bytes) | ('empty', None) | ('error', None)."""
    try:
      repo_r = self._api("GET", f"/repos/{self.repo}")
      if repo_r.status_code != 200:
        self.last_error = self._explain(repo_r)
        return "error", None
      r = self._contents()
      if r.status_code == 404:
        ref = self._api("GET", f"/repos/{self.repo}/git/ref/heads/{self.branch}")
        if ref.status_code not in (200, 404):
          self.last_error = self._explain(ref)
          return "error", None
        self.branch_exists = ref.status_code == 200
        self.sha = None
        self.synced_ok = True
        self.last_error = ""
        return "empty", None
      if r.status_code != 200:
        self.last_error = self._explain(r)
        return "error", None
      js = r.json()
      data = None
      if js.get("encoding") == "base64" and js.get("content"):
        data = base64.b64decode(js["content"])
      else:  # 1 MB üstü dosyalarda içerik JSON'da gelmez
        raw = self._contents(raw=True)
        if raw.status_code != 200:
          self.last_error = self._explain(raw)
          return "error", None
        data = raw.content
      if not data.startswith(SQLITE_MAGIC):
        self.last_error = "data dalındaki dosya geçerli bir SQLite veritabanı değil"
        return "error", None
      self.sha = js.get("sha")
      self.branch_exists = True
      self.synced_ok = True
      self.last_error = ""
      return "ok", data
    except GitError as e:
      self.last_error = str(e)
      return "error", None

  # ---- yükleme
  def push(self, data, message):
    if not self.synced_ok:
      self.last_error = "Önce uzaktaki veritabanı çekilmeli (veri kaybını önlemek için)"
      return False
    try:
      if not self.branch_exists:
        return self._create_branch(data, message)
      return self._put(data, message)
    except GitError as e:
      self.last_error = str(e)
      return False

  def _put(self, data, message, retry=True):
    body = {"message": message, "content": base64.b64encode(data).decode(), "branch": self.branch}
    if self.sha:
      body["sha"] = self.sha
    r = self._api("PUT", f"/repos/{self.repo}/contents/{self.path}", json=body)
    if r.status_code in (200, 201):
      self.sha = (r.json().get("content") or {}).get("sha", self.sha)
      self.last_error = ""
      return True
    if r.status_code in (409, 422) and retry:  # sha eski kalmış: güncelini al, bir kez daha dene
      cur = self._contents()
      self.sha = cur.json().get("sha") if cur.status_code == 200 else None
      return self._put(data, message, retry=False)
    self.last_error = self._explain(r)
    return False

  def _create_branch(self, data, message):
    """Yalnızca db/radar.db içeren, ana koddan bağımsız (kök) bir `data` dalı oluşturur."""
    base = f"/repos/{self.repo}/git"
    b = self._api("POST", f"{base}/blobs",
                  json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
    if b.status_code != 201:
      self.last_error = self._explain(b)
      return False
    blob_sha = b.json()["sha"]
    entries = [{"path": self.path, "mode": "100644", "type": "blob", "sha": blob_sha}]
    for p, content in self.extra_files.items():
      eb = self._api("POST", f"{base}/blobs",
                     json={"content": base64.b64encode(content).decode(), "encoding": "base64"})
      if eb.status_code == 201:
        entries.append({"path": p, "mode": "100644", "type": "blob", "sha": eb.json()["sha"]})
    t = self._api("POST", f"{base}/trees", json={"tree": entries})
    if t.status_code != 201:
      self.last_error = self._explain(t)
      return False
    c = self._api("POST", f"{base}/commits",
                  json={"message": message, "tree": t.json()["sha"], "parents": []})
    if c.status_code != 201:
      self.last_error = self._explain(c)
      return False
    ref = self._api("POST", f"{base}/refs",
                    json={"ref": f"refs/heads/{self.branch}", "sha": c.json()["sha"]})
    if ref.status_code != 201:
      self.last_error = self._explain(ref)
      return False
    self.branch_exists = True
    self.sha = blob_sha
    self.last_error = ""
    return True


# =============================================================================
# Veritabanı
# =============================================================================
class RadarDB:
  def __init__(self, path=DEFAULT_DB_PATH, git=None, push_interval_s=1200):
    self.path = Path(path)
    try:
      self.path.parent.mkdir(parents=True, exist_ok=True)
      probe = self.path.parent / ".write_test"
      probe.write_text("ok")
      probe.unlink()
    except OSError:  # depo klasörü yazılamıyorsa geçici klasöre düş (veri GitHub'dan zaten geri gelir)
      self.path = Path(tempfile.gettempdir()) / "atlasradar" / self.path.name
      self.path.parent.mkdir(parents=True, exist_ok=True)
    self.git = git
    self.push_interval = push_interval_s
    self.lock = threading.RLock()
    self.fetch_lock = threading.Lock()   # tarife çekmeyi oturumlar arasında tekilleştirir
    self._push_lock = threading.Lock()
    self._push_thread = None
    self.dirty = False
    self.write_seq = 0
    self.last_push = 0.0
    self.last_push_ok = 0.0
    self.init_schema()

  # ---- bağlantı
  def connect(self):
    con = sqlite3.connect(str(self.path), timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=DELETE")  # tek dosya: GitHub'a yüklemek kolay
    return con

  @contextmanager
  def tx(self, write=True):
    with self.lock:
      con = self.connect()
      try:
        yield con
        con.commit()
        if write:
          self.dirty = True
          self.write_seq += 1
      except Exception:
        con.rollback()
        raise
      finally:
        con.close()

  def init_schema(self):
    with self.tx(write=False) as con:
      con.executescript(SCHEMA)
      con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
                  (str(SCHEMA_VERSION),))

  # ---- meta
  def meta_get(self, key, default=None):
    with self.tx(write=False) as con:
      row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

  def meta_set(self, **kv):
    with self.tx() as con:
      for k, v in kv.items():
        con.execute("INSERT INTO meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, None if v is None else str(v)))

  # ---- tarife
  def upsert_fids(self, rows, now_iso):
    if not rows:
      return 0
    cols = ", ".join(FIDS_COLS)
    ph = ", ".join("?" for _ in FIDS_COLS)
    sets = []
    for c in FIDS_COLS:
      if c in _IDENTITY:
        continue
      if c in _KEEP_OLD:
        sets.append(f"{c}=COALESCE(excluded.{c}, fids_flights.{c})")
      else:
        sets.append(f"{c}=excluded.{c}")
    sql = (f"INSERT INTO fids_flights ({cols}, first_seen, updated_at) VALUES ({ph}, ?, ?) "
           f"ON CONFLICT(key) DO UPDATE SET {', '.join(sets)}, updated_at=excluded.updated_at")
    with self.tx() as con:
      for r in rows:
        con.execute(sql, [r.get(c) for c in FIDS_COLS] + [now_iso, now_iso])
    return len(rows)

  def fids_between(self, direction, from_iso, to_iso):
    with self.tx(write=False) as con:
      cur = con.execute(
          "SELECT *, updated_at FROM fids_flights WHERE direction=? AND sched_local BETWEEN ? AND ? "
          "ORDER BY sched_local", (direction, from_iso, to_iso))
      return [dict(r) for r in cur.fetchall()]

  def prune(self, before_iso):
    """Eski tarife kayıtlarını ve eski çekme günlüklerini temizler."""
    with self.tx() as con:
      con.execute("DELETE FROM fids_flights WHERE sched_local < ?", (before_iso,))
      con.execute("DELETE FROM fetch_log WHERE ts < ?", (before_iso,))

  # ---- kota / günlük
  def usage(self, month, provider):
    with self.tx(write=False) as con:
      row = con.execute("SELECT calls, units FROM api_usage WHERE month=? AND provider=?",
                        (month, provider)).fetchone()
    return (row["calls"], row["units"]) if row else (0, 0)

  def add_usage(self, month, provider, calls, units):
    with self.tx() as con:
      con.execute(
          "INSERT INTO api_usage(month, provider, calls, units) VALUES(?,?,?,?) "
          "ON CONFLICT(month, provider) DO UPDATE SET calls=calls+excluded.calls, units=units+excluded.units",
          (month, provider, calls, units))

  def log_fetch(self, ts, provider, win_from, win_to, ok, n_arr=0, n_dep=0, note=""):
    with self.tx() as con:
      con.execute("INSERT INTO fetch_log(ts, provider, win_from, win_to, ok, n_arr, n_dep, note) "
                  "VALUES(?,?,?,?,?,?,?,?)", (ts, provider, win_from, win_to, int(ok), n_arr, n_dep, note))

  # ---- gözlemler
  def record_sightings(self, items, now_iso):
    """items: sözlük listesi (day, icao24, callsign, ... , dist_km, alt_ft)."""
    if not items:
      return 0
    cols = ", ".join(SIGHT_COLS)
    ph = ", ".join("?" for _ in SIGHT_COLS)
    sql = (f"INSERT INTO sightings ({cols}, first_seen, last_seen, min_dist_km, max_alt_ft) "
           f"VALUES ({ph}, ?, ?, ?, ?) "
           "ON CONFLICT(day, icao24, callsign) DO UPDATE SET "
           "last_seen=excluded.last_seen, "
           "min_dist_km=MIN(COALESCE(sightings.min_dist_km, excluded.min_dist_km), excluded.min_dist_km), "
           "max_alt_ft=MAX(COALESCE(sightings.max_alt_ft, 0), COALESCE(excluded.max_alt_ft, 0)), "
           "direction=COALESCE(excluded.direction, sightings.direction), "
           "airline=COALESCE(NULLIF(excluded.airline, ''), sightings.airline), "
           "type_code=COALESCE(NULLIF(excluded.type_code, ''), sightings.type_code), "
           "type_name=COALESCE(NULLIF(excluded.type_name, ''), sightings.type_name), "
           "reg=COALESCE(NULLIF(excluded.reg, ''), sightings.reg), "
           "origin_iata=COALESCE(excluded.origin_iata, sightings.origin_iata), "
           "origin_city=COALESCE(excluded.origin_city, sightings.origin_city), "
           "dest_iata=COALESCE(excluded.dest_iata, sightings.dest_iata), "
           "dest_city=COALESCE(excluded.dest_city, sightings.dest_city)")
    with self.tx() as con:
      for it in items:
        vals = [it.get(c) if c != "callsign" else (it.get(c) or "") for c in SIGHT_COLS]
        con.execute(sql, vals + [now_iso, now_iso, it.get("dist_km"), it.get("alt_ft")])
    return len(items)

  def sighting_stats(self, today, week_from):
    with self.tx(write=False) as con:
      one = lambda q, *a: con.execute(q, a).fetchone()[0]  # noqa: E731
      stats = {
          "today": one("SELECT COUNT(*) FROM sightings WHERE day=?", today),
          "week": one("SELECT COUNT(*) FROM sightings WHERE day>=?", week_from),
          "total": one("SELECT COUNT(*) FROM sightings"),
          "days": one("SELECT COUNT(DISTINCT day) FROM sightings"),
      }
      r = con.execute("SELECT airline, COUNT(*) c FROM sightings WHERE COALESCE(airline,'')<>'' "
                      "GROUP BY airline ORDER BY c DESC, airline LIMIT 1").fetchone()
      stats["top_airline"] = (r["airline"], r["c"]) if r else None
      r = con.execute("SELECT type_name, COUNT(*) c FROM sightings WHERE COALESCE(type_name,'') NOT IN ('','Bilinmiyor') "
                      "GROUP BY type_name ORDER BY c DESC, type_name LIMIT 1").fetchone()
      stats["top_type"] = (r["type_name"], r["c"]) if r else None
      stats["per_day"] = {r["day"]: r["c"] for r in con.execute(
          "SELECT day, COUNT(*) c FROM sightings WHERE day>=? GROUP BY day", (week_from,))}
    return stats

  def recent_sightings(self, limit=30):
    with self.tx(write=False) as con:
      return [dict(r) for r in con.execute(
          "SELECT * FROM sightings ORDER BY last_seen DESC, id DESC LIMIT ?", (limit,))]

  # ---- GitHub senkronu
  def snapshot_bytes(self):
    """Tutarlı bir anlık görüntü (yazma sırasında bozuk dosya yüklenmesin)."""
    with self.lock:
      src = self.connect()
      fd, tmp = tempfile.mkstemp(suffix=".db", dir=str(self.path.parent))
      os.close(fd)
      try:
        dst = sqlite3.connect(tmp)
        try:
          src.backup(dst)
        finally:
          dst.close()
        return Path(tmp).read_bytes()
      finally:
        src.close()
        try:
          os.remove(tmp)
        except OSError:
          pass

  def _write_temp(self, data):
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=str(self.path.parent))
    with os.fdopen(fd, "wb") as f:
      f.write(data)
    return tmp

  def install_remote(self, data):
    """Uzaktaki veritabanını yerel dosyanın yerine koyar (yalnızca açılışta)."""
    tmp = self._write_temp(data)
    try:
      chk = sqlite3.connect(tmp)
      try:
        ok = chk.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
      finally:
        chk.close()
      if not ok:
        raise GitError("Uzaktaki veritabanı bozuk görünüyor, yerel dosya korunuyor")
      with self.lock:
        os.replace(tmp, self.path)
        tmp = None
        self.init_schema()  # eski sürüm dosyalara eksik tabloları ekler
    finally:
      if tmp:
        try:
          os.remove(tmp)
        except OSError:
          pass
    self.dirty = False

  def merge_remote(self, data):
    """Açılışta çekme başarısız olduysa, sonradan çekilen uzak veriyi yerel veriyle BİRLEŞTİRİR."""
    tmp = self._write_temp(data)
    try:
      with self.lock:
        con = self.connect()
        try:
          con.execute("ATTACH DATABASE ? AS r", (tmp,))
          tables = {x[0] for x in con.execute("SELECT name FROM r.sqlite_master WHERE type='table'")}
          if "sightings" in tables:
            cols = ", ".join(SIGHT_COLS + ("first_seen", "last_seen", "min_dist_km", "max_alt_ft"))
            con.execute(f"INSERT OR IGNORE INTO sightings ({cols}) SELECT {cols} FROM r.sightings")
          if "fids_flights" in tables:
            cols = ", ".join(FIDS_COLS + ("first_seen", "updated_at"))
            con.execute(f"INSERT OR IGNORE INTO fids_flights ({cols}) SELECT {cols} FROM r.fids_flights")
          if "api_usage" in tables:
            con.execute(
                "INSERT INTO api_usage(month, provider, calls, units) "
                "SELECT month, provider, calls, units FROM r.api_usage WHERE true "
                "ON CONFLICT(month, provider) DO UPDATE SET "
                "calls=MAX(api_usage.calls, excluded.calls), units=MAX(api_usage.units, excluded.units)")
          if "meta" in tables:
            con.execute("INSERT OR IGNORE INTO meta(key, value) SELECT key, value FROM r.meta")
          con.commit()
          con.execute("DETACH DATABASE r")
        finally:
          con.close()
    finally:
      try:
        os.remove(tmp)
      except OSError:
        pass
    self.dirty = True
    self.write_seq += 1

  def startup_sync(self):
    """Uygulama açılışında bir kez: data dalındaki veritabanını getir."""
    if not self.git:
      return "local"
    status, data = self.git.pull()
    if status == "ok":
      try:
        self.install_remote(data)
      except Exception as e:  # bozuk dosya: yerel dosya kalsın, push kapalı kalsın
        self.git.synced_ok = False
        self.git.last_error = str(e)
        return "error"
    return status

  def _sync_then_push(self):
    """Arka plan iş parçacığı: gerekirse çek+birleştir, sonra yükle."""
    seq = self.write_seq
    ok = False
    try:
      if not self.git.synced_ok:
        status, data = self.git.pull()
        if status == "ok":
          self.merge_remote(data)
          seq = self.write_seq
      if self.git.synced_ok:
        data = self.snapshot_bytes()
        msg = "db: otomatik senkron " + time.strftime("%Y-%m-%d %H:%M", time.gmtime()) + " UTC"
        ok = self.git.push(data, msg)
    except Exception as e:  # asla uygulamayı düşürme
      self.git.last_error = f"{type(e).__name__}: {e}"
    finally:
      now = time.time()
      if ok:
        self.last_push_ok = now
        self.last_push = now
        if self.write_seq == seq:
          self.dirty = False
      else:
        self.last_push = now - self.push_interval + 120  # 2 dk sonra tekrar dene
      self._push_lock.release()

  def maybe_push(self, force=False, wait=False):
    """Değişiklik varsa ve süre dolduysa arka planda GitHub'a yükler. Başlatıldıysa True."""
    if not self.git or (not self.dirty and not force):
      return False
    if not force and time.time() - self.last_push < self.push_interval:
      return False
    if not self._push_lock.acquire(blocking=False):
      return False
    self.last_push = time.time()
    t = threading.Thread(target=self._sync_then_push, daemon=True, name="radar-db-push")
    self._push_thread = t
    t.start()
    if wait:
      t.join(timeout=60)
    return True

  def wait_push(self, timeout=30):
    t = self._push_thread
    if t is not None:
      t.join(timeout=timeout)

  def sync_status(self):
    g = self.git
    if not g:
      return {"mode": "local", "ok": True, "dirty": self.dirty, "branch": "", "error": "",
              "last_ok": 0.0}
    return {"mode": "github", "ok": bool(g.synced_ok and not g.last_error), "dirty": self.dirty,
            "branch": g.branch, "error": g.last_error, "last_ok": self.last_push_ok,
            "synced": g.synced_ok}


def open_db(secret, path=DEFAULT_DB_PATH, http=None):
  """secret(name, default) -> str. Ayarlar: GITHUB_TOKEN, GITHUB_REPO, DATA_BRANCH, DATA_DB_PATH, DB_PUSH_MIN."""
  token = secret("GITHUB_TOKEN", "")
  git = None
  if token:
    git = GitStore(token, secret("GITHUB_REPO", "Blixembosch/atlasradar"),
                   secret("DATA_BRANCH", "data") or "data",
                   secret("DATA_DB_PATH", "db/radar.db") or "db/radar.db", http=http,
                   extra_files={"db/schema.sql": SCHEMA.strip().encode("utf-8") + b"\n"})
  try:
    interval = max(1, int(float(secret("DB_PUSH_MIN", "20")))) * 60
  except ValueError:
    interval = 1200
  db = RadarDB(path, git=git, push_interval_s=interval)
  db.startup_sync()
  return db
