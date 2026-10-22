import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar, Net, SF, row, ap
FAILS = []
def ck(n, c, i=""):
    print(("OK   " if c else "FAIL ") + n + (f"   [{i}]" if (i and not c) else ""))
    if not c: FAILS.append(n)
def set_ss(k, v): fake.session_state._force(k, v)
P = radar.PAGES
radar.FETCH_TTL = 8
radar._WARM.update(t=0.0, busy=False)
H.reset_app({"APP_PASSWORD": "p"}); Net.gh = None
EIN = ap("EIN", "EHEH", "Eindhoven", "NL", 51.45, 5.37)
Net.routes = {"TRA6710": {"airline": {"name": "Transavia", "icao": "TRA", "iata": "HV"}, "origin": ap("ATH", "LGAV", "Athens", "GR", 37.9, 23.9), "destination": EIN}}
Net.states = [row("a1", "TRA6710", 51.505, 5.52, 2400, 275, 215, -4)]
radar.get_store().clear(); radar._TCACHE.clear()
radar.DEFAULT_PAGE = P[0]                       # gerçek davranış: Terminal ile açılış
H.run(); set_ss("Şifre", "p"); fake.pressed = {"Giriş yap"}; H.run()
radar.join_background()
ck("Terminal açıkken trafik arka planda çekildi", Net.calls["opensky"] + Net.calls["adsblol"] >= 1, dict(Net.calls))
ck("rota önceden alındı", Net.calls["adsbdb"] >= 1)
n = (Net.calls["opensky"], Net.calls["adsblol"], Net.calls["adsbdb"])
Net.os_delay = 1.5; Net.logo_delay = 0
set_ss("page", "🛰️ Radar"); t = time.time(); H.run(); dt = time.time() - t
ck("Radar'a geçiş anında (yavaş kaynak beklenmedi)", dt < 0.7 and len(SF.calls[-1][0].markers()) == 1, dt)
ck("geçişte yeni ağ çağrısı yok", (Net.calls["opensky"], Net.calls["adsblol"], Net.calls["adsbdb"]) == n, (n, dict(Net.calls)))
print("\nBAŞARISIZ:", FAILS if FAILS else "yok"); sys.exit(1 if FAILS else 0)
