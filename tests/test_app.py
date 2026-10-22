import sys, os, re, time
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar, Net, SF, run, press, login, row, ap, adb_payload
from fakes import FakeGH

FAILS = []
def ck(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name + (f"   [{info}]" if (info and not cond) else ""))
    if not cond: FAILS.append(name)

ALL_MD = []
_run = H.run
def run_all():
    n = _run(); ALL_MD.extend(fake.md); return n
H.run = run_all; run = run_all
P = radar.PAGES
PAGE_TERM, PAGE_DIARY, PAGE_RADAR = "🛫 Terminal", "📒 Gözlem Defteri", "🛰️ Radar"
def login(pw="gizli"):
    fake.session_state._force("Şifre", pw); fake.session_state._force("page", PAGE_RADAR); fake.pressed = {"Giriş yap"}; return run_all()
def press(key):
    cb, args = fake.buttons[key]
    if cb: cb(*args)
    fake.pressed = {key}; return run_all()

SECRETS = {"APP_PASSWORD": "gizli", "AERODATABOX_KEY": "adbkey-123", "GITHUB_TOKEN": "ghtok-456",
           "GITHUB_REPO": "Blixembosch/atlasradar"}
P = radar.PAGES
def md(): return "\n".join(fake.md)
def set_ss(k, v): fake.session_state._force(k, v)
def markers(): return SF.calls[-1][0].markers()
def n_rows(panel): return panel.count("class='frow")
def panels():
    a = next((x for x in fake.md if "tphead arr" in x), ""); d = next((x for x in fake.md if "tphead dep" in x), "")
    return a, d

TRA_ROUTE = {"airline": {"name": "Transavia", "icao": "TRA", "iata": "HV"},
             "origin": ap("ATH", "LGAV", "Athens", "GR", 37.9, 23.9),
             "destination": ap("EIN", "EHEH", "Eindhoven", "NL", 51.45, 5.37)}
def setup_world():
    Net.states = [row("a1", "TRA6710", 51.5050, 5.5200, 2400, 275, 215, -4),
                  row("b2", "ZZZ999", 51.5300, 5.5350, 3000, 280, 215, -5),
                  row("c3", "RYR4123", 51.5100, 5.4500, 2800, 270, 215, -4)]
    Net.routes = {"TRA6710": TRA_ROUTE}
    Net.route_err = {"RYR4123"}
    Net.gh = FakeGH(branch=False)

# ================= 1) Şifre kapısı
H.reset_app(SECRETS); setup_world(); run()
ck("giriş ekranı çizildi", "login-card" in md() and "Atlas'ın Uçak Gözlem Kulesi" in md())
ck("giriş yokken hiçbir ağ çağrısı yok", sum(Net.calls.values()) == 0, Net.calls)
ck("giriş yokken otomatik yenileme yok", fake.refresh is None)
ck("giriş yokken gezinme/harita yok", "<div class='topbar'>" not in md() and not SF.calls)
login("yanlis")
ck("yanlış şifre reddedilir", any("yanlış" in e for e in fake.errors) and not fake.session_state.get("auth_ok"))
ck("yanlış şifrede hâlâ ağ çağrısı yok", sum(Net.calls.values()) == 0, Net.calls)
ck("yanlış şifre ekranda gösterilmez", "yanlis" not in md())

# ================= 2) Giriş + radar
login("gizli")
set_ss("page", PAGE_RADAR); run()
ck("doğru şifre: uygulama açıldı", fake.session_state.get("auth_ok") and "<div class='topbar'>" in md())
ck("OpenSky çağrıldı", Net.calls["opensky"] >= 1)
ck("GitHub'dan çekme denendi (veri dalı yok)", Net.calls["github"] >= 1)
mk = markers()
ck("rotası bilinmeyen (ZZZ999) haritada YOK, diğer 2 uçak var", len(mk) == 2, len(mk))
ck("gizlenen sayısı çipte (1)", "🙈 <b>1</b>" in md())
ck("rotası bilinmeyen kartlarda yok", "ZZZ999" not in md())
ck("geçici hatalı uçak (RYR4123) gizlenmedi", "RYR4123" in md())
ck("hata durumunda 'Rota aranıyor' yazar", "Rota aranıyor" in md())
ck("rotası bilinen uçak (TRA6710) var", "TRA6710" in md() and "ATH" in md())
set_ss("f_unk", True); run()
ck("'bilinmeyenleri göster' açılınca 3 uçak", len(markers()) == 3 and "🙈" not in md())
set_ss("f_unk", False); run()
ck("kapatınca tekrar 2 uçak", len(markers()) == 2)

