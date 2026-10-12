import base64, json, os, sys, tempfile, time, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import radar_db as R
import radar_auth as A

FAILS = []
def ck(name, cond):
  print(("OK   " if cond else "FAIL ") + name)
  if not cond: FAILS.append(name)


from fakes import FakeGH, Resp

def newdb(gh=None, interval=1):
  d = tempfile.mkdtemp()
  git = R.GitStore("tok", "o/r", http=gh) if gh else None
  return R.RadarDB(os.path.join(d, "db", "radar.db"), git=git, push_interval_s=interval)


def row(key, **kw):
  r = dict(key=key, direction="DEP", number="HV1", sched_local="2026-10-12T10:00", status="Expected")
  r.update(kw); return r

# ---- şema + tarife
db = newdb()
ck("şema kuruldu", db.meta_get("schema_version") == "1")
db.upsert_fids([row("a", gate="B3", aircraft="B738"), row("b", sched_local="2026-10-12T09:00")], "2026-10-12T08:00")
db.upsert_fids([row("a", gate=None, aircraft=None, status="Departed", est_local="2026-10-12T10:10")], "2026-10-12T08:30")
rows = db.fids_between("DEP", "2026-10-12T00:00", "2026-10-12T23:59")
ck("sıralı", [r["key"] for r in rows] == ["b", "a"])
a = rows[1]
ck("boş yeni değer eskiyi silmez", a["gate"] == "B3" and a["aircraft"] == "B738")
ck("durum güncellenir", a["status"] == "Departed" and a["est_local"].endswith("10:10"))
ck("first_seen korunur", a["first_seen"] == "2026-10-12T08:00")
ck("yön filtresi", db.fids_between("ARR", "2026-10-12T00:00", "2026-10-12T23:59") == [])
db.prune("2026-10-12T09:30")
ck("prune", [r["key"] for r in db.fids_between("DEP", "2000", "2100")] == ["a"])

# ---- kota
db.add_usage("2026-10", "adb", 1, 2); db.add_usage("2026-10", "adb", 1, 2)
ck("kota toplanır", db.usage("2026-10", "adb") == (2, 4) and db.usage("2026-09", "adb") == (0, 0))

# ---- gözlemler
s = dict(day="2026-10-12", icao24="abc", callsign="TRA1", airline="Transavia", type_code="B738",
         type_name="Boeing 737-800", dist_km=3.0, alt_ft=2000, origin_iata=None)
db.record_sightings([s], "t1")
s2 = dict(s, dist_km=1.5, alt_ft=1500, origin_iata="AGP", type_name="")
db.record_sightings([s2], "t2")
st = db.sighting_stats("2026-10-12", "2026-10-06")
ck("aynı uçak tek kayıt", st["today"] == 1 and st["total"] == 1)
rs = db.recent_sightings()[0]
ck("min mesafe/max irtifa", rs["min_dist_km"] == 1.5 and rs["max_alt_ft"] == 2000)
ck("boş alan eskiyi silmez", rs["type_name"] == "Boeing 737-800" and rs["origin_iata"] == "AGP")
db.record_sightings([dict(s, icao24="def", callsign="")], "t3")
ck("istatistik", db.sighting_stats("2026-10-12", "2026-10-06")["top_airline"][0] == "Transavia")

# ---- snapshot
snap = db.snapshot_bytes()
ck("snapshot SQLite", snap.startswith(R.SQLITE_MAGIC))

# ---- GitHub: dal yok -> oluştur
gh = FakeGH(branch=False)
db = newdb(gh)
ck("pull empty", db.startup_sync() == "empty" and db.git.synced_ok)
db.meta_set(x=1)
ck("push başlar", db.maybe_push(force=True, wait=True))
ck("orphan dal oluşturuldu", gh.branch and gh.data.startswith(R.SQLITE_MAGIC))
ck("sadece FakeGH ağacı kontrolü (extra yok)", len(gh.tree) == 1)
_g = FakeGH(branch=False); _d = newdb(_g); _d.git.extra_files = {"db/schema.sql": b"-- x"}; _d.startup_sync(); _d.maybe_push(force=True, wait=True)
ck("data dalı: radar.db + schema.sql", sorted(e["path"] for e in _g.tree) == ["db/radar.db", "db/schema.sql"])
ck("token loglanmadı", "tok" not in db.git.last_error)

# ---- GitHub: mevcut veri çekilir ve yerel üzerine kurulur
db2 = newdb(FakeGH(branch=True, data=gh.data))
ck("pull ok", db2.startup_sync() == "ok")
ck("uzak veri geldi", db2.meta_get("x") == "1")
db2.meta_set(y=2); db2.add_usage("2026-10", "adb", 1, 2)
gh2 = db2.git.http
ck("push (PUT)", db2.maybe_push(force=True, wait=True) and gh2.data != gh.data)
db3 = newdb(FakeGH(branch=True, data=gh2.data)); db3.startup_sync()
ck("round-trip", db3.meta_get("y") == "2" and db3.usage("2026-10", "adb") == (1, 2))

