"""Uçtan uca PERFORMANS testleri: gerçekçi ağ gecikmeleriyle (zaman ölçeği küçültülmüş) kullanıcı yolculuğu.

Ölçülen şey: kullanıcı bir şey yaptıktan sonra ekran ne kadar sürede çiziliyor (script çalışma süresi).
Bütçeler, yavaş ağ çağrılarının (GitHub, OpenSky zaman aşımı, adsbdb, hava durumu, foto) sayfayı
BEKLETMEDİĞİNİ garanti eder. Gerçek gecikmeler = bu testteki değerler / SCALE.
"""
import sys, os, time, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar, Net, SF, row, ap, adb_payload, FakeGH
import radar_fids as F, radar_db
SCALE = float(os.environ.get("PERF_SCALE", "0.3"))       # 1.0 = gerçek gecikmeler
FAILS, TIMES = [], []
def ck(n, c, i=""):
    print(("OK   " if c else "FAIL ") + n + (f"   [{i}]" if (i and not c) else ""))
    if not c: FAILS.append(n)
def set_ss(k, v): fake.session_state._force(k, v)
def md(): return "\n".join(fake.md)
def timed(label=None):
    t = time.time(); H.run(); dt = time.time() - t
    if label: TIMES.append((label, dt))
    return dt
P = radar.PAGES
# gerçek dünyada tipik gecikmeler (sn) × SCALE
LAT = {"github": 1.0, "adsblol": 0.8, "adsbdb": 0.3, "aircraft": 0.3, "photo": 0.5, "meteo": 0.4}
OPENSKY_TIMEOUT = 5.0
LOGO, ADB = 0.4, 1.2
BUDGET_PAINT = 0.35          # bir çizimin en fazla süresi (sn): yavaş çağrı beklenmemeli
BUDGET_PAINT_STEADY = 0.25

def setup(github_rows=True, opensky_down=True):
    radar.DEFAULT_PAGE = P[1]
    radar.COLD_NONBLOCK = True; radar.FETCH_TTL = 8
    H.BG_SYNC["on"] = True
    H.reset_app({"APP_PASSWORD": "p", "AERODATABOX_KEY": "k", "GITHUB_TOKEN": "t", "GITHUB_REPO": "o/r"})
    Net.lat = {k: v * SCALE for k, v in LAT.items()}
    Net.logo_delay = LOGO * SCALE; Net.adb_delay = ADB * SCALE
    if opensky_down:
        Net.os_delay = OPENSKY_TIMEOUT * SCALE; Net.os_exc = TimeoutError("read timed out")
    # uzak veritabanı: dolu tarife, taze zaman damgaları
    d = tempfile.mkdtemp(); rdb = radar_db.RadarDB(os.path.join(d, "x.db"))
    if github_rows:
        rows = F.parse_adb(adb_payload(32))
        now_iso = F.to_iso(F.now_local())
        rdb.upsert_fids(rows, now_iso)
        rdb.meta_set(fids_last_fetch=now_iso, fids_last_ok=now_iso, fids_parser=radar.APP_VERSION)
        rdb.add_usage(F.month_key(F.now_local()), "aerodatabox", 8, 16)
    Net.gh = FakeGH(branch=True, data=rdb.snapshot_bytes())
    # trafik: 15 uçak EIN'e iniyor/kalkıyor (adsb.lol biçiminde)
    EIN = ap("EIN", "EHEH", "Eindhoven", "NL", 51.45, 5.37)
    ac, routes = [], {}
    for i in range(15):
        cs = f"TRA{6000 + i}"
        ac.append({"hex": f"a{i:05x}", "flight": cs + " ", "lat": 51.50 + i * 0.004, "lon": 5.50 + i * 0.003,
                   "alt_baro": 2000 + i * 100, "gs": 150, "track": 215, "baro_rate": -700, "seen_pos": 0.5})
        routes[cs] = {"airline": {"name": "Transavia", "icao": "TRA", "iata": "HV"},
                      "origin": ap("ATH", "LGAV", "Athens", "GR", 37.9, 23.9), "destination": EIN}
    Net.adsb = {"ac": ac}; Net.routes = routes
    Net.aircraft = {a["hex"]: {"icao_type": "B738", "registration": "PH-X%02d" % i} for i, a in enumerate(ac)}
    radar.get_store().clear()

def login():
    H.run(); set_ss("Şifre", "p"); fake.pressed = {"Giriş yap"}
    return timed("giriş → ilk çizim (Terminal)")

def wait_sync(timeout=10):
    db = radar.get_db(); db.sync_done.wait(timeout); return db

# ------------------------------------------------------------------ 1) SOĞUK AÇILIŞ (sunucu yeni uyandı)
print("== 1) soğuk açılış: giriş → Terminal")
setup()
t_login = time.time()
dt = login()
ck(f"giriş sonrası ilk çizim GitHub'ı beklemez ({dt:.2f} sn < {BUDGET_PAINT})", dt < BUDGET_PAINT, dt)
ck("ilk çizimde 'yükleniyor' görünür (boş ekran değil)", "yükleniyor" in md().lower())
wait_sync(); H.run()
t_full = time.time() - t_login
ck("senkron bitince 'Şimdi' görünümü dolu (≥8 satır)", md().count("class='frow") >= 8, md().count("class='frow"))
set_ss("fids_view", "Tüm gün"); H.run()
ck("'Tüm gün' görünümü tam liste (≥40)", md().count("class='frow") >= 40, md().count("class='frow"))
set_ss("fids_view", "Şimdi")
ck("GitHub verisi taze: AeroDataBox çağrılmadı (kota harcanmadı)", Net.calls["adb"] == 0, Net.calls["adb"])
gh_total = 3 * LAT["github"] * SCALE
ck(f"girişten dolu tabloya toplam süre ≈ GitHub süresi ({t_full:.2f} sn ≤ {gh_total + 0.8:.2f})", t_full <= gh_total + 0.8, t_full)
dt = timed("Terminal tekrar çizim (dolu)")
ck(f"Terminal tekrar çizimi hızlı ({dt:.2f} sn)", dt < BUDGET_PAINT_STEADY, dt)