# geçici hata düzelince rota gelir
Net.routes["RYR4123"] = {"airline": {"name": "Ryanair", "icao": "RYR", "iata": "FR"},
                         "origin": ap("AGP", "LEMG", "Málaga", "ES", 36.6, -4.4),
                         "destination": ap("EIN", "EHEH", "Eindhoven", "NL", 51.45, 5.37)}
Net.route_err = set()
radar.get_store()[("route", "RYR4123")] = (0, {"_state": "err"})   # kısa önbellek süresi doldu
run()
ck("hata düzelince rota görünür", "Rota aranıyor" not in md() and "AGP" in md())

# ================= 3) Gözlem kaydı
db = radar.get_db()
today_str = datetime.now(radar.TZ).strftime("%Y-%m-%d")
st_ = db.sighting_stats(today_str, "2000-01-01")
ck("bahçeden görünen + rotası bilinen uçak deftere yazıldı", st_["today"] >= 1, st_)
rs = db.recent_sightings()
ck("rotasız uçak deftere yazılmadı", all(r["callsign"] != "ZZZ999" for r in rs))

# ================= 4) Sayfalar arası durum korunur
fake.secrets.pop("AERODATABOX_KEY")
set_ss("f_over", True); run()
set_ss("page", PAGE_TERM); set_ss("fids_view", "Tüm gün"); run()
ck("terminal sayfasında radar bileşen anahtarı silinir (Streamlit davranışı)", "f_over" not in fake.session_state)
set_ss("page", PAGE_RADAR); run()
ck("radara dönünce 'Üstümüzden geçenler' hâlâ açık", fake.session_state.get("f_over") is True)
set_ss("f_over", False); run()

# ================= 5) Terminal: anahtar yok
set_ss("page", PAGE_TERM); set_ss("fids_view", "Tüm gün"); run()
ck("anahtar yokken boş durum açıklaması", "AERODATABOX_KEY" in md())
ck("anahtar yokken AeroDataBox çağrısı yok", Net.calls["adb"] == 0)
ck("iki panel de çizildi (Varış/Kalkış)", "tphead arr" in md() and "tphead dep" in md())

# ================= 6) Terminal: anahtar var
fake.secrets["AERODATABOX_KEY"] = "adbkey-123"
Net.adb_json = adb_payload(); run()
a, d = panels()
ck("AeroDataBox 1 kez çağrıldı", Net.calls["adb"] == 1, Net.calls["adb"])
ck("varış panelinde en az 20 uçuş", n_rows(a) >= 20, n_rows(a))
ck("kalkış panelinde en az 20 uçuş", n_rows(d) >= 20, n_rows(d))
ck("tam 20 satır (varsayılan)", n_rows(a) == 20 and n_rows(d) == 20)
ck("Durum ve Gecikme ayrı sütun başlıkları", all(">Durum<" in x and "Gecikme<" in x for x in (a, d)))
ck("gecikme değeri gösteriliyor", "+20 dk" in a and "+20 dk" in d)
ck("kalkışta Kapı sütunu var, varışta yok", ">Kapı<" in d and ">Kapı<" not in a)
ck("bayrak ve şehir", "🇪🇸" in a and "Malaga" in a and "İstanbul" in d)
ck("havayolu logosu sınıfı (CSS bir kez)", ".alogo.k-TRA" in md() and md().count(".alogo.k-TRA{") == 1)
ck("sıradaki uçuş vurgusu", "frow fgrid arr next" in a or "frow fgrid arr " in a and "next" in a)
ck("canlı/güncel etiketi", "Güncel" in md())
ck("saat başlığı", "Eindhoven Airport" in md() and "EIN · EHEH" in md())
ck("kota bilgisi", "kota birimi" in md())
run()
ck("tekrar çizimde API çağrısı yok (taze)", Net.calls["adb"] == 1)
ck("AeroDataBox anahtarı ekranda yok", "adbkey-123" not in "\n".join(ALL_MD))
ck("terminal yenileme 60 sn", fake.refresh == 60000)
# veritabanında
rows_dep = db.fids_between("DEP", "2000", "2100")
ck("tarife veritabanına yazıldı", len(rows_dep) >= 30)
month_str = datetime.now(radar.TZ).strftime("%Y-%m")
ck("kota sayacı yazıldı", db.usage(month_str, "aerodatabox")[0] == 1)

# arama
set_ss("fids_q", "malaga"); run()
a2, d2 = panels()
ck("arama: sadece Malaga", 0 < n_rows(a2) < 20 and "İstanbul" not in a2)
set_ss("fids_q", "b3"); run()
a3, d3 = panels()
ck("arama: kapı B3 (kalkış)", 0 < n_rows(d3) < 20)
set_ss("fids_q", "zzzz-yok"); run()
ck("arama sonuçsuz: boş durum", "eşleşen" in md())
set_ss("fids_q", ""); run()

