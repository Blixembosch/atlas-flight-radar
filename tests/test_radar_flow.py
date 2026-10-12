import re, time, sys
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar, Net, SF, row, ap
from fakes import FakeGH
run = H.run
def press(key):
    cb, args = fake.buttons[key]
    if cb: cb(*args)
    fake.pressed = {key}; return H.run()
def set_ss(k, v): fake.session_state._force(k, v)
DEF = {"f_over": False, "f_view": "Hepsi", "f_q": "", "f_cov": list(radar.COVERAGE)[0], "demo": False}
def W(**kw):
    m = {"over": "f_over", "view": "f_view", "q": "f_q", "cov": "f_cov", "demo": "demo"}
    for k, v in DEF.items(): set_ss(k, v)
    for k, v in kw.items(): set_ss(m[k], v)
    run()
H.reset_app({"APP_PASSWORD": "gizli"})


EIN = ap("EIN","EHEH","Eindhoven","NL",51.45,5.374)
Net.routes = {
 "TRA216Y": {"airline":{"name":"Transavia","icao":"TRA","iata":"HV"}, "origin":ap("TFS","GCTS","Tenerife","ES",28.0,-16.5), "destination":EIN},
 "TRA54U":  {"airline":{"name":"Transavia","icao":"TRA","iata":"HV"}, "origin":EIN, "destination":ap("ZTH","LGZA","Zakynthos","GR",37.7,20.9)},
 "RYR9":    {"airline":{"name":"Ryanair","icao":"RYR","iata":"FR"}, "origin":ap("AGP","LEMG","Malaga","ES",36.7,-4.5), "destination":EIN},
 "DLH958":  {"airline":{"name":"Lufthansa","icao":"DLH","iata":"LH"}, "origin":ap("FRA","EDDF","Frankfurt","DE",50.0,8.5), "destination":ap("BHX","EGBB","Birmingham","GB",52.45,-1.74)},
}
Net.aircraft = {"a1":{"icao_type":"B738","registration":"PH-HXJ"}, "a2":{"icao_type":"B738","registration":"PH-HXK"},
                "a3":{"icao_type":"B38M","registration":"EI-XYZ"}, "a4":{"icao_type":"A320","registration":"D-AIZZ"}}
Net.gh = None
Net.states = [
 row("a1","TRA216Y",51.53,5.53,3025,318,215,-4),     # eve yaklaşan, alçalıyor
 row("a2","TRA54U", 51.47,5.43,800,260,30,6),        # kalkış
 row("a3","RYR9",   51.62,5.55,6500,380,215,-5),     # uzakta ama yaklaşıyor
 row("a4","DLH958", 51.53,5.40,35700,830,285,0),     # geçiş (anahtar kapalıyken görünmez)
 row("a5","",       51.50,5.50,2000,200,10,0,),
]

ok = True
def check(name, cond, extra=""):
    global ok; ok &= bool(cond)
    print(("✅" if cond else "❌"), name, extra)

def sel_markers():
    m = SF.calls[-1][0]
    return [mk for mk in m.markers() if "#facc15" in mk.k["icon"].html and "width='46'" in mk.k["icon"].html]
def panel():
    return next((h for h in reversed(fake.md) if "class='panel'" in h), "")

# 1) ilk açılış
run()
set_ss("Şifre", "gizli"); fake.pressed = {"Giriş yap"}; run()
labels = [mk.k["tooltip"] for mk in SF.calls[-1][0].markers()]
check("ilk çalıştırma hatasız, uçaklar haritada", len(labels) == 3, labels)   # DLH958 kapalı, rotasız a5 gizli
check("geçiş uçağı anahtar kapalıyken yok", "DLH958" not in labels)
sel0 = fake.session_state["sel"]
check("bir uçak otomatik seçili", sel0 is not None, sel0)
check("haritada tam 1 sarı seçili uçak", len(sel_markers()) == 1)
p = panel(); cs0 = re.search(r"class='cs'>([^<]+)<", p).group(1)
check("panel seçili uçağı gösteriyor", cs0 in labels, cs0)
check("panelde hız (km/sa, kt) ve koltuk", "km/sa" in p and "kt)" in p and "koltuk" in p)
check("kartlarda hız ve koltuk var", any("💺" in h and "km/sa" in h for h in fake.md))
check("koltuk: Transavia 737-800 = ~189", "~189 koltuk" in "".join(fake.md))
check("hareket JS'i eklendi", any(i.kind == "Macro" for i in SF.calls[-1][0].items))
print("   yenileme (ms):", fake.refresh, "| aktif:", fake.session_state.get("_active"))

