"""
Eindhoven Havalimanı terminal ekranı (Varış / Kalkış) veri katmanı.

Kaynak: AeroDataBox (RapidAPI) - ücretsiz katman ayda ~600 birim. Bu yüzden:
  * tarife veritabanında önbelleklenir, ekran her zaman veritabanından okunur,
  * API çağrıları kalan aylık bütçeye göre seyreltilir ve oturumlar arasında tekilleştirilir,
  * anahtar yoksa ya da bütçe bittiyse eldeki önbellek gösterilir (ekran boş kalmaz).

Bu modül Streamlit'e bağlı değildir; tamamı test edilebilir.
"""
from __future__ import annotations

import calendar
import hashlib
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
AIRPORT_ICAO = "EHEH"
ADB_HOST = "aerodatabox.p.rapidapi.com"
PROVIDER = "aerodatabox"
ISO = "%Y-%m-%dT%H:%M"
WINDOW_H = 12              # AeroDataBox tek çağrıda en çok 12 saat verir
PAST_H = 2                 # pencere şu andan kaç saat geriden başlar
FRESH_MIN = 25             # ekranda "taze" saymak için üst sınır (dk)
MIN_ROWS = 20              # her yönde hedef satır sayısı
MIN_INTERVAL_H = 1.0       # iki çekme arası mutlak alt sınır
MAX_INTERVAL_H = 12.0
RESERVE = 0.10             # aylık bütçenin %10'u güvenlik payı
DEFAULT_MONTHLY_UNITS = 600
DEFAULT_UNITS_PER_CALL = 2

# (etiket, görünüm sınıfı)  ok=yeşil, warn=sarı, bad=kırmızı, info=mavi, done=gri
STATUS_TR = {
    "expected": ("Bekleniyor", "info"),
    "enroute": ("Yolda", "info"),
    "approaching": ("Yaklaşıyor", "info"),
    "checkin": ("Check-in", "info"),
    "boarding": ("Biniş", "ok"),
    "gateclosed": ("Kapı kapandı", "warn"),
    "departed": ("Kalktı", "done"),
    "arrived": ("İndi", "done"),
    "delayed": ("Gecikmeli", "warn"),
    "canceled": ("İptal", "bad"),
    "canceleduncertain": ("İptal?", "bad"),
    "diverted": ("Yönlendirildi", "bad"),
    "unknown": ("Bilgi yok", "info"),
}
DELAY_THRESHOLD_MIN = 5


# =============================================================================
# Zaman yardımcıları
# =============================================================================
def now_local(now=None):
  return (now or datetime.now(TZ)).astimezone(TZ).replace(second=0, microsecond=0)


def to_iso(dt):
  return dt.strftime(ISO)


def parse_local(s):
  """'2026-10-12 10:05+02:00' | '2026-10-12T10:05' -> naif yerel datetime ya da None."""
  if not s or not isinstance(s, str):
    return None
  m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", s.strip())
  if not m:
    return None
  try:
    return datetime(*map(int, m.groups()))
  except ValueError:
    return None


def _iso_or_none(s):
  d = parse_local(s)
  return to_iso(d) if d else None


def month_key(now):
  return now.strftime("%Y-%m")


def days_left_in_month(now):
  last = calendar.monthrange(now.year, now.month)[1]
  return max(1, last - now.day + 1)


# =============================================================================
# AeroDataBox çözümleme
# =============================================================================
def norm_status(raw):
  k = re.sub(r"[^a-z]", "", str(raw or "").lower())
  return k if k in STATUS_TR else "unknown"


def _flight_key(direction, number, sched, callsign, other):
  base = f"{direction}|{number or callsign or other}|{sched}"
  return hashlib.sha1(base.encode()).hexdigest()[:16]


def _local(mv, base):
  """Saat alanını iki sürüm biçiminde de okur:
     {"scheduledTime": {"utc": .., "local": ..}}  ya da  {"scheduledTimeLocal": "..."}."""
  v = mv.get(base)
  if isinstance(v, dict):
    out = v.get("local") or v.get("Local")
    if out:
      return out
  elif isinstance(v, str) and v:
    return v
  return mv.get(base + "Local") or mv.get(base.replace("Time", "TimeLocal")) or None


