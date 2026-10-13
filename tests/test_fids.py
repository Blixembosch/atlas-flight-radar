import os, sys, tempfile
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import radar_db as R
import radar_fids as F

FAILS = []
def ck(name, cond, info=""):
  print(("OK   " if cond else "FAIL ") + name + (f"   [{info}]" if (info and not cond) else ""))
  if not cond: FAILS.append(name)

NOW = datetime(2026, 10, 12, 14, 7, tzinfo=F.TZ)

def adb_flight(num, hhmm, city="Malaga", iata="AGP", status="Expected", revised=None, gate=None,
               day="2026-10-12", runway=None, al=("Transavia", "HV", "TRA"), **extra):
  mv = {"airport": {"icao": "LEMG", "iata": iata, "name": city + " Airport", "municipalityName": city, "countryCode": "ES"},
        "scheduledTime": {"utc": "x", "local": f"{day} {hhmm}+02:00"}}
  if revised: mv["revisedTime"] = {"utc": "x", "local": f"{day} {revised}+02:00"}
  if runway: mv["runwayTime"] = {"utc": "x", "local": f"{day} {runway}+02:00"}
  if gate: mv["gate"] = gate
  d = {"movement": mv, "number": num, "status": status, "callSign": num.replace(" ", ""),
       "aircraft": {"model": "Boeing 737-800", "reg": "PH-HZA"}, "airline": {"name": al[0], "iata": al[1], "icao": al[2]}}
  d.update(extra); return d

# ---- ayrıştırma
js = {"departures": [adb_flight("HV 5101", "15:00", revised="15:20", gate="B3", status="Delayed"),
                     adb_flight("FR 123", "16:00", status="Canceled"),
                     adb_flight("HV 9", "17:00", codeshareStatus="IsCodeshared"),
                     adb_flight("QY 1", "18:00", isCargo=True),
                     {"movement": {"scheduledTime": {}}},          # bozuk kayıt
                     "garip"],
      "arrivals": [adb_flight("HV 5102", "14:30", status="Arrived", runway="14:41")]}
rows = F.parse_adb(js)
ck("bozuk/ortak/kargo atlandı", [r["number"] for r in rows] == ["HV 5101", "FR 123", "HV 5102"])
ck("yön", [r["direction"] for r in rows] == ["DEP", "DEP", "ARR"])
ck("yerel saat", rows[0]["sched_local"] == "2026-10-12T15:00" and rows[0]["est_local"] == "2026-10-12T15:20")
ck("kapı/tescil", rows[0]["gate"] == "B3" and rows[0]["reg"] == "PH-HZA")
ck("durum normalleşir", rows[0]["status"] == "delayed" and rows[1]["status"] == "canceled")
ck("parse_adb bozuk girdi", F.parse_adb(None) == [] and F.parse_adb({"departures": None}) == [])
ck("anahtar kararlı", F.parse_adb(js)[0]["key"] == rows[0]["key"])

# ---- durum / gecikme ayrı
b = F.board_row(rows[0], NOW)
ck("gecikme +20 dk ayrı", b["delay_txt"] == "+20 dk" and b["delay_kind"] == "warn" and b["status_label"] == "Gecikmeli")
ck("planlanan/yeni saat", b["sched_hm"] == "15:00" and b["eff_hm"] == "15:20")
c = F.board_row(rows[1], NOW)
ck("iptalde gecikme yok", c["delay_txt"] == "" and c["status_kind"] == "bad")
a = F.board_row(rows[2], NOW)
ck("indi + gerçekleşen +11", a["status_label"] == "İndi" and a["delay_txt"] == "+11 dk")
e = F.board_row(dict(rows[0], status="expected", est_local="2026-10-12T15:02"), NOW)
ck("2 dk fark: zamanında", e["status_label"] == "Zamanında" and e["delay_txt"] == "")
e = F.board_row(dict(rows[0], status="expected", est_local="2026-10-12T15:50"), NOW)
ck("50 dk -> gecikmeli + kırmızı", e["status_label"] == "Gecikmeli" and e["delay_kind"] == "bad")
e = F.board_row(dict(rows[0], status="expected", est_local="2026-10-12T14:50"), NOW)
ck("erken: -10 dk yeşil", e["delay_txt"] == "-10 dk" and e["delay_kind"] == "ok")
e = F.board_row(dict(rows[0], status="boarding", est_local=None), NOW)
ck("tahmin yok -> gecikme boş", e["delay_txt"] == "" and e["status_label"] == "Biniş")
ck("bilinmeyen durum", F.board_row(dict(rows[0], status="zzz", est_local=None), NOW)["status_label"] == "Bilgi yok")