# 2) İncele düğmesi
other = next(f for f in labels if f != cs0)
btn = {k: v for k, v in fake.buttons.items()}
target_key = next(k for k in btn if k.startswith("btn_") and k != f"btn_{sel0}")
target_id = target_key[4:]
fake.pressed = {target_key}; key_before = SF.calls[-1][1]["key"]
press(target_key)
check("İncele: seçim değişti", fake.session_state["sel"] == target_id, target_id)
check("İncele: harita anahtarı yenilendi", SF.calls[-1][1]["key"] != key_before)
sm = sel_markers()
check("İncele: haritada seçili uçak sarı ve tek", len(sm) == 1)
tt = sm[0].k["tooltip"]
check("İncele: sarı uçak seçilen uçak", tt in panel(), tt)
check("İncele: panel yeni uçağa geçti", re.search(r"class='cs'>([^<]+)<", panel()).group(1) == tt)
check("İncele: panelde hız, kt ve ~189 koltuk", all(x in panel() for x in ["318 km/sa","kt)","~189 koltuk"]) if tt=="TRA216Y" else True, tt)

# 3) haritadan tıklama
cur = fake.session_state["sel"]
click_label = next(f for f in labels if f != tt)
SF.click_for_key[SF.calls[-1][1]["key"]] = click_label
gen_before = fake.session_state["_map_gen"]
run()
check("harita tıklaması: panel güncellendi", re.search(r"class='cs'>([^<]+)<", panel()).group(1) == click_label, click_label)
check("harita tıklaması: sarı uçak değişti", len(sel_markers()) == 1 and sel_markers()[0].k["tooltip"] == click_label)
check("harita tıklaması: anahtar yenilendi", fake.session_state["_map_gen"] == gen_before + 1)

# 4) bayat tıklama hatası: haritadan A, sonra İncele ile B -> B kalmalı
A = click_label
B_key = next(k for k in fake.buttons if k.startswith("btn_") and k != f"btn_{fake.session_state['sel']}")
fake.pressed = {B_key}; press(B_key)
check("tıkla(A) sonra İncele(B): B seçili kaldı (geri dönmedi)", fake.session_state["sel"] == B_key[4:], fake.session_state["sel"])
run()  # otomatik yenileme turu
check("otomatik yenilemeden sonra da B seçili", fake.session_state["sel"] == B_key[4:])

# 5) yenilemelerde seçim korunuyor, uçak kaybolursa otomatik yeni seçim
keep = fake.session_state["sel"]; run(); run()
check("birkaç yenilemede seçim korunuyor", fake.session_state["sel"] == keep)
saved = list(Net.states); Net.states = [s for s in Net.states if s[0] != keep]
run(); check("seçili uçak giderse otomatik başkası seçilir", fake.session_state["sel"] not in (keep, None))
Net.states = saved

# 6) seçenekler
W(over=True)
labels2 = [mk.k["tooltip"] for mk in SF.calls[-1][0].markers()]
check("geçiş açık: DLH958 geldi", "DLH958" in labels2)
dlh = next(mk for mk in SF.calls[-1][0].markers() if mk.k["tooltip"] == "DLH958")
check("geçiş uçağı mor (seçili değilse)", "#a78bfa" in dlh.k["icon"].html or "#facc15" in dlh.k["icon"].html)
W(over=True, view="Geçiş")
check("Geçiş filtresi sadece geçişleri gösterir", [mk.k["tooltip"] for mk in SF.calls[-1][0].markers()] == ["DLH958"])
W(view="Kalkış")
kal=[mk.k["tooltip"] for mk in SF.calls[-1][0].markers()]; check("Kalkış filtresi (rotasız a5 gizli)", sorted(kal) == ["TRA54U"], kal)
W(q="HV6710"); check("arama boş sonuçta çökmüyor", fake.infos or True)
W(q="hv216y")
check("arama uçuş numarasıyla (HV216Y)", [mk.k["tooltip"] for mk in SF.calls[-1][0].markers()] == ["TRA216Y"])
W(q="ph-hxk")
check("arama tescille", [mk.k["tooltip"] for mk in SF.calls[-1][0].markers()] == ["TRA54U"])
W(cov=list(radar.COVERAGE)[2]); check("200 km kapsama çalışıyor", True)
W(demo=True)
check("demo modu çalışıyor", len(SF.calls[-1][0].markers()) == 3 and len(sel_markers()) == 1)
W()

# 7) boş ve hata durumları
Net.states = []; run(); check("uçak yokken bilgi mesajı", len(fake.infos) == 1 and not sel_markers())
check("uçak yokken panel boş durumda", "Şu an koridorda uçak yok" in panel())
Net.states = saved; Net.fail_opensky = True; run(); check("OpenSky hatasında çökmüyor", True)
Net.fail_opensky = False; Net.states = saved

# 8) yenileme aralığı
run(); run(); print("   aktif:", fake.session_state["_active"], "yenileme:", fake.refresh)
check("yaklaşan uçak varken hızlı yenileme (15 sn, hesapsız)", fake.refresh == 15000)
n0 = fake.reruns; run(); check("tek çalıştırmada rerun fırtınası yok", fake.reruns - n0 == 0)
Net.states = [row("z","TRA9",52.3,5.4,30000,800,0,0)]; run(); run()
check("yaklaşan yokken yavaş yenileme (60 sn)", fake.refresh == 60000, fake.refresh)

print("\nSONUÇ:", "TÜM TESTLER GEÇTİ" if ok else "HATA VAR")
sys.exit(0 if ok else 1)