def describe_payload(js, depth=3):
  """Yanıtın YAPISINI (değerleri değil) kısa metne çevirir; tanı için."""
  def shape(x, d):
    if isinstance(x, dict):
      if d <= 0:
        return "{…}"
      return "{" + ",".join(f"{k}{shape(v, d - 1) if isinstance(v, (dict, list)) else ''}" for k, v in list(x.items())[:14]) + "}"
    if isinstance(x, list):
      return f"[{len(x)}]" + (shape(x[0], d - 1) if x and d > 0 else "")
    return ""
  if not isinstance(js, dict):
    return f"yanıt sözlük değil ({type(js).__name__})"
  return ", ".join(f"{k}{shape(v, depth)}" for k, v in list(js.items())[:8])[:600]


def parse_adb(js, only_direction=None):
  """AeroDataBox yanıtını satır sözlüklerine çevirir. Bozuk/eksik alanlar atlanır, hata fırlatmaz."""
  rows = []
  if not isinstance(js, dict):
    return rows
  for direction, field in (("DEP", "departures"), ("ARR", "arrivals")):
    if only_direction and direction != only_direction:
      continue
    for f in js.get(field) or []:
      try:
        if not isinstance(f, dict):
          continue
        mv = f.get("movement") or {}
        ap = mv.get("airport") or {}
        sched_iso = _iso_or_none(_local(mv, "scheduledTime"))
        if not sched_iso:
          continue
        est = _iso_or_none(_local(mv, "revisedTime")) or _iso_or_none(_local(mv, "predictedTime"))
        actual = _iso_or_none(_local(mv, "runwayTime"))
        number = re.sub(r"\s+", " ", str(f.get("number") or "")).strip() or None
        cs = (f.get("callSign") or "").strip().upper() or None
        al = f.get("airline") or {}
        ac = f.get("aircraft") or {}
        if str(f.get("codeshareStatus") or f.get("codeShareStatus") or "").lower().endswith("iscodeshared"):
          continue  # ortak uçuş kopyalarını gösterme
        if f.get("isCargo"):
          continue
        rows.append({
            "key": _flight_key(direction, number, sched_iso, cs, ap.get("icao") or ap.get("iata")),
            "direction": direction,
            "number": number,
            "callsign": cs,
            "airline": al.get("name"),
            "airline_iata": (al.get("iata") or None),
            "airline_icao": (al.get("icao") or None),
            "other_iata": ap.get("iata") or None,
            "other_icao": ap.get("icao") or None,
            "other_city": ap.get("municipalityName") or ap.get("name") or None,
            "other_cc": (ap.get("countryCode") or None),
            "sched_local": sched_iso,
            "est_local": est,
            "actual_local": actual,
            "status": norm_status(f.get("status")),
            "terminal": (str(mv.get("terminal")) if mv.get("terminal") else None),
            "gate": (str(mv.get("gate")) if mv.get("gate") else None),
            "aircraft": ac.get("model"),
            "reg": ac.get("reg"),
        })
      except Exception:  # tek bir bozuk kayıt tüm listeyi düşürmesin
        continue
  return rows


# =============================================================================
# Ekran satırı: durum ve gecikme AYRI sütunlar
# =============================================================================
def delay_minutes(row):
  """Planlanan ile tahmin/gerçekleşen arasındaki fark (dk); bilinmiyorsa None."""
  sched = parse_local(row.get("sched_local"))
  other = parse_local(row.get("actual_local")) or parse_local(row.get("est_local"))
  if not sched or not other:
    return None
  return int(round((other - sched).total_seconds() / 60))