# ---- sha çakışması bir kez yeniden denenir
gh3 = FakeGH(branch=True, data=gh2.data); db4 = newdb(gh3); db4.startup_sync()
gh3.conflict_once = True; db4.meta_set(z=3)
ck("409 sonrası yeniden dene", db4.maybe_push(force=True, wait=True) and db4.git.last_error == "")

# ---- GÜVENLİK: çekme başarısızsa uzağa ASLA yazma
gh4 = FakeGH(branch=True, data=gh2.data, repo_ok=False); db5 = newdb(gh4)
ck("pull error", db5.startup_sync() == "error" and not db5.git.synced_ok)
before = gh4.data
db5.meta_set(q=1)
db5.maybe_push(force=True, wait=True)
ck("çekme başarısızken veri ezilmedi", gh4.data == before and not any(m == "PUT" for m, _ in gh4.calls))
ck("hata mesajı açık", "404" in db5.git.last_error)
# depo düzelince birleştirip yükler, yerel veri kaybolmaz
gh4.repo_ok = True
db5.last_push = 0
ck("sonra birleşip yükler", db5.maybe_push(force=True, wait=True))
dbx = newdb(FakeGH(branch=True, data=gh4.data)); dbx.startup_sync()
ck("hem yerel hem uzak veri var", dbx.meta_get("q") == "1" and dbx.meta_get("y") == "2")

# ---- bozuk uzak dosya
bad = FakeGH(branch=True, data=b"not a db"); db6 = newdb(bad)
ck("bozuk dosya reddedilir", db6.startup_sync() == "error" and not db6.git.synced_ok)

# ---- aralık
db7 = newdb(FakeGH(branch=False), interval=3600); db7.startup_sync(); db7.meta_set(a=1)
db7.last_push = time.time()
ck("aralık dolmadan push yok", db7.maybe_push() is False)
db7.last_push = time.time() - 4000
ck("aralık dolunca push", db7.maybe_push(wait=True) is True and db7.sync_status()["ok"])

# ---- open_db + yerel mod
sec = lambda k, d="": {"GITHUB_TOKEN": ""}.get(k, d)
ck("token yoksa yerel", R.open_db(sec, os.path.join(tempfile.mkdtemp(), "x.db")).git is None)

# ---- AUTH
ck("doğru şifre", A.check_password(" gizli ", "gizli"))
ck("yanlış şifre", not A.check_password("x", "gizli"))
ck("boş şifre asla geçmez", not A.check_password("", "") and not A.check_password("a", ""))
ck("kilit süreleri", [A.lock_seconds(i) for i in (0, 2, 3, 4, 5, 40)] == [0, 0, 5, 10, 15, 60])

class S:
  def __init__(self): self.session_state = {}; self.reruns = 0
  def rerun(self): self.reruns += 1

def run(st, secrets, pw, t=1000.0):
  return A.gate(st, lambda k, d="": secrets.get(k, d), login_ui=lambda s, state: (st.__dict__.setdefault("seen", []).append(dict(state)) or pw), now=lambda: t)

st = S()
ck("şifre yok -> kilitli", run(st, {}, "x") is False and st.seen[-1]["misconfigured"])
ck("şifre yok + izin", run(S(), {"RADAR_ALLOW_NO_PASSWORD": "true"}, None) is True)
st = S()
ck("form gönderilmedi", run(st, {"APP_PASSWORD": "p"}, None) is False and st.reruns == 0)
ck("yanlış", run(st, {"APP_PASSWORD": "p"}, "no") is False and st.session_state["auth_fails"] == 1 and not st.session_state.get("auth_ok"))
for _ in range(2): run(st, {"APP_PASSWORD": "p"}, "no")
ck("3. yanlışta bekleme", st.session_state["auth_until"] > 1000 and "sn sonra" in st.session_state["auth_error"])
ck("bekleme sırasında doğru şifre de geçmez", run(st, {"APP_PASSWORD": "p"}, "p", t=1001) is False and not st.session_state.get("auth_ok"))
ck("bekleme bitince geçer", run(st, {"APP_PASSWORD": "p"}, "p", t=1100) is True or st.session_state.get("auth_ok"))
ck("oturum açık kalır", A.gate(st, lambda k, d="": "", login_ui=lambda *_: 1/0) is True)
A.logout(st)
ck("çıkış", "auth_ok" not in st.session_state)

print("\nBAŞARISIZ:", FAILS if FAILS else "yok")
sys.exit(1 if FAILS else 0)
