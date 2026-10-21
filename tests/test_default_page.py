import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar
import radar_auth

fails = []
def chk(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

# 1) Varsayılan sayfa Radar (PAGES[0])
H.reset_app({"APP_PASSWORD": "p", "AERODATABOX_KEY": "k"})
H.run(); fake.session_state._force("Şifre", "p"); fake.pressed = {"Giriş yap"}; H.run()
chk("uygulama doğrudan Radar ile açılır", fake.session_state["page"] == radar.PAGES[0])

# 2) URL anahtarı (?k=...) ile şifresiz otomatik giriş
H.reset_app({"APP_PASSWORD": "p", "AERODATABOX_KEY": "k"})
fake.query_params = {"k": radar_auth.make_token("p")}
H.run()
chk("URL token ile şifresiz giriş çalışır", fake.session_state.get("auth_ok") is True)
fake.query_params = {}

# 3) FIDS + Radar birleştirme, Gökyüzü Pusulası ve Çocuk Karşılaştırması
db = radar.get_db()
db.upsert_fids([{
    "key": "fids1", "direction": "ARR", "number": "HV 6672", "callsign": "TRA6672",
    "airline": "Transavia", "airline_iata": "HV", "airline_icao": "TRA",
    "other_iata": "AYT", "other_icao": "LTAI", "other_city": "Antalya", "other_cc": "TR",
    "sched_local": "2099-01-01T14:20", "est_local": "2099-01-01T14:35", "actual_local": None,
    "status": "Approaching", "terminal": "1", "gate": "A2", "aircraft": "B738", "reg": "PH-HXA",
}], "2099-01-01T12:00")
fmap = db.fids_lookup_map("2099-01-01T00:00", "2099-01-02T00:00")
store = radar.get_store()
states = [H.row("484001", "TRA6672 ", radar.HOME_LAT + 0.004, radar.HOME_LON, 2800, 320, 215, -3.5)]
flights = radar.build_flights(states, store, fids_map=fmap)
f0 = flights[0]
chk("FIDS verisi rotası bilinmeyen uçağı zenginleştirir (Antalya -> Eindhoven)",
    f0["route_known"] and f0["origin"]["city"] == "Antalya" and f0["fids"]["gate"] == "A2")
chk("Gökyüzü pusulası yön ve açı üretir",
    bool(f0.get("look_dir")) and f0.get("elev_deg", 0) > 0 and "°" in f0.get("look_hint", ""))
chk("Çocuk dostu hız/irtifa karşılaştırması üretilir",
    "Formula 1" in radar.kid_comparison(f0) or "Eyfel" in radar.kid_comparison(f0))

# 4) Bahçe üstündeki özel çağrı kodlu (LIFELINER) uçak gizlenmez ve rozetler çizilir
states_unk = [H.row("484999", " lifeliner ", radar.HOME_LAT + 0.001, radar.HOME_LON, 1200, 210, 180, 0.0)]
fl_unk = radar.build_flights(states_unk, store, fids_map={})
chk("Özel çağrı kodu (LIFELINER) tanınır ve gizlenmez", len(fl_unk) == 1 and "Lifeliner" in fl_unk[0]["airline"])
st_stats = db.sighting_stats("2099-01-01", "2099-01-01")
chk("Rozet koleksiyonu HTML üretir", "Atlas'ın Rütbesi:" in radar.badges_html(st_stats))

# 5) Uçtan uca Fonksiyonel UI Testi: Pusula kutusu, FIDS eşleşme kartı, Sesli uyarı ve Manuel Defter Kaydı
H.reset_app({"APP_PASSWORD": "p", "AERODATABOX_KEY": "k"})
H.Net.states = [H.row("484001", "TRA6672", radar.HOME_LAT + 0.004, radar.HOME_LON, 2200, 310, 215, -3.5)]
H.login("p")
db2 = radar.get_db()
now_iso = radar.fids.to_iso(radar.fids.now_local())
db2.upsert_fids([{
    "key": "fids_live1", "direction": "ARR", "number": "HV 6672", "callsign": "TRA6672",
    "airline": "Transavia", "airline_iata": "HV", "airline_icao": "TRA",
    "other_iata": "AYT", "other_icao": "LTAI", "other_city": "Antalya", "other_cc": "TR",
    "sched_local": now_iso, "est_local": now_iso, "actual_local": None,
    "status": "Approaching", "terminal": "1", "gate": "A2", "aircraft": "B738", "reg": "PH-HXA",
}], now_iso)
fake.session_state._force("f_sound", True)
H.run()
html_out = "\n".join(fake.md)
chk("Radar detay panelinde Gökyüzü Pusulası (.compass-box) çizilir", "compass-box" in html_out and "Nereye Bakmalı?" in html_out)
chk("Radar detay panelinde Terminal FIDS eşleşmesi (.fids-match) çizilir", "fids-match" in html_out and "Kapı <b>A2</b>" in html_out)
chk("Radar detay panelinde Çocuk Karşılaştırması (.fact) çizilir", "class='fact'" in html_out and "Otobandaki bir arabadan" in html_out)
chk("Bahçe sesli uyarısı açıkken kokpit çanı (AudioContext) tetiklenir", "AudioContext" in html_out)
chk("Manuel Gözlem Defteri kayıt düğmesi (spot_manual_btn) görünür", "spot_manual_btn" in fake.buttons)

# Manuel kayıt düğmesine bas ve Gözlem Defteri sayfasında rozetleri kontrol et
H.press("spot_manual_btn")
fake.session_state._force("page", radar.PAGES[2])
H.run()
diary_html = "\n".join(fake.md)
chk("Gözlem Defteri sayfasında rütbe ve 8 rozet (.rank-box, .badge-grid) çizilir",
    "rank-box" in diary_html and "badge-grid" in diary_html and "İlk Av" in diary_html)

print("\nBAŞARISIZ:", ", ".join(fails) if fails else "yok")
sys.exit(1 if fails else 0)