def board_row(row, now):
  """Veritabanı satırını ekranda gösterilecek alanlara çevirir."""
  st_key = row.get("status") or "unknown"
  if st_key not in STATUS_TR:
    st_key = "unknown"
  label, kind = STATUS_TR[st_key]
  d = delay_minutes(row)
  sched = parse_local(row["sched_local"])
  effective = parse_local(row.get("actual_local")) or parse_local(row.get("est_local")) or sched
  # Gecikme etiketi: yalnızca eşiği aşan gecikmeler; erken gelenler "-N"
  if st_key in ("canceled", "canceleduncertain"):
    delay_txt, delay_kind = "", ""
  elif d is not None and d >= DELAY_THRESHOLD_MIN:
    delay_txt, delay_kind = f"+{d} dk", "warn" if d < 30 else "bad"
  elif d is not None and d <= -DELAY_THRESHOLD_MIN:
    delay_txt, delay_kind = f"{d} dk", "ok"
  else:
    delay_txt, delay_kind = "", ""
  # Durum "Bekleniyor" iken belirgin gecikme varsa durumu "Gecikmeli" yap
  if st_key in ("expected", "unknown", "enroute", "checkin") and d is not None and d >= 15:
    label, kind = STATUS_TR["delayed"]
  if st_key in ("expected", "unknown") and d is not None and -DELAY_THRESHOLD_MIN < d < DELAY_THRESHOLD_MIN \
      and row.get("est_local"):
    label, kind = "Zamanında", "ok"
  num = row.get("number") or row.get("callsign") or "—"
  place = row.get("other_city") or row.get("other_iata") or row.get("other_icao") or "—"
  return {
      **row,
      "sched_hm": sched.strftime("%H:%M") if sched else "--:--",
      "eff_hm": effective.strftime("%H:%M") if effective and delay_txt else "",
      "status_label": label, "status_kind": kind,
      "delay_txt": delay_txt, "delay_kind": delay_kind, "delay_min": d,
      "number_disp": num, "place_disp": place,
      "dt": sched,
  }


def board_matches(r, q):
  """Terminal ekranı araması: uçuş no, havayolu, şehir, havalimanı kodu, durum, kapı, tescil."""
  q = (q or "").strip().lower().replace(" ", "")
  if not q:
    return True
  hay = " ".join(str(r.get(k) or "") for k in (
      "number", "callsign", "airline", "other_city", "other_iata", "other_icao", "status_label",
      "gate", "terminal", "reg", "aircraft", "sched_hm")).lower().replace(" ", "")
  return q in hay


def select_board(db, direction, now, limit=MIN_ROWS, past_min=45, query=""):
  """Ekranda gösterilecek satırlar: son `past_min` dk içindekiler + gelecekler, en az `limit` (varsa)."""
  start = to_iso(now - timedelta(minutes=past_min))
  end = to_iso(now + timedelta(hours=36))
  rows = db.fids_between(direction, start, end)
  out = [board_row(r, now) for r in rows]
  # Çok eski ve tamamlanmış satırları ele (ör. 45 dk önce kalkmış olanlar zaten pencerede)
  out = [r for r in out if not (r["status_kind"] == "done" and r["dt"] and
                                r["dt"] < now.replace(tzinfo=None) - timedelta(minutes=past_min))]
  if query:
    out = [r for r in out if board_matches(r, query)]
  total = len(out)
  return out[:limit], total


# =============================================================================
# Kota bütçesi ve çekme planı
# =============================================================================
def budget_state(db, now, monthly_units=DEFAULT_MONTHLY_UNITS, units_per_call=DEFAULT_UNITS_PER_CALL):
  calls, used = db.usage(month_key(now), PROVIDER)
  cap = int(monthly_units * (1 - RESERVE))
  remaining = max(0, cap - used)
  days = days_left_in_month(now)
  per_day = remaining / days
  calls_per_day = per_day / max(1, units_per_call)
  interval_h = MAX_INTERVAL_H if calls_per_day < 24 / MAX_INTERVAL_H else 24 / calls_per_day
  interval_h = min(MAX_INTERVAL_H, max(MIN_INTERVAL_H, interval_h))
  return {"cap": cap, "used": used, "calls": calls, "remaining": remaining, "monthly": monthly_units,
          "days_left": days, "interval_h": interval_h, "can_call": remaining >= units_per_call}


