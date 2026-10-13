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
P = radar.PAGES
def start(secrets):
    H.reset_app(secrets); Net.gh = None
    H.run(); set_ss("Şifre", "p"); fake.pressed = {"Giriş yap"}; H.run()
S = {"APP_PASSWORD": "p", "AERODATABOX_KEY": "secret-key-xyz"}

# 1) düz alan biçimi (scheduledTimeLocal) ekranda satır üretir
def flatify(js):
    for k in ("departures", "arrivals"):
        for f in js[k]:
            mv = f["movement"]
            mv["scheduledTimeLocal"] = mv.pop("scheduledTime")["local"]
            if "revisedTime" in mv: mv["revisedTimeLocal"] = mv.pop("revisedTime")["local"]
    return js
start(S); Net.adb_json = flatify(adb_payload()); set_ss("page", P[1]); set_ss("fids_view", "Tüm gün"); H.run()
ck("düz biçimli yanıttan 20+20 satır", md().count("class='frow") == 40, md().count("class='frow"))

# 2) boş 200: sebep ekranda, tanı görünür, anahtar yok
start(S); Net.adb_json = {"departures": [], "arrivals": []}; set_ss("page", P[1]); set_ss("fids_view", "Tüm gün"); H.run()
m = md()
ck("boş yanıt: açıklama ekranda", "uçuş döndürmedi" in m)
ck("boş yanıt: yalnızca 1 çağrı", Net.calls["adb"] == 1, Net.calls["adb"])
ck("boş yanıt: 'Eski veri' değil 'Veri yok'", "Veri yok" in m and "Eski veri" not in m)
ck("tanı kutusunda ham sayılar", "ham: 0 varış / 0 kalkış" in m)
ck("tanıda anahtar yok", "secret-key-xyz" not in m)

# 3) düğme: veri gelince doldurur (2 dk koruma sonrası)
Net.adb_json = adb_payload()
ck("yenile düğmesi görünür", "fids_force" in fake.buttons)
db = radar.get_db(); db.meta_set(fids_last_fetch="2000-01-01T00:00")
fake.pressed = {"fids_force"}; H.run()
ck("düğme: tarife çekildi ve satırlar geldi", Net.calls["adb"] >= 2 and md().count("class='frow") >= 40)
fake.pressed = {"fids_force"}; n = Net.calls["adb"]; H.run()
ck("düğme: art arda basılınca kota harcanmaz", Net.calls["adb"] == n)

# 4) demo / anahtarsız modda düğme yok
set_ss("demo", True); H.run()
ck("demo modunda yenile düğmesi yok", "fids_force" not in fake.buttons)
print("\nBAŞARISIZ:", FAILS if FAILS else "yok")
sys.exit(1 if FAILS else 0)
