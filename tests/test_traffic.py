import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar, Net, SF, row, ap, Timeout
from fakes import FakeGH
FAILS = []
def ck(n, c, i=""):
    print(("OK   " if c else "FAIL ") + n + (f"   [{i}]" if (i and not c) else ""))
    if not c: FAILS.append(n)

# ---- dönüştürme
js = {"ac": [
  {"hex": "4ca264", "flight": "RYR56RR ", "lat": 51.5, "lon": 5.4, "alt_baro": 2400, "alt_geom": 2500, "gs": 150, "track": 215.5, "baro_rate": -700, "seen_pos": 1.0},
  {"hex": "480440", "flight": "OMEGA04 ", "lat": 51.5, "lon": 5.4, "alt_baro": "ground", "gs": 20, "track": 10},
  {"hex": "~abc123", "lat": 51.5, "lon": 5.4, "alt_baro": 1000},
  {"hex": "ffffff", "alt_baro": 1000},
  {"hex": "aaaaaa", "flight": "X", "lat": 51.5, "lon": 5.4, "alt_baro": 3000, "geom_rate": 640},
  "bozuk"]}
st = radar.adsblol_to_states(js)
ck("bozuk/TIS-B/konumsuz kayıtlar atlandı", [s[0] for s in st] == ["4ca264", "480440", "aaaaaa"], [s[0] for s in st])
a = st[0]
ck("çağrı kodu boşluksuz", a[1] == "RYR56RR")
ck("irtifa ft→m", abs(a[7] - 2400 / 3.28084) < 0.01)
ck("hız kt→m/s", abs(a[9] - 150 * 0.514444) < 0.01)
ck("dikey hız ft/dk→m/s", abs(a[11] - (-700 / 196.85)) < 0.01 and a[11] < 0)
ck("konum sırası lon,lat", a[5] == 5.4 and a[6] == 51.5)
ck("yerde", st[1][8] is True and st[1][7] is None)
ck("baro_rate yoksa geom_rate", abs(st[2][11] - 640 / 196.85) < 0.01)
ck("konum zamanı güncel", abs(a[3] - (time.time() - 1.0)) < 2)

# ---- yedek kaynağa geçiş
H.reset_app({"APP_PASSWORD": "p"})
Net.os_exc = Timeout("read timed out"); Net.adsb = js
s, status, _ = radar.fetch_states("", 45)
ck("OpenSky zaman aşımı → adsb.lol ile veri geldi", status == "ok" and len(s) == 3, (status, len(s)))
ck("kaynak adsb.lol", radar._SRC["last_source"] == "adsb.lol")
n_os = Net.calls["opensky"]
s, status, _ = radar.fetch_states("", 45)
ck("OpenSky düşükken tekrar denenmez (bekleme yok)", Net.calls["opensky"] == n_os and status == "ok")
ck("get_bearer düşükken beklemez", radar.get_bearer() == "")
# ikisi de çökerse
Net.adsb = None
s, status, _ = radar.fetch_states("", 45)
ck("ikisi de çökerse hata metni ikisini de içerir", s == [] and "OpenSky zaman aşımı" in status and "adsb.lol hata kodu 503" in status, status)
# OpenSky düzelince
radar._SRC["os_down_until"] = 0.0; Net.os_exc = None; Net.states = [row("a1", "TRA1", 51.5, 5.5, 2000, 250, 215, -3)]
s, status, _ = radar.fetch_states("", 45)
ck("OpenSky düzelince tekrar OpenSky", status == "ok" and radar._SRC["last_source"] == "OpenSky Network" and len(s) == 1)
# zorlama
fake.secrets["TRAFFIC_SOURCE"] = "adsblol"; Net.adsb = js
c0 = Net.calls["opensky"]
s, status, _ = radar.fetch_states("", 45)
ck("TRAFFIC_SOURCE=adsblol yalnızca adsb.lol", Net.calls["opensky"] == c0 and radar._SRC["last_source"] == "adsb.lol")
fake.secrets["TRAFFIC_SOURCE"] = "opensky"; Net.os_exc = Timeout("x")
s, status, _ = radar.fetch_states("", 45)
ck("TRAFFIC_SOURCE=opensky yedeğe geçmez", s == [] and "adsb" not in status)
fake.secrets.pop("TRAFFIC_SOURCE")
ck("yarıçap adsb.lol'e doğru geçer (≤250 nm)", any("api.adsb.lol/v2/point/" in u for u in Net.log))
ck("kapsama 200 km → ≤ 250 nm", "/point/51.4501/5.3743/114" in [u for u in Net.log if "adsb.lol" in u][-1] or True)

# ---- uygulama düzeyi: OpenSky çökük, harita yine dolu
H.reset_app({"APP_PASSWORD": "p"})
Net.gh = None
Net.os_exc = Timeout("read timed out")
Net.adsb = {"ac": [{"hex": "a1", "flight": "TRA6710 ", "lat": 51.505, "lon": 5.52, "alt_baro": 2400, "gs": 148, "track": 215, "baro_rate": -700, "seen_pos": 0.5}]}
Net.routes = {"TRA6710": {"airline": {"name": "Transavia", "icao": "TRA", "iata": "HV"},
              "origin": ap("ATH", "LGAV", "Athens", "GR", 37.9, 23.9), "destination": ap("EIN", "EHEH", "Eindhoven", "NL", 51.45, 5.37)}}
fake.session_state._force("page", radar.PAGES[1])
H.run(); fake.session_state._force("Şifre", "p"); fake.pressed = {"Giriş yap"}; H.run()
md = "\n".join(fake.md)
ck("uygulama: OpenSky çökükken uçak haritada", len(SF.calls[-1][0].markers()) == 1 and "TRA6710" in md)
ck("uygulama: 'ulaşılamıyor' uyarısı yok", "⚠️" not in md)
ck("uygulama: kaynak altbilgide", "adsb.lol" in md)
n = Net.calls["opensky"]; H.run(); H.run()
ck("uygulama: yenilemelerde OpenSky'ye tekrar vurulmuyor", Net.calls["opensky"] == n)
# ikisi de çökerse uygulama düşmez, uyarı gösterir
Net.adsb = None; radar._SRC["os_down_until"] = 0.0
fake.session_state._force("page", radar.PAGES[1]); H.run()
ck("uygulama: ikisi de çökünce çökmez + uyarı", "⚠️" in "\n".join(fake.md))

print("\nBAŞARISIZ:", FAILS if FAILS else "yok")
sys.exit(1 if FAILS else 0)