def due_for_refresh(db, now, state, force=False):
  """(çekilmeli_mi, neden)"""
  if not state["can_call"]:
    return False, "bütçe bitti"
  last = db.meta_get("fids_last_fetch")
  last_dt = parse_local(last) if last else None
  age_h = (now.replace(tzinfo=None) - last_dt).total_seconds() / 3600 if last_dt else 999
  if force:
    return (True, "elle") if age_h * 60 >= 2 else (False, "az önce çekildi")
  if age_h < MIN_INTERVAL_H:
    return False, "yakın zamanda çekildi"
  if age_h >= state["interval_h"]:
    return True, "süre doldu"
  # Önbellekte ileriye dönük yeterli satır yoksa (ör. gün sonu), alt sınırdan sonra çek
  n_ahead = 999
  for d in ("ARR", "DEP"):
    ahead = db.fids_between(d, to_iso(now), to_iso(now + timedelta(hours=6)))
    n_ahead = min(n_ahead, len(ahead))
  if n_ahead < 5 and age_h >= 2:
    return True, "önbellek tükeniyor"
  return False, "taze"


def _call(http, key, host, from_iso, to_iso_, timeout=25):
  url = (f"https://{host}/flights/airports/icao/{AIRPORT_ICAO}/{from_iso}/{to_iso_}")
  params = {"direction": "Both", "withLeg": "true", "withCancelled": "true", "withCodeshared": "false",
            "withCargo": "false", "withPrivate": "false", "withLocation": "false"}
  headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": host, "Accept": "application/json"}
  return http.get(url, headers=headers, params=params, timeout=timeout)