# ---- arama
ck("arama no", F.board_matches(b, "hv5101") and F.board_matches(b, "HV 5101"))
ck("arama şehir/kapı/durum", F.board_matches(b, "malaga") and F.board_matches(b, "b3") and F.board_matches(b, "gecik"))
ck("arama olmayan", not F.board_matches(b, "istanbul"))

# ---- bütçe
def newdb():
  return R.RadarDB(os.path.join(tempfile.mkdtemp(), "r.db"))

db = newdb()
bs = F.budget_state(db, NOW)
ck("bütçe başlangıç", bs["cap"] == 540 and bs["remaining"] == 540 and bs["can_call"])
ck("aralık makul", 1 <= bs["interval_h"] <= 12 and abs(bs["interval_h"] - 24 / (540 / 20 / 2)) < 0.01)
db.add_usage("2026-10", F.PROVIDER, 270, 540)
ck("bütçe bitti", not F.budget_state(db, NOW)["can_call"])

class Resp:
  def __init__(self, code, js=None): self.status_code, self._js = code, js
  def json(self):
    if self._js is None: raise ValueError("bad json")
    return self._js

class Http:
  def __init__(self, resp): self.resp, self.calls = resp, []
  def get(self, url, headers=None, params=None, timeout=None):
    self.calls.append((url, dict(headers), dict(params)));
    r = self.resp
    return r(len(self.calls)) if callable(r) else r

def many(n, base_h, direction):
  out = []
  for i in range(n):
    t = datetime(2026, 10, 12, 12, 0) + timedelta(minutes=base_h * 60 + 15 * i)
    out.append(adb_flight(f"HV {100 + i}", t.strftime("%H:%M"), day=t.strftime("%Y-%m-%d")))
  return out

# ---- yenileme
db = newdb()
http = Http(Resp(200, {"departures": many(30, 0, "DEP"), "arrivals": many(30, 0, "ARR")}))
r = F.refresh(db, "KEY", NOW, http=http)
ck("çekti", r["fetched"] and r["calls"] == 1 and r["ok"])
u, h, p = http.calls[0]
ck("URL EHEH + pencere", "/icao/EHEH/2026-10-12T12:07/2026-10-13T00:06" in u or "/icao/EHEH/2026-10-12T12:07/2026-10-12T23:" in u)
ck("başlıklar", h["X-RapidAPI-Key"] == "KEY" and h["X-RapidAPI-Host"] == F.ADB_HOST and p["withLeg"] == "true")
ck("kota düştü", db.usage("2026-10", F.PROVIDER) == (1, 2))
ck("kayıtlar yazıldı", len(db.fids_between("DEP", "2026-10-12T00:00", "2026-10-13T23:59")) == 30)
ck("meta", db.meta_get("fids_last_ok") == "2026-10-12T14:07" and F.data_age_min(db, NOW) == 0)
r2 = F.refresh(db, "KEY", NOW + timedelta(minutes=30), http=http)
ck("taze: tekrar çağırmaz", not r2["fetched"] and len(http.calls) == 1)
r3 = F.refresh(db, "KEY", NOW + timedelta(hours=13), http=http)
ck("süre dolunca çeker", r3["fetched"] and len(http.calls) >= 2)

# kısa liste -> ikinci pencere
db = newdb(); http = Http(Resp(200, {"departures": many(5, 0, "DEP"), "arrivals": many(5, 0, "ARR")}))
r = F.refresh(db, "KEY", NOW, http=http)
ck("kısa ise ikinci pencere (en çok 2 çağrı)", r["calls"] == 2 and len(http.calls) == 2)
ck("ikinci pencere ilkinin devamı", http.calls[1][0].split("/")[-2] > http.calls[0][0].split("/")[-2])