# daha fazla
ck("'daha fazla' düğmesi var", "fids_more" in fake.buttons)
press("fids_more")
a4, d4 = panels()
ck("daha fazla: 30 satır", n_rows(a4) == 30 and n_rows(d4) == 30, (n_rows(a4), n_rows(d4)))

# tarife tüketilirse önbellekten gösterir
Net.adb_status = 403
db.meta_set(fids_last_fetch="2000-01-01T00:00")     # yenileme zamanı gelmiş say
run()
radar.join_background(); run()
a5, _ = panels()
ck("API hata verse de önbellek gösterilir", n_rows(a5) >= 20)
ck("hata uyarısı gösterilir (anahtar sızmadan)", "güncellenemedi" in md() and "adbkey" not in md())
Net.adb_status = 200

# demo
n_adb = Net.calls["adb"]
set_ss("demo", True); run()
a6, d6 = panels()
ck("demo: her yönde >= 20 uçuş", n_rows(a6) >= 20 and n_rows(d6) >= 20, (n_rows(a6), n_rows(d6)))
ck("demo: API çağrısı yok", Net.calls["adb"] == n_adb)
ck("demo etiketi", "Demo tarife" in md())
set_ss("demo", False); run()

# ================= 7) Defter
set_ss("page", PAGE_DIARY); run()
ck("defter KPI'ları", "kpis" in md() and "Bugün" in md())
ck("defterde TRA6710", "TRA6710" in md())
ck("defter yenileme 120 sn", fake.refresh == 120000)
ck("senkron durumu: GitHub bağlı", "data" in md() and "GitHub" in md())
ck("yedekle düğmesi", "backup_btn" in fake.buttons)
press("backup_btn")
ck("data dalı oluşturuldu + SQLite yüklendi", Net.gh.branch and Net.gh.data and Net.gh.data.startswith(b"SQLite format 3"))
ck("son yedek bilgisi", "son yedek" in md())
ck("token ekranda yok", "ghtok-456" not in "\n".join(ALL_MD))

# ================= 8) Sunucu yeniden başlar (yerel dosya yok) -> data dalından geri gelir
os.remove(os.path.join(H.DBDIR, "radar.db"))
radar.get_db.memo.clear(); radar.get_store.memo.clear()
H.new_session()
run()
ck("yeniden başlayınca yine şifre ister", "login-card" in md())
login("gizli")
set_ss("page", PAGE_DIARY); run()
ck("veri data dalından geri geldi (TRA6710)", "TRA6710" in md())
db = radar.get_db()
ck("tarife de geri geldi", len(db.fids_between("DEP", "2000", "2100")) >= 30)

# ================= 9) Çıkış
press("logout_btn")
ck("çıkış: giriş ekranı", "login-card" in md() and not fake.session_state.get("auth_ok"))

# ================= 10) Şifre tanımsız = kilitli
H.reset_app({"AERODATABOX_KEY": "k"}); setup_world(); run()
ck("APP_PASSWORD yoksa kilitli + açıklama", any("APP_PASSWORD" in e for e in fake.errors))
ck("şifresizken hiçbir ağ çağrısı yok", sum(Net.calls.values()) == 0)
login("")
ck("boş şifre girmez", not fake.session_state.get("auth_ok"))

# ================= 11) GitHub erişilemiyor -> uygulama yine çalışır, uzağa yazılmaz
H.reset_app(SECRETS); setup_world(); Net.gh = FakeGH(branch=True, data=b"SQLite format 3\x00" + b"x" * 100, repo_ok=False)
run(); login("gizli")
ck("GitHub hatasına rağmen radar açıldı", "<div class='topbar'>" in md())
set_ss("page", PAGE_DIARY); run()
ck("hata defterde okunur", "404" in md() or "yetki" in md() or "GitHub" in md())
press("backup_btn")
ck("çekme başarısızken uzağa yazılmadı", not any(m == "PUT" for m, _ in Net.gh.calls))

# ================= 12) Ev konumu secrets ile
H.reset_app({**SECRETS, "HOME_LAT": "52.1", "HOME_LON": "5.1"}); setup_world(); run(); login("gizli")
ck("HOME_LAT/HOME_LON secrets'tan okunur", abs(radar.HOME_LAT - 52.1) < 1e-9 and abs(radar.HOME_LON - 5.1) < 1e-9)
radar.HOME_LAT, radar.HOME_LON = 51.4951, 5.4779

# ================= 13) Tüm çıktıda sır yok
txt = "\n".join(ALL_MD)
ck("çıktıda parola/token yok", "gizli" not in txt.replace("gizli_", "") and "ghtok" not in txt and "adbkey" not in txt)
ck("ev adresi yazmıyor", "Panorama" not in txt and "5629" not in txt)

print("\nBAŞARISIZ:", FAILS if FAILS else "yok")
sys.exit(1 if FAILS else 0)
