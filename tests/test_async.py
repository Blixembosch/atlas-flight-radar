import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar, Net, adb_payload
import radar_fids as F
FAILS = []
def ck(n, c, i=""):
    print(("OK   " if c else "FAIL ") + n + (f"   [{i}]" if (i and not c) else ""))
    if not c: FAILS.append(n)
def set_ss(k, v): fake.session_state._force(k, v)
def md(): return "\n".join(fake.md)
def timed():
    t = time.time(); H.run(); return time.time() - t

P = radar.PAGES
H.reset_app({"APP_PASSWORD": "p", "AERODATABOX_KEY": "k"})
H.run(); set_ss("Şifre", "p"); fake.pressed = {"Giriş yap"}; H.run()
Net.adb_json = adb_payload(); Net.adb_delay = 1.2; Net.logo_delay = 1.2

# 1) hiç veri yok: ilk seferde bekler (boş ekran göstermemek için)
set_ss("page", P[1]); dt = timed()
ck("ilk açılışta tarife beklenir ve dolu gelir", Net.calls["adb"] == 1 and md().count("class='frow") >= 40, (Net.calls["adb"], dt))
ck("logo indirmesi sayfayı BEKLETMEZ (1.2 sn gecikmeli logolar)", dt < 2.2, dt)   # tarife ~1.2 + logo 0
ck("logolar bekliyorken kısa yenileme (5 sn)", fake.refresh == 5000, fake.refresh)
ck("logosuzken metin rozeti", "alogo txt" in md())
radar.join_background()
H.run()
ck("logolar gelince CSS sınıfı", ".alogo.k-TRA" in md() and ".alogo.k-RYR" in md())
ck("logolar tamamlanınca yenileme 60 sn", fake.refresh == 60000, fake.refresh)
ck("sayfa süresi altbilgide", "sayfa " in md() and " sn" in md())

# 2) veri var ama yenileme zamanı geldi: sayfa API'yi BEKLEMEZ
db = radar.get_db()
db.meta_set(fids_last_fetch="2000-01-01T00:00")
n = Net.calls["adb"]
dt = timed()
ck("yenileme arka planda: sayfa hızlı (<0.6 sn)", dt < 0.6, dt)
ck("eldeki veri hemen gösterildi", md().count("class='frow") >= 40)
radar.join_background()
ck("arka plan güncellemesi API'yi çağırdı", Net.calls["adb"] > n, (n, Net.calls["adb"]))
n2 = Net.calls["adb"]
for _ in range(3): H.run()
ck("sonraki çizimlerde tekrar çağrı yok (taze)", Net.calls["adb"] == n2)

# 3) logo hatası: sayfa yine hızlı, sonsuz 5 sn döngüsü yok
H.reset_app({"APP_PASSWORD": "p", "AERODATABOX_KEY": "k"})
H.run(); set_ss("Şifre", "p"); fake.pressed = {"Giriş yap"}; H.run()
Net.adb_json = adb_payload()
import requests as rq
orig = rq.get
def broken(url, **kw):
    if "avs.io" in url or "gstatic" in url or "kiwi" in url: raise Exception("logo sunucusu yok")
    return orig(url, **kw)
rq.get = broken
set_ss("page", P[1]); H.run(); radar.join_background(); H.run()
ck("logo sunucusu çökükken sayfa çalışır", md().count("class='frow") >= 40 and "alogo txt" in md())
ck("başarısız logo önbelleğe alınır: 5 sn döngüsü yok", fake.refresh == 60000, fake.refresh)
rq.get = orig

print("\nBAŞARISIZ:", FAILS if FAILS else "yok")
sys.exit(1 if FAILS else 0)