# hatalar
db = newdb(); r = F.refresh(db, "", NOW, http=Http(Resp(200, {})))
ck("anahtar yok", not r["fetched"] and r["reason"] == "anahtar yok")
db = newdb(); http = Http(Resp(403)); r = F.refresh(db, "K", NOW, http=http)
ck("403 yetki mesajı", not r["ok"] and "yetki" in r["error"] and db.usage("2026-10", F.PROVIDER) == (0, 0))
ck("hata meta", "403" in db.meta_get("fids_last_error"))
r = F.refresh(db, "K", NOW + timedelta(minutes=10), http=http)
ck("hatadan sonra hemen tekrar denemez", len(http.calls) == 1)
db = newdb(); http = Http(Resp(429)); r = F.refresh(db, "K", NOW, http=http)
ck("429", "429" in r["error"] and len(http.calls) == 1)
db = newdb(); http = Http(Resp(200, None)); r = F.refresh(db, "K", NOW, http=http)
ck("bozuk JSON düşürmez", not r["fetched"] and "çözümlenemedi" in r["error"])
class Boom:
  def get(self, *a, **k): raise ConnectionError("secret-key-in-url")
db = newdb(); r = F.refresh(db, "K", NOW, http=Boom())
ck("ağ hatası mesajında ayrıntı sızmaz", "ConnectionError" in r["error"] and "secret" not in r["error"])
db = newdb(); db.add_usage("2026-10", F.PROVIDER, 270, 540); http = Http(Resp(200, {}))
r = F.refresh(db, "K", NOW, http=http)
ck("bütçe bitince çağrı yok", len(http.calls) == 0 and r["reason"] == "bütçe bitti")
db = newdb(); db.fetch_lock.acquire(); http = Http(Resp(200, {}))
r = F.refresh(db, "K", NOW, http=http)
ck("eşzamanlı oturum çağırmaz", len(http.calls) == 0); db.fetch_lock.release()

# ---- ekran listesi
db = newdb()
F.refresh(db, "KEY", NOW, http=Http(Resp(200, {"departures": many(30, 0, "DEP"), "arrivals": many(30, 0, "ARR")})))
dep, tot = F.select_board(db, "DEP", NOW, limit=20)
ck("20 satır", len(dep) == 20 and tot >= 20)
ck("zaman sıralı", [r["sched_local"] for r in dep] == sorted(r["sched_local"] for r in dep))
ck("çok eski satır yok", all(r["dt"] >= NOW.replace(tzinfo=None) - timedelta(minutes=45) for r in dep))
dep2, tot2 = F.select_board(db, "DEP", NOW, limit=20, query="hv 115")
ck("arama filtreler", 0 < len(dep2) < 20 and all("hv115" in (r["number"] or "").lower().replace(" ", "") for r in dep2))

# ---- demo
for d in ("ARR", "DEP"):
  rows_, tot = F.select_demo(d, NOW, limit=20)
  ck(f"demo {d} >= 20 satır", len(rows_) == 20 and tot >= 20)
dm, _ = F.select_demo("DEP", NOW, limit=30)
kinds = {r["status_kind"] for r in dm}
ck("demo çeşitli durum", {"ok", "warn", "bad", "done", "info"} <= kinds | {"ok"} and len(kinds) >= 3)
ck("demo gecikme sütunu", any(r["delay_txt"] for r in dm))
ck("demo saatler sıralı", [r["sched_local"] for r in dm] == sorted(r["sched_local"] for r in dm))


# ================= v0.3.6: yanıt biçimi varyantları, boş yanıt, tanı
def flat(num, hhmm, **kw):
  mv = {"airport": {"icao": "LEMG", "iata": "AGP", "municipalityName": "Malaga", "countryCode": "ES"},
        "scheduledTimeLocal": f"2026-10-12 {hhmm}+02:00", "scheduledTimeUtc": "x"}
  if kw.get("rev"): mv["revisedTimeLocal"] = f"2026-10-12 {kw['rev']}+02:00"
  if kw.get("run"): mv["runwayTimeLocal"] = f"2026-10-12 {kw['run']}+02:00"
  return {"movement": mv, "number": num, "status": kw.get("status", "Expected"),
          "airline": {"name": "Transavia", "iata": "HV", "icao": "TRA"}, "aircraft": {"model": "B738"}}