def refresh(db, key, now, http=None, host=ADB_HOST, monthly_units=DEFAULT_MONTHLY_UNITS,
            units_per_call=DEFAULT_UNITS_PER_CALL, force=False, max_calls=2):
  """Gerekliyse tarifeyi çeker. Sonuç sözlüğü döner; asla istisna fırlatmaz."""
  res = {"fetched": False, "reason": "", "ok": True, "calls": 0, "error": ""}
  if not key:
    res.update(reason="anahtar yok", ok=False)
    return res
  if http is None:
    import requests as http  # noqa: PLC0415
  if not db.fetch_lock.acquire(blocking=False):
    res.update(reason="başka oturum çekiyor")
    return res
  try:
    state = budget_state(db, now, monthly_units, units_per_call)
    due, why = due_for_refresh(db, now, state, force=force)
    res["reason"] = why
    if not due:
      return res
    # Başarısız denemeler de zaman damgasını ilerletir: hata anında API'yi yormayalım
    db.meta_set(fids_last_fetch=to_iso(now))
    start = now - timedelta(hours=PAST_H)
    got_arr = got_dep = 0
    windows = [(start, start + timedelta(hours=WINDOW_H - 0.01))]
    errors = []
    i = 0
    while i < len(windows) and res["calls"] < max_calls:
      w0, w1 = windows[i]
      i += 1
      cur = budget_state(db, now, monthly_units, units_per_call)
      if not cur["can_call"]:
        errors.append("bütçe bitti")
        break
      try:
        r = _call(http, key, host, to_iso(w0), to_iso(w1))
      except Exception as e:
        errors.append(f"ağ hatası ({type(e).__name__})")
        db.log_fetch(to_iso(now), PROVIDER, to_iso(w0), to_iso(w1), False, note=errors[-1])
        break
      res["calls"] += 1
      if r.status_code == 429:  # istek sınırı: çağrı sayılabilir, birim düşmeyebilir; yine de say
        db.add_usage(month_key(now), PROVIDER, 1, 0)
        errors.append("429 istek sınırı")
        db.log_fetch(to_iso(now), PROVIDER, to_iso(w0), to_iso(w1), False, note=errors[-1])
        break
      if r.status_code != 200:
        body = str(getattr(r, "text", "") or "")[:160].replace("\n", " ")
        db.meta_set(fids_last_diag=f"{to_iso(now)} · HTTP {r.status_code} · {body}")
      if r.status_code in (401, 403):
        errors.append(f"{r.status_code} yetki: anahtar geçersiz ya da abonelik yok")
        db.log_fetch(to_iso(now), PROVIDER, to_iso(w0), to_iso(w1), False, note=errors[-1])
        break
      if r.status_code != 200:
        errors.append(f"HTTP {r.status_code}")
        db.log_fetch(to_iso(now), PROVIDER, to_iso(w0), to_iso(w1), False, note=errors[-1])
        break
      db.add_usage(month_key(now), PROVIDER, 1, units_per_call)
      try:
        js = r.json()
        rows = parse_adb(js)
      except Exception:
        errors.append("yanıt çözümlenemedi")
        db.meta_set(fids_last_diag=f"HTTP 200 · JSON okunamadı")
        db.log_fetch(to_iso(now), PROVIDER, to_iso(w0), to_iso(w1), False, note=errors[-1])
        break
      raw_a = len((js or {}).get("arrivals") or []) if isinstance(js, dict) else 0
      raw_d = len((js or {}).get("departures") or []) if isinstance(js, dict) else 0
      na = sum(1 for x in rows if x["direction"] == "ARR")
      nd = sum(1 for x in rows if x["direction"] == "DEP")
      db.meta_set(fids_last_diag=(f"{to_iso(now)} · HTTP 200 · ham: {raw_a} varış / {raw_d} kalkış · "
                                  f"çözümlenen: {na} / {nd} · yapı: {describe_payload(js)}"))
      if not rows:
        if raw_a + raw_d > 0:
          errors.append("uçuşlar çözümlenemedi (yanıt biçimi beklenenden farklı)")
        else:
          errors.append("API bu aralık için uçuş döndürmedi")
        db.log_fetch(to_iso(now), PROVIDER, to_iso(w0), to_iso(w1), False, note=errors[-1])
        break                                   # boş yanıtta ikinci pencereyle kota harcama
      db.upsert_fids(rows, to_iso(now))
      got_arr += na
      got_dep += nd
      db.log_fetch(to_iso(now), PROVIDER, to_iso(w0), to_iso(w1), True, na, nd)
      res["fetched"] = True
      # Gelecekte hedef satır sayısına ulaşılmadıysa bir sonraki 12 saati de iste
      if len(windows) == 1:
        short = False
        for d in ("ARR", "DEP"):
          if len(db.fids_between(d, to_iso(now - timedelta(minutes=45)), to_iso(now + timedelta(hours=36)))) < MIN_ROWS + 4:
            short = True
        if short:
          windows.append((w1 + timedelta(minutes=1), w1 + timedelta(hours=WINDOW_H)))
    if errors:
      res["ok"] = res["fetched"]
      res["error"] = "; ".join(errors)
      db.meta_set(fids_last_error=res["error"])
    else:
      db.meta_set(fids_last_error="", fids_last_ok=to_iso(now))
    if res["fetched"]:
      db.meta_set(fids_last_ok=to_iso(now))
    db.prune(to_iso(now - timedelta(days=2)))
    return res
  except Exception as e:  # güvenlik ağı
    res.update(ok=False, error=f"{type(e).__name__}", reason="hata")
    return res
  finally:
    db.fetch_lock.release()