# ------------------------------------------------------------------ 2) TERMINAL AÇIKKEN ARKA PLAN ISINMASI → RADAR
print("== 2) Terminal'den Radar'a geçiş")
radar.join_background(timeout=20)
n_calls = dict(Net.calls)
set_ss("page", P[0]); dt = timed("Terminal → Radar (ısınmış)")
ck(f"ısınmış Radar çizimi hızlı ({dt:.2f} sn)", dt < BUDGET_PAINT_STEADY, dt)
ck("haritada 15 uçak var", len(SF.calls[-1][0].markers()) >= 15, len(SF.calls[-1][0].markers()))
ck("geçişte yeni ağ çağrısı yok", all(Net.calls[k] == n_calls[k] for k in ("opensky", "adsblol", "adsbdb")), (n_calls, dict(Net.calls)))
for i in range(4): timed("Radar tekrar çizim")
ck("sürekli çizimde en yavaş çizim bütçede", max(t for l, t in TIMES if l == "Radar tekrar çizim") < BUDGET_PAINT_STEADY)

# ------------------------------------------------------------------ 3) RADAR'A HEMEN GEÇİŞ (ısınma bitmeden)
print("== 3) girişin hemen ardından Radar (soğuk, OpenSky erişilemez)")
setup()
login(); wait_sync()
radar._TCACHE.clear(); radar._WARM.update(t=0.0, busy=False); radar._BG["logo"].clear(); radar._WX.update(val=None, t=0.0, busy=False)
radar.get_store().clear()
set_ss("page", P[0]); t0 = time.time(); dt = timed("Radar soğuk ilk çizim")
ck(f"soğuk Radar ilk çizimi beklemez ({dt:.2f} sn)", dt < BUDGET_PAINT, dt)
ck("'yükleniyor' bilgisi görünür", "yükleniyor" in md().lower())
ck("kısa yenileme (≤3 sn) ile veriyi hemen çeker", fake.refresh is not None and fake.refresh <= 3000, fake.refresh)
radar.join_background(timeout=20); dt = timed("Radar veri geldikten sonra")
t_planes = time.time() - t0
ck("veri gelince 15 uçak çizilir", len(SF.calls[-1][0].markers()) >= 15, len(SF.calls[-1][0].markers()))
ck(f"veri gelince çizim hızlı ({dt:.2f} sn): rota/uçak önceden ısındı", dt < BUDGET_PAINT_STEADY, dt)
bound = (OPENSKY_TIMEOUT * SCALE + LAT["adsblol"] * SCALE + 3 * LAT["adsbdb"] * SCALE + 0.8)
ck(f"soğuk Radar'da uçakların görünmesi ≤ {bound:.1f} sn ({t_planes:.2f})", t_planes <= bound, t_planes)

# ------------------------------------------------------------------ 4) YAVAŞ YAN SERVİSLER ÇİZİMİ BEKLETMEZ
print("== 4) yavaş hava durumu / fotoğraf servisi")
setup()
login(); wait_sync()
radar._TCACHE.clear(); radar._WX.update(val=None, t=0.0, busy=False); radar.get_store().clear()
Net.lat["meteo"] = 3.0 * SCALE; Net.lat["photo"] = 3.0 * SCALE
set_ss("page", P[0]); timed(); radar.join_background(timeout=20)
t = time.time(); H.run(); dt = time.time() - t
ck(f"hava durumu 3 sn gecikmeli iken çizim beklemez ({dt:.2f} sn)", dt < BUDGET_PAINT, dt)
ck("fotoğraf servisi yavaşken çizim beklemez", dt < BUDGET_PAINT, dt)

# ------------------------------------------------------------------ 5) KARARLI DURUM: AĞ ÇAĞRISI YOK
print("== 5) kararlı durumda gereksiz ağ çağrısı yok")
setup(); login(); wait_sync(); H.run(); radar.join_background(timeout=20)
n = dict(Net.calls)
for _ in range(5): H.run()
ck("Terminal tekrar çizimlerinde ağ çağrısı yok", dict(Net.calls) == n, (n, dict(Net.calls)))

# ------------------------------------------------------------------ 6) GITHUB ÇÖKÜK: UYGULAMA YİNE AÇILIR
print("== 6) GitHub ulaşılamaz")
setup(); Net.gh.repo_ok = False
dt = login()
ck(f"GitHub hatalıyken giriş yine hızlı ({dt:.2f} sn)", dt < BUDGET_PAINT, dt)
wait_sync(); H.run()
ck("veri yoksa tarife API'den çekilir (yedek yol)", Net.calls["adb"] >= 1 or md().count("class='frow") >= 8)
ck("GitHub hatasına rağmen güvenli: ezme yok", not any(m == "PUT" for m, _ in Net.gh.calls))

print("\n--- Süre özeti (sn, ölçek %.2f) ---" % SCALE)
for l, t in TIMES: print(f"  {t:6.2f}  {l}")
print("\nBAŞARISIZ:", FAILS if FAILS else "yok"); sys.exit(1 if FAILS else 0)