js2 = {"departures": [flat("HV 1", "15:00", rev="15:25"), flat("HV 2", "16:00", status="Departed", run="16:03")],
       "arrivals": [flat("HV 3", "14:30")]}
r2 = F.parse_adb(js2)
ck("düz alan biçimi (scheduledTimeLocal) çözülür", [x["number"] for x in r2] == ["HV 1", "HV 2", "HV 3"], [x["number"] for x in r2])
ck("düz biçim: tahmini/gerçekleşen saat", r2[0]["est_local"] == "2026-10-12T15:25" and r2[1]["actual_local"] == "2026-10-12T16:03")
ck("düz biçim: gecikme +25", F.board_row(r2[0], NOW)["delay_txt"] == "+25 dk")
mixed = {"departures": [{"movement": {"airport": {}, "scheduledTime": "2026-10-12 15:00+02:00"}, "number": "X 1"}]}
ck("saat düz metin olarak da gelirse çözülür", len(F.parse_adb(mixed)) == 1)
d = F.describe_payload(js)
ck("tanı: yapı metni (değer yok)", "departures[" in d and "movement" in d and "HV 5101" not in d and "Transavia" not in d, d)
ck("tanı: sözlük olmayan yanıt", "sözlük değil" in F.describe_payload([1]))

# boş 200 yanıtı: ikinci pencereye gitmez, sebep yazılır, 'son başarılı' işaretlenmez
db = newdb(); http = Http(Resp(200, {"departures": [], "arrivals": []}))
r = F.refresh(db, "K", NOW, http=http)
ck("boş yanıt: tek çağrı (kota boşa gitmez)", len(http.calls) == 1 and r["calls"] == 1, len(http.calls))
ck("boş yanıt: sebep yazılır", "uçuş döndürmedi" in r["error"], r["error"])
ck("boş yanıt: 'son başarılı' işaretlenmez", db.meta_get("fids_last_ok") in (None, ""))
ck("boş yanıt: tanı kaydı", "ham: 0 varış / 0 kalkış" in (db.meta_get("fids_last_diag") or ""))
# ham var ama çözülemiyor
db = newdb(); http = Http(Resp(200, {"departures": [{"foo": 1}], "arrivals": []}))
r = F.refresh(db, "K", NOW, http=http)
ck("çözülemeyen biçim açıkça belirtilir", "biçimi beklenenden farklı" in r["error"] and "ham: 0 varış / 1 kalkış" in db.meta_get("fids_last_diag"))
# HTTP hatası tanıya yazılır
class R403(Resp):
  text = '{"message":"You are not subscribed to this API."}'
db = newdb(); F.refresh(db, "SECRETKEY", NOW, http=Http(R403(403)))
dg = db.meta_get("fids_last_diag")
ck("HTTP hatası tanıda, anahtar yok", "HTTP 403" in dg and "not subscribed" in dg and "SECRETKEY" not in dg, dg)
# zorla yenileme: 1 saatlik alt sınırı aşar ama 2 dk korumalı
db = newdb(); http = Http(Resp(200, {"departures": many(30, 0, "DEP"), "arrivals": many(30, 0, "ARR")}))
F.refresh(db, "K", NOW, http=http); n = len(http.calls)
F.refresh(db, "K", NOW + timedelta(minutes=1), http=http, force=True)
ck("zorla: 2 dakikadan önce reddedilir", len(http.calls) == n)
F.refresh(db, "K", NOW + timedelta(minutes=10), http=http, force=True)
ck("zorla: 10 dk sonra çeker (1 saat beklemez)", len(http.calls) > n)
n = len(http.calls)
db.add_usage("2026-10", F.PROVIDER, 270, 540)
F.refresh(db, "K", NOW + timedelta(minutes=30), http=http, force=True)
ck("zorla: bütçe bitmişse yine çağırmaz", len(http.calls) == n)
print("\nBAŞARISIZ:", FAILS if FAILS else "yok")
sys.exit(1 if FAILS else 0)