def data_age_min(db, now):
  ok = parse_local(db.meta_get("fids_last_ok") or "")
  if not ok:
    return None
  return max(0, int((now.replace(tzinfo=None) - ok).total_seconds() // 60))


# =============================================================================
# Demo tarifesi (anahtar olmadan arayüzü denemek için; veritabanına YAZILMAZ)
# =============================================================================
_DEMO_PLACES = [
    ("AGP", "Malaga", "ES"), ("PMI", "Palma de Mallorca", "ES"), ("ALC", "Alicante", "ES"),
    ("BCN", "Barselona", "ES"), ("IST", "İstanbul", "TR"), ("SAW", "İstanbul Sabiha Gökçen", "TR"),
    ("AYT", "Antalya", "TR"), ("ATH", "Atina", "GR"), ("HER", "Girit", "GR"), ("FAO", "Faro", "PT"),
    ("LIS", "Lizbon", "PT"), ("VCE", "Venedik", "IT"), ("NAP", "Napoli", "IT"), ("KRK", "Krakow", "PL"),
    ("WAW", "Varşova", "PL"), ("SOF", "Sofya", "BG"), ("BUD", "Budapeşte", "HU"), ("DUB", "Dublin", "IE"),
    ("LTN", "Londra Luton", "GB"), ("STN", "Londra Stansted", "GB"), ("PRG", "Prag", "CZ"),
    ("OPO", "Porto", "PT"), ("TFS", "Tenerife", "ES"), ("DBV", "Dubrovnik", "HR"),
]
_DEMO_AIRLINES = [("Transavia", "HV", "TRA"), ("Ryanair", "FR", "RYR"), ("Wizz Air", "W6", "WZZ"),
                  ("TUI fly", "OR", "TFL"), ("Pegasus", "PC", "PGT")]
_DEMO_TYPES = ["Boeing 737-800", "Airbus A320", "Airbus A321neo", "Boeing 737 MAX 8", "Airbus A320neo"]


def demo_rows(now, per_direction=26):
  """Deterministik örnek tarife: her yönde `per_direction` uçuş, çeşitli durumlar ve gecikmeler."""
  base = now.replace(tzinfo=None, minute=0) - timedelta(hours=1)
  rows = []
  for direction in ("ARR", "DEP"):
    for i in range(per_direction):
      al_name, iata, icao = _DEMO_AIRLINES[(i * 3 + (1 if direction == "DEP" else 0)) % len(_DEMO_AIRLINES)]
      pi, pn, pc = _DEMO_PLACES[(i * 5 + (2 if direction == "DEP" else 0)) % len(_DEMO_PLACES)]
      sched = base + timedelta(minutes=18 * i + (7 if direction == "DEP" else 0))
      delay = [0, 0, 0, 12, 0, 25, 0, 0, 47, 0, 0, 6, 0, -8][i % 14]
      est = sched + timedelta(minutes=delay) if delay else None
      past = sched < now.replace(tzinfo=None) - timedelta(minutes=5)
      soon = not past and sched < now.replace(tzinfo=None) + timedelta(minutes=40)
      if i % 17 == 9:
        status = "canceled"
      elif past:
        status = "departed" if direction == "DEP" else "arrived"
      elif soon:
        status = ("boarding" if i % 2 else "gateclosed") if direction == "DEP" else "approaching"
      else:
        status = "expected"
      actual = (sched + timedelta(minutes=delay)) if past and status != "canceled" else None
      num = f"{iata}{1000 + (i * 37) % 8000}"
      rows.append({
          "key": f"demo-{direction}-{i}", "direction": direction, "number": f"{iata} {num[len(iata):]}",
          "callsign": f"{icao}{num[len(iata):]}", "airline": al_name, "airline_iata": iata,
          "airline_icao": icao, "other_iata": pi, "other_icao": None, "other_city": pn, "other_cc": pc,
          "sched_local": to_iso(sched), "est_local": to_iso(est) if est else None,
          "actual_local": to_iso(actual) if actual else None, "status": status,
          "terminal": None, "gate": (f"{'ABC'[i % 3]}{1 + i % 9}" if direction == "DEP" and status in ("boarding", "gateclosed", "expected") else None),
          "aircraft": _DEMO_TYPES[i % len(_DEMO_TYPES)], "reg": f"PH-{chr(65 + i % 26)}{chr(70 + (i * 3) % 20)}{chr(75 + (i * 7) % 15)}",
      })
  return rows


def select_demo(direction, now, limit=MIN_ROWS, query="", past_min=45):
  out = [board_row(r, now) for r in demo_rows(now) if r["direction"] == direction]
  floor = now.replace(tzinfo=None) - timedelta(minutes=past_min)
  out = [r for r in out if r["dt"] >= floor]
  out.sort(key=lambda r: r["sched_local"])
  if query:
    out = [r for r in out if board_matches(r, query)]
  return out[:limit], len(out)
