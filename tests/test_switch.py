import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar, Net, SF, row, ap
FAILS = []
def ck(n, c, i=""):
    print(("OK   " if c else "FAIL ") + n + (f"   [{i}]" if (i and not c) else ""))
    if not c: FAILS.append(n)
def set_ss(k, v): fake.session_state._force(k, v)
def timed():
    t = time.time(); H.run(); return time.time() - t
P = radar.PAGES
PAGE_TERM, PAGE_DIARY, PAGE_RADAR = "🛫 Terminal", "📒 Gözlem Defteri", "🛰️ Radar"
radar.FETCH_TTL = 8      # gerçek önbellek davranışı
H.reset_app({"APP_PASSWORD": "p"}); Net.gh = None
EIN = ap("EIN", "EHEH", "Eindhoven", "NL", 51.45, 5.37)
Net.routes = {"TRA6710": {"airline": {"name": "Transavia", "icao": "TRA", "iata": "HV"}, "origin": ap("ATH", "LGAV", "Athens", "GR", 37.9, 23.9), "destination": EIN},
              "RYR1": {"airline": {"name": "Ryanair", "icao": "RYR", "iata": "FR"}, "origin": ap("AGP", "LEMG", "Malaga", "ES", 36.7, -4.5), "destination": EIN}}
Net.states = [row("a1", "TRA6710", 51.505, 5.52, 2400, 275, 215, -4)]
# radar'ı açmak için PAGE_RADAR seçilir
set_ss("page", PAGE_RADAR); H.run(); set_ss("Şifre", "p"); fake.pressed = {"Giriş yap"}; H.run()
radar.join_background(); H.run()
ck("radar açıldı, uçak var", len(SF.calls[-1][0].markers()) == 1)
key = list(radar._TCACHE)[0]

# 1) sayfa değişimi: bayat (30 sn) veri beklemeden gösterilir
set_ss("page", PAGE_TERM); H.run()
ts, res = radar._TCACHE[key]; radar._TCACHE[key] = (ts - 30, res)
Net.os_delay = 1.5; n = Net.calls["opensky"]
set_ss("page", PAGE_RADAR); dt = timed()
ck("geçişte bayat veri anında (<0.7 sn), 1.5 sn'lik OpenSky beklenmedi", dt < 0.7 and len(SF.calls[-1][0].markers()) == 1, dt)
radar.join_background()
ck("arka planda tazelendi", Net.calls["opensky"] == n + 1 and time.time() - radar._TCACHE[key][0] < 5)

# 2) normal yenileme (sayfa değişmedi): taze veri beklenir
ts, res = radar._TCACHE[key]; radar._TCACHE[key] = (ts - 30, res)
dt = timed()
ck("normal yenilemede taze veri beklenir (konum bayat gösterilmez)", dt >= 1.4, dt)

# 3) çok eski veri (>120 sn) geçişte de beklenir
set_ss("page", PAGE_TERM); H.run()
ts, res = radar._TCACHE[key]; radar._TCACHE[key] = (ts - 300, res)
set_ss("page", PAGE_RADAR); dt = timed()
ck("120 sn'den eski veri gösterilmez (beklenir)", dt >= 1.4, dt)

# 4) hatalı sonuç bayat olarak servis edilmez
Net.os_delay = 0; set_ss("page", PAGE_TERM); H.run()
radar._TCACHE[key] = (time.time() - 30, ([], "OpenSky zaman aşımı", time.time()))
Net.os_delay = 1.0; set_ss("page", PAGE_RADAR); dt = timed()
ck("hata sonucu bayat servis edilmez", dt >= 0.9, dt)

# 5) logo indirme radarı bekletmez
Net.os_delay = 0; Net.logo_delay = 1.5
Net.states = [row("a1", "TRA6710", 51.505, 5.52, 2400, 275, 215, -4), row("a9", "RYR1", 51.52, 5.50, 3000, 280, 215, -4)]
radar.get_store().clear(); radar._TCACHE.clear()
dt = timed()
ck("logo yokken radar beklemez (<0.8 sn)", dt < 0.8, dt)
ck("logolar inerken kısa yenileme", fake.refresh in (4000, 5000), fake.refresh)
radar.join_background(); H.run()
ck("logo inince 5 sn döngüsü biter", fake.refresh != 5000, fake.refresh)
ck("altbilgide zamanlama", "⏱" in "\n".join(fake.md) and "toplam" in "\n".join(fake.md))

# 6) sayfa gezinme (Terminal <-> Radar <-> Defter) doğrulaması
set_ss("page", PAGE_TERM); H.run()
ck("Terminal sayfasına başarıyla geçildi", fake.session_state["page"] == PAGE_TERM and any("Tarife" in m or "Uçuş" in m or "Görünüm" in m or "fids" in str(fake.rendered) for m in fake.md + list(fake.rendered)))

set_ss("page", PAGE_DIARY); H.run()
ck("Gözlem defteri sayfasına başarıyla geçildi", fake.session_state["page"] == PAGE_DIARY and any("Gözlem Defteri" in m or "rozet" in m.lower() for m in fake.md))

set_ss("page", PAGE_RADAR); H.run()
ck("Radar sayfasına başarıyla geri dönüldü", fake.session_state["page"] == PAGE_RADAR and len(SF.calls[-1][0].markers()) >= 1)

print("\nBAŞARISIZ:", FAILS if FAILS else "yok")
sys.exit(1 if FAILS else 0)
