"""
Atlas'ın Uçak Gözlem Kulesi  (v0.3.11)
  * Radar        : harita + detay paneli (rotası bilinmeyen uçaklar gizlenir)
  * Terminal     : Eindhoven Havalimanı varış / kalkış bilgi ekranı (AeroDataBox)
  * Gözlem Defteri: bahçeden görülen uçaklar (SQLite, GitHub `data` dalında yedeklenir)
  * Açılışta şifre (APP_PASSWORD)

Kurulum:
    pip install -r requirements.txt
Çalıştırma:
    streamlit run Radar.py

Ayarlar .streamlit/secrets.toml içindedir (örnek: secrets.toml.example).
"""

import base64
import html
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import streamlit as st

import radar_auth
import radar_db
import radar_fids as fids

try:
  import folium
  from streamlit_folium import st_folium
except ImportError:  # main() içinde kullanıcıya hata gösterilir
  folium = None
  st_folium = None
  MacroElement = None
else:
  from branca.element import MacroElement, Template

try:
  from streamlit_autorefresh import st_autorefresh
except ImportError:
  st_autorefresh = None

# =============================================================================
# AYARLAR  (burayı kendi ihtiyacına göre değiştirebilirsin)
# =============================================================================
TZ = ZoneInfo("Europe/Amsterdam")

HOME_LAT, HOME_LON = 51.4951, 5.4779  # Panorama (5629 TT) civarı; ekranda adres yazmaz.
# Depo herkese açıksa HOME_LAT / HOME_LON değerlerini secrets içine yazıp buradakini yaklaşık bırakabilirsin.
AIRPORT_LAT, AIRPORT_LON = 51.4501, 5.3743  # Eindhoven Havalimanı
AIRPORT_ICAO = "EHEH"

# OpenSky sorgu kutusu (havalimanı + kuzey koridoru + ev çevresi)
NEAR_KM = 50  # havalimanına bu kadar yakın alçak uçaklar her zaman gösterilir
OVERFLIGHT_KM = 30  # "Üstümüzden geçenler": evden bu kadar yakın yüksek uçaklar
INBOUND_MAX_ALT_FT = 25000  # uzaktan gelen (EIN'e alçalan) uçaklar için irtifa sınırı
# Kapsama seçenekleri: etiket -> (tarama yarıçapı km, haritanın gösterdiği yarıçap km)
# Not: OpenSky'de 25 derece-kareden küçük sorgu 1 kredi harcar; 200 km hâlâ bunun altında.
COVERAGE = {
    "📡 Yakın · 50 km": (50, 40),
    "📡 Geniş · 100 km": (100, 85),
    "📡 Çok geniş · 200 km": (200, 170),
}

# Veri yenileme: yaklaşan uçak varken sık, yokken seyrek (OpenSky kotasını korur).
# Hesap bilgisi (secrets.toml) varsa günlük kota 10 kat fazla olduğu için daha sık yenilenir.
REFRESH_ACTIVE = {"auth": 8, "anon": 15}
REFRESH_IDLE = {"auth": 30, "anon": 60}
FETCH_TTL = 8  # aynı veriyi bu süre içinde tekrar istemez
MOTION_TICK_MS = 500  # haritadaki uçakların kayma sıklığı (internetsiz, sadece ekranda)
MOTION_MAX_AGE_S = 90  # veri bundan eskiyse uçak kaymayı bırakır
VISIBLE_KM = 4.0  # "bahçeden görünür" yarıçapı
VISIBLE_ALT_FT = 5000  # bu irtifanın altı "görünür" sayılır
MAX_SHOW_ALT_FT = 10000  # bunun üstündeki uçaklar (transit) gösterilmez
MAP_ZOOM = 11
MAP_HEIGHT = 640
CFG = {"visible_km": VISIBLE_KM, "visible_alt": VISIBLE_ALT_FT, "overflight_km": OVERFLIGHT_KM}  # ⚙️ menüsünden değişir

# Kuzey koridoru şeridi (yaklaşık; pist 03/21 ekseni). Gözlemine göre ayarla.
CORRIDOR_ON = True
CORRIDOR_HEADING = 30  # derece
CORRIDOR_LEN_KM = 14
CORRIDOR_HALF_WIDTH_KM = 1.5

LOGO_DIR = Path(__file__).parent / "assets" / "logos"
ENRICH_WORKERS = 8  # rota/tür/logo sorguları paralel yapılır
RUNWAY_AXIS = 30  # pist 03/21 ekseni (derece)
RUNWAY_NEAR_KM = 10  # pist tespiti için havalimanına bu kadar yakın uçaklara bakılır
LOGO_URLS = [  # sırayla denenir; ilk çalışan sunucu tarafında indirilip gömülür
    "https://pics.avs.io/240/120/{iata}.png",
    "https://www.gstatic.com/flights/airline_logos/70px/{iata}.png",
    "https://images.kiwi.com/airlines/64/{iata}.png",
]

OPENSKY_URL = "https://opensky-network.org/api/states/all"
OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/"
    "protocol/openid-connect/token"
)
ADSBDB = "https://api.adsbdb.com/v0"
ADSBLOL_URL = "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}"  # ücretsiz, anahtarsız yedek kaynak
OPENSKY_TIMEOUT = 5
OPENSKY_DOWN_S = 600  # OpenSky ulaşılamazsa bu süre boyunca yedek kaynak önce denenir
_SRC = {"os_down_until": 0.0, "last_source": ""}  # sunucu geneli kaynak durumu

# =============================================================================
# HAVAYOLU VE UÇAK BİLGİLERİ
# =============================================================================
# Çağrı kodunun ilk 3 harfi -> ortak anahtar
ALIASES = {
    "TVF": "TRA", "WMT": "WZZ", "WUK": "WZZ", "TFL": "TUI", "TOM": "TUI",
    "TUY": "TUI", "RUK": "RYR", "KLC": "KLM", "EZS": "EZY", "EJU": "EZY",
}
# anahtar: (ad, arka plan, yazı rengi, IATA kodu)  -> logo bulunamazsa bu rozet çıkar
AIRLINES = {
    "TRA": ("Transavia", "#00a651", "#ffffff", "HV"),
    "RYR": ("Ryanair", "#073590", "#f1c933", "FR"),
    "WZZ": ("Wizz Air", "#c6007e", "#ffffff", "W6"),
    "TUI": ("TUI", "#d40e14", "#ffffff", "OR"),
    "KLM": ("KLM", "#00a1de", "#ffffff", "KL"),
    "EZY": ("easyJet", "#ff6600", "#ffffff", "U2"),
    "VLG": ("Vueling", "#ffcc00", "#222222", "VY"),
    "PGT": ("Pegasus", "#f5a100", "#222222", "PC"),
    "THY": ("Turkish Airlines", "#c70a0c", "#ffffff", "TK"),
    "SXS": ("SunExpress", "#ffcc00", "#222222", "XQ"),
    "DLH": ("Lufthansa", "#05164d", "#ffb900", "LH"),
}

# ICAO tür kodu -> (ad, tipik koltuk sayısı, çocuklara göre kısa bilgi)
AIRCRAFT_TYPES = {
    "B737": ("Boeing 737-700", 149, "737'nin biraz kısa kuzeni."),
    "B738": ("Boeing 737-800", 189, "Dünyanın en popüler kısa-orta menzilli yolcu uçaklarından."),
    "B739": ("Boeing 737-900", 190, "737-800'ün biraz uzun hali."),
    "B38M": ("Boeing 737 MAX 8", 189, "737'nin yeni nesil, daha sessiz modeli."),
    "B39M": ("Boeing 737 MAX 9", 220, "737 MAX ailesinin uzun üyesi."),
    "A318": ("Airbus A318", 107, "A320 ailesinin en küçüğü, 'Baby Bus' diye bilinir."),
    "A319": ("Airbus A319", 140, "A320 ailesinin kısa üyelerinden."),
    "A320": ("Airbus A320-200", 180, "Geniş kabinli popüler dar gövde uçak."),
    "A20N": ("Airbus A320neo", 186, "A320'nin yeni, yakıt tasarruflu modeli."),
    "A321": ("Airbus A321", 220, "A320'nin uzatılmış gövdeli hali."),
    "A21N": ("Airbus A321neo", 239, "Yeni nesil, uzun menzilli A321."),
    "E170": ("Embraer 170", 76, "Brezilya yapımı küçük yolcu uçağı."),
    "E175": ("Embraer 175", 78, "Brezilya yapımı bölgesel yolcu uçağı."),
    "E190": ("Embraer 190", 100, "Brezilya yapımı, küçük bölgesel yolcu uçağı."),
    "E195": ("Embraer 195", 120, "Embraer 190'ın uzun versiyonu."),
    "AT72": ("ATR 72", 70, "İki pervaneli, kısa mesafe uçağı."),
    "DH8D": ("Dash 8 Q400", 78, "İki pervaneli, hızlı bölgesel uçak."),
    "CRJ9": ("Bombardier CRJ-900", 90, "Kuyruğunda motorları olan bölgesel jet."),
    "B763": ("Boeing 767-300", 220, "Okyanus aşan geniş gövdeli uçak."),
    "B772": ("Boeing 777-200", 300, "İki motorlu dev yolcu uçağı."),
    "B77W": ("Boeing 777-300ER", 350, "Dünyanın en büyük iki motorlu uçaklarından."),
    "B788": ("Boeing 787-8 Dreamliner", 240, "Gövdesi hafif malzemeden, sessiz bir uçak."),
    "B789": ("Boeing 787-9 Dreamliner", 290, "Dreamliner'ın uzun hali."),
    "A332": ("Airbus A330-200", 250, "Uzun mesafe geniş gövdeli uçak."),
    "A333": ("Airbus A330-300", 290, "A330'un uzun versiyonu."),
    "A359": ("Airbus A350-900", 300, "Yeni nesil, çok sessiz geniş gövdeli uçak."),
    "A388": ("Airbus A380", 520, "Dünyanın en büyük yolcu uçağı, iki katlı!"),
    "B744": ("Boeing 747-400", 400, "Üst katıyla ünlü 'Jumbo Jet'."),
}

# Havayoluna özel koltuk sayısı (tipik düzen, yaklaşık): (havayolu, tip) -> koltuk
SEATS_BY_AIRLINE = {
    ("TRA", "B738"): 189, ("TRA", "B737"): 149,
    ("RYR", "B738"): 189, ("RYR", "B38M"): 197,
    ("WZZ", "A320"): 180, ("WZZ", "A20N"): 186, ("WZZ", "A321"): 230, ("WZZ", "A21N"): 239,
    ("EZY", "A319"): 156, ("EZY", "A320"): 180, ("EZY", "A20N"): 186,
}


def seat_text(airline_key, type_code, default=None):
  """'~189 koltuk' gibi metin; bilinmiyorsa 'Bilinmiyor'."""
  n = SEATS_BY_AIRLINE.get((airline_key, type_code)) or default
  return f"~{n} koltuk" if n else "Bilinmiyor"

WMO = {  # Open-Meteo hava kodu -> (emoji, açıklama)
    0: ("☀️", "Açık"), 1: ("🌤️", "Az bulutlu"), 2: ("⛅", "Parçalı bulutlu"),
    3: ("☁️", "Bulutlu"), 45: ("🌫️", "Sisli"), 48: ("🌫️", "Sisli"),
    51: ("🌦️", "Çiseleme"), 53: ("🌦️", "Çiseleme"), 55: ("🌦️", "Çiseleme"),
    61: ("🌧️", "Yağmurlu"), 63: ("🌧️", "Yağmurlu"), 65: ("🌧️", "Kuvvetli yağmur"),
    71: ("🌨️", "Karlı"), 73: ("🌨️", "Karlı"), 75: ("❄️", "Yoğun kar"),
    80: ("🌧️", "Sağanak"), 81: ("🌧️", "Sağanak"), 82: ("🌧️", "Kuvvetli sağanak"),
    95: ("⛈️", "Gök gürültülü"), 96: ("⛈️", "Dolu"), 99: ("⛈️", "Dolu"),
}

PLANE_PATH = (
    "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19"
    "l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"
)

# =============================================================================
# CSS
# =============================================================================
CSS = """
<style>
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
#MainMenu, footer{visibility:hidden;}
.stApp{background:#0b1020;color:#e5e9f5;}
.block-container{padding:.9rem 1.3rem 1.5rem!important;max-width:1600px;}
:root{--card:#121a33;--line:#223056;--muted:#8b97b8;--arr:#38bdf8;--dep:#fb923c;--ok:#22c55e;}

/* Üst bar */
.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;
  background:linear-gradient(120deg,#1d2a6b 0%,#3b2a8c 55%,#7a2a6a 100%);
  border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:12px 20px;}
.brand{font-size:1.35rem;font-weight:800;letter-spacing:-.3px;color:#fff;}
.brand small{display:block;font-size:.72rem;font-weight:500;opacity:.8;letter-spacing:0;}
.chips{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}
.chip{background:rgba(10,14,32,.45);border:1px solid rgba(255,255,255,.14);border-radius:12px;
  padding:6px 12px;font-size:.82rem;font-weight:600;color:#fff;white-space:nowrap;}
.chip b{color:#fff;}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:middle;}
.dot.live{background:#ef4444;box-shadow:0 0 0 0 rgba(239,68,68,.7);animation:pulse 1.6s infinite;}
.dot.demo{background:#f59e0b;} .dot.err{background:#94a3b8;}
@keyframes pulse{70%{box-shadow:0 0 0 9px rgba(239,68,68,0);}100%{box-shadow:0 0 0 0 rgba(239,68,68,0);}}

/* Tek satırlık bilgi şeritleri (sıradaki uçak, aktif pist) */
.strip{display:flex;align-items:center;gap:10px;margin:10px 0 12px;padding:6px 14px;min-height:38px;
  background:var(--card);border:1px solid var(--line);border-radius:12px;font-size:.86rem;
  white-space:nowrap;overflow:hidden;color:#cdd5ea;}
.strip .ic{font-size:1.05rem;flex:none;}
.strip .tx{overflow:hidden;text-overflow:ellipsis;min-width:0;}
.strip .sub{color:var(--muted);font-size:.76rem;margin-left:8px;}
.strip b{color:#fff;}
.strip.hot{border-color:rgba(56,189,248,.5);background:linear-gradient(90deg,rgba(56,189,248,.14),rgba(124,77,255,.08));}

/* Logo */
.logo{display:inline-flex;align-items:center;justify-content:center;border-radius:12px;font-weight:900;
  letter-spacing:.3px;box-shadow:0 2px 8px rgba(0,0,0,.35);overflow:hidden;}
.logo-xl{height:56px;min-width:140px;padding:0 18px;font-size:1.35rem;}
.logo-md{height:46px;min-width:120px;padding:0 10px;font-size:.92rem;}
.logo.logo-img{background:#eef0f4;}
.logo-img img{max-height:100%;max-width:100%;object-fit:contain;padding:6px 4px;}

/* Sağ detay paneli */
.panel{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:14px 16px;min-height:690px;box-sizing:border-box;}
.panel .head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px;}
.panel .cs{font-size:1.7rem;font-weight:800;color:#fff;line-height:1.05;}
.panel .al{color:var(--muted);font-size:.9rem;margin-top:2px;}
.panel .ph{width:100%;border-radius:12px;margin:6px 0 2px;max-height:140px;object-fit:cover;}
.panel .credit{font-size:.65rem;color:#64708f;margin-bottom:4px;}
.route{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:8px 0 4px;}
.route .ap{text-align:center;min-width:0;}
.route .code{font-size:1.6rem;font-weight:800;color:#fff;}
.route .city{font-size:.8rem;color:var(--muted);}
.route .fl{font-size:1.5rem;}
.prog{position:relative;flex:1;height:4px;background:var(--line);border-radius:4px;margin:0 6px;}
.prog-fill{height:100%;background:linear-gradient(90deg,#38bdf8,#7c4dff);border-radius:4px;}
.prog-plane{position:absolute;top:-11px;transform:translateX(-50%);font-size:1.1rem;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;}
.stat{background:#0e1630;border:1px solid var(--line);border-radius:12px;padding:8px 12px;}
.stat small{display:block;color:var(--muted);font-size:.7rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;}
.stat b{font-size:1.15rem;color:#fff;}
.badge{display:inline-block;border-radius:8px;padding:4px 10px;font-size:.72rem;font-weight:800;}
.badge.arr{background:#0369a1;color:#e0f2fe;} .badge.dep{background:#c2410c;color:#ffedd5;}
.badge.trn{background:#4c1d95;color:#ddd6fe;} .badge.vis{background:#14532d;color:#86efac;} .badge.far{background:#1e293b;color:#94a3b8;}
.status2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;}
.sbox{border-radius:12px;padding:10px;text-align:center;font-weight:700;font-size:.88rem;}
.sbox.a{background:#14532d;color:#bbf7d0;} .sbox.b{background:#0e1630;border:1px solid var(--line);color:#cbd5e1;}
.fact{margin-top:8px;font-size:.85rem;color:#b7c0da;background:#0e1630;border-radius:12px;padding:10px 12px;}
.empty{text-align:center;color:var(--muted);padding:80px 10px;}
.empty .big{font-size:3rem;}

/* Kart şeridi */
.fcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin-bottom:6px;}
.fcard.sel{border-color:#38bdf8;box-shadow:0 0 0 2px rgba(56,189,248,.35);}
.fcard .r1{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;}
.fcard .cs{font-weight:800;color:#fff;font-size:1.02rem;}
.fcard .rt{margin-top:8px;font-weight:600;color:#dbe3f7;font-size:.9rem;}
.fcard .meta{margin-top:4px;font-size:.78rem;color:var(--muted);}
/* Filtre çubuğu: tek bir kart, tüm öğeler aynı yükseklikte */
.st-key-toolbar{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:10px 16px;margin:0 0 14px;}
.st-key-toolbar [data-testid="stHorizontalBlock"]{gap:14px;align-items:center;}
.st-key-toolbar [data-testid="stElementContainer"]{margin:0;}
.st-key-toolbar [data-testid="stRadio"] [role="radiogroup"]{gap:6px 16px;flex-wrap:nowrap;}
.st-key-toolbar [data-testid="stRadio"] label{white-space:nowrap;}
.st-key-toolbar [data-baseweb="input"],.st-key-toolbar [data-baseweb="select"]>div{
  min-height:42px;background:#0e1630;border:1px solid var(--line);border-radius:10px;}
.st-key-toolbar input{height:40px;}
.st-key-toolbar [data-testid="stToggle"] label,.st-key-toolbar [data-testid="stToggle"] p{white-space:nowrap;}
.st-key-toolbar [data-testid="stPopover"] button,.st-key-toolbar [data-testid="stPopoverButton"]{
  min-height:42px;width:100%;justify-content:center;}
div.stButton>button{border-radius:10px;font-weight:700;background:#1b2750;color:#e5e9f5;border:1px solid var(--line);}
div.stButton>button:hover{border-color:#38bdf8;color:#fff;}
[data-testid="stBaseButton-secondary"],[data-testid="stPopoverButton"],[data-testid="stBaseButton-secondary"] p,[data-testid="stPopoverButton"] p{background:#1b2750 !important;color:#e5e9f5 !important;border-color:var(--line) !important;}
[data-testid="stBaseButton-secondary"]:hover{border-color:#38bdf8 !important;}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;margin:8px 0 22px;padding:6px 12px;
  background:var(--card);border:1px solid var(--line);border-radius:12px;font-size:.78rem;color:#cdd5ea;}
.lg{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;}
.lgdot{width:12px;height:12px;border-radius:50%;background:#3b82f6;border:2px solid #fff;display:inline-block;}
.lgring{width:16px;height:16px;border-radius:50%;display:inline-block;box-sizing:border-box;}
.lgring.blue{border:1.5px dashed #3b82f6;background:rgba(59,130,246,.12);}
.lgring.grey{border:1.5px dotted #94a3b8;}
.foot{text-align:center;color:#5d6a8c;font-size:.72rem;margin-top:16px;}
/* ===== v0.3 ===== */
.block-container{padding-top:1.1rem!important;}
.topbar{box-shadow:0 8px 30px rgba(20,10,60,.35);}
.fcard{transition:transform .12s ease,border-color .12s ease;}
.fcard:hover{transform:translateY(-2px);border-color:#38bdf8;}
.panel{box-shadow:0 8px 28px rgba(0,0,0,.25);}

/* Gezinme çubuğu */
.st-key-nav{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:8px 12px;margin:0 0 12px;}
.st-key-nav [data-testid="stHorizontalBlock"]{align-items:center;gap:12px;}
.st-key-nav [data-testid="stElementContainer"]{margin:0;}
.st-key-nav [data-testid="stRadio"] [role="radiogroup"]{gap:8px;flex-wrap:wrap;}
.st-key-nav [data-testid="stRadio"] label{background:#0e1630;border:1px solid var(--line);border-radius:12px;
  padding:7px 18px;margin:0;cursor:pointer;transition:all .12s ease;}
.st-key-nav [data-testid="stRadio"] label>div:first-child{display:none;}
.st-key-nav [data-testid="stRadio"] label p{font-weight:700;font-size:.92rem;color:#cdd5ea;white-space:nowrap;}
.st-key-nav [data-testid="stRadio"] label:hover{border-color:#38bdf8;}
.st-key-nav [data-testid="stRadio"] label:has(input:checked){background:linear-gradient(120deg,#2b3a9a,#6a35b8);
  border-color:rgba(255,255,255,.25);}
.st-key-nav [data-testid="stRadio"] label:has(input:checked) p{color:#fff;}
.st-key-nav [data-testid="stToggle"] p{white-space:nowrap;font-weight:600;font-size:.85rem;}

/* Giriş ekranı */
.login-card{text-align:center;background:linear-gradient(160deg,#16204a,#1b1740);border:1px solid var(--line);
  border-radius:22px;padding:30px 24px 18px;margin:9vh 0 12px;box-shadow:0 18px 50px rgba(0,0,0,.4);}
.login-card .big{font-size:3.2rem;line-height:1;}
.login-card h1{font-size:1.45rem;margin:10px 0 4px;color:#fff;font-weight:800;letter-spacing:-.3px;}
.login-card p{color:var(--muted);font-size:.86rem;margin:0 0 6px;}

/* Terminal (varış / kalkış) */
.term-head{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;
  background:linear-gradient(120deg,#0f2a55 0%,#12306b 50%,#1b2a74 100%);border:1px solid rgba(255,255,255,.12);
  border-radius:18px;padding:14px 22px;margin-bottom:12px;}
.term-head .tt{font-size:1.45rem;font-weight:800;color:#fff;letter-spacing:-.3px;}
.term-head .tt span{font-size:.8rem;font-weight:700;color:#7dd3fc;margin-left:10px;letter-spacing:.08em;}
.term-head .ts{font-size:.78rem;color:#b6c4e8;margin-top:2px;}
.term-head .tr{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.clock{font-size:1.9rem;font-weight:800;color:#fff;font-variant-numeric:tabular-nums;letter-spacing:.02em;}
.livepill{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:5px 12px;font-size:.78rem;font-weight:700;
  background:rgba(10,14,32,.5);border:1px solid rgba(255,255,255,.16);color:#fff;white-space:nowrap;}
.livepill i{width:8px;height:8px;border-radius:50%;display:inline-block;background:#94a3b8;}
.livepill.ok i{background:#22c55e;box-shadow:0 0 8px #22c55e;} .livepill.old i{background:#f59e0b;}
.livepill.demo i{background:#f59e0b;} .livepill.none i{background:#ef4444;}
.tpanel{background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 8px 28px rgba(0,0,0,.22);}
.tphead{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;
  border-bottom:1px solid var(--line);}
.tphead.arr{background:linear-gradient(90deg,rgba(56,189,248,.20),rgba(56,189,248,0));}
.tphead.dep{background:linear-gradient(90deg,rgba(251,146,60,.22),rgba(251,146,60,0));}
.tphead .nm{font-size:1.12rem;font-weight:800;color:#fff;} .tphead .nm small{color:var(--muted);font-weight:600;font-size:.76rem;margin-left:8px;}
.tphead .ct{font-size:.76rem;color:var(--muted);font-weight:600;}
.fgrid{display:grid;align-items:center;gap:10px;padding:0 16px;}
.fgrid.arr{grid-template-columns:70px minmax(0,1.5fr) minmax(0,1.5fr) 118px 70px;}
.fgrid.dep{grid-template-columns:70px minmax(0,1.5fr) minmax(0,1.5fr) 46px 118px 70px;}
.fcols{padding-top:8px;padding-bottom:8px;font-size:.66rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;
  color:#6f7da3;border-bottom:1px solid var(--line);background:#0f1730;}
.frow{min-height:52px;border-bottom:1px solid rgba(34,48,86,.55);transition:background .1s ease;}
.frow:hover{background:rgba(56,189,248,.06);}
.frow.done{opacity:.5;} .frow.canc .c-fl b,.frow.canc .c-time b{text-decoration:line-through;}
.frow.next{background:linear-gradient(90deg,rgba(250,204,21,.10),rgba(250,204,21,0));box-shadow:inset 3px 0 0 #facc15;}
.c-time b{display:block;font-size:1.05rem;color:#fff;font-variant-numeric:tabular-nums;line-height:1.1;}
.c-time small{display:block;font-size:.72rem;color:#fbbf24;font-weight:700;font-variant-numeric:tabular-nums;}
.c-fl,.c-pl{display:flex;align-items:center;gap:10px;min-width:0;}
.c-fl div,.c-pl div{min-width:0;}
.c-fl b,.c-pl b{display:block;color:#fff;font-size:.92rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.c-fl small,.c-pl small{display:block;color:var(--muted);font-size:.72rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.fg{font-size:1.35rem;flex:none;}
.alogo{flex:none;width:44px;height:30px;border-radius:8px;background:#eef0f4 center/contain no-repeat;
  background-origin:content-box;padding:3px;box-sizing:border-box;box-shadow:0 1px 4px rgba(0,0,0,.35);}
.alogo.txt{display:inline-flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:900;padding:0;}
.c-gate{text-align:center;font-weight:800;color:#e2e8f0;font-size:.9rem;}
.c-gate.na{color:#475569;font-weight:600;}
.pill{display:inline-block;border-radius:999px;padding:4px 10px;font-size:.74rem;font-weight:800;white-space:nowrap;}
.pill.ok{background:rgba(34,197,94,.16);color:#86efac;} .pill.warn{background:rgba(245,158,11,.18);color:#fcd34d;}
.pill.bad{background:rgba(239,68,68,.18);color:#fca5a5;} .pill.info{background:rgba(56,189,248,.14);color:#7dd3fc;}
.pill.done{background:rgba(148,163,184,.14);color:#cbd5e1;}
.c-dl{text-align:right;font-weight:800;font-size:.86rem;font-variant-numeric:tabular-nums;color:#475569;}
.c-dl.warn{color:#fbbf24;} .c-dl.bad{color:#f87171;} .c-dl.ok{color:#4ade80;}
.tempty{text-align:center;color:var(--muted);padding:40px 16px;font-size:.9rem;line-height:1.6;}
.tempty .big{font-size:2.6rem;}
.tfoot{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:8px 16px;font-size:.72rem;color:#5d6a8c;}
.tnote{margin:10px 0 0;padding:8px 14px;border-radius:12px;background:var(--card);border:1px solid var(--line);font-size:.8rem;color:#cdd5ea;}
.tnote.warn{border-color:rgba(245,158,11,.5);}

/* Gözlem defteri */
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px;}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 16px;}
.kpi small{display:block;color:var(--muted);font-size:.7rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;}
.kpi b{display:block;font-size:1.9rem;color:#fff;line-height:1.15;}
.kpi span{font-size:.78rem;color:#9aa7c7;}
.bars{display:flex;align-items:flex-end;gap:10px;height:110px;padding:10px 6px 0;}
.bar{flex:1;text-align:center;display:flex;flex-direction:column;justify-content:flex-end;height:100%;}
.bar i{display:block;border-radius:8px 8px 3px 3px;background:linear-gradient(180deg,#38bdf8,#6d4aff);min-height:3px;}
.bar b{font-size:.78rem;color:#fff;margin-bottom:3px;} .bar small{font-size:.68rem;color:var(--muted);margin-top:4px;}
.sight{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--line);
  border-radius:14px;padding:10px 14px;margin-bottom:8px;}
.sight .sd{flex:1;min-width:0;} .sight b{color:#fff;} .sight small{display:block;color:var(--muted);font-size:.76rem;}
.sight .tm{font-variant-numeric:tabular-nums;color:#cbd5e1;font-weight:700;font-size:.82rem;white-space:nowrap;}
.box{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px 16px;margin-bottom:12px;}
.box h4{margin:0 0 6px;color:#fff;font-size:.95rem;}

@media (max-width:900px){
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr));}
  .fgrid.arr,.fgrid.dep{grid-template-columns:52px minmax(0,1.25fr) minmax(0,1.15fr) auto;gap:8px;padding:0 12px;}
  .fgrid .c-dl,.fgrid .c-gate,.fgrid .alogo,.fcols>div:last-child{display:none;}
  .fgrid.dep.fcols>div:nth-child(4){display:none;}
  .c-pl .fg{font-size:1.1rem;}
  .clock{font-size:1.5rem;}
}
</style>
"""

# =============================================================================
# YARDIMCI FONKSİYONLAR
# =============================================================================


def haversine_km(lat1, lon1, lat2, lon2):
  r = 6371.0
  p1, p2 = math.radians(lat1), math.radians(lat2)
  dphi = p2 - p1
  dl = math.radians(lon2 - lon1)
  a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
  return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
  p1, p2 = math.radians(lat1), math.radians(lat2)
  dl = math.radians(lon2 - lon1)
  y = math.sin(dl) * math.cos(p2)
  x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
  return (math.degrees(math.atan2(y, x)) + 360) % 360


def dest_point(lat, lon, bearing, km):
  r = 6371.0
  b = math.radians(bearing)
  p1, l1 = math.radians(lat), math.radians(lon)
  d = km / r
  p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
  l2 = l1 + math.atan2(
      math.sin(b) * math.sin(d) * math.cos(p1),
      math.cos(d) - math.sin(p1) * math.sin(p2),
  )
  return math.degrees(p2), math.degrees(l2)


def angle_diff(a, b):
  return abs((a - b + 180) % 360 - 180)


def flag(iso):
  if not iso or len(iso) != 2 or not iso.isalpha():
    return "🏳️"
  return "".join(chr(0x1F1E6 + ord(c) - 65) for c in iso.upper())


def fmt_int(n):
  return f"{int(n):,}".replace(",", ".")


def esc(x):
  return html.escape(str(x)) if x is not None else ""


# =============================================================================
# VERİ KATMANI
# =============================================================================


@st.cache_data(ttl=1500, show_spinner=False)
def _opensky_token(client_id, client_secret):
  r = requests.post(
      OPENSKY_TOKEN_URL,
      data={
          "grant_type": "client_credentials",
          "client_id": client_id,
          "client_secret": client_secret,
      },
      timeout=6,
  )
  r.raise_for_status()
  return r.json()["access_token"]


def get_bearer():
  """secrets.toml içinde OpenSky bilgisi varsa token döndürür, yoksa ''."""
  if time.time() < _SRC["os_down_until"]:  # OpenSky ulaşılamıyor: boşuna token isteği bekleme
    return ""
  try:
    cid = st.secrets["opensky_client_id"]
    sec = st.secrets["opensky_client_secret"]
  except Exception:
    return ""
  if not cid or not sec:
    return ""
  try:
    return _opensky_token(cid, sec)
  except Exception:
    _SRC["os_down_until"] = time.time() + 300
    return ""


def bbox_for(radius_km):
  """Havalimanı merkezli kare sorgu kutusu."""
  dlat = radius_km / 111.2
  dlon = radius_km / (111.2 * math.cos(math.radians(AIRPORT_LAT)))
  return {"lamin": round(AIRPORT_LAT - dlat, 3), "lamax": round(AIRPORT_LAT + dlat, 3),
          "lomin": round(AIRPORT_LON - dlon, 3), "lomax": round(AIRPORT_LON + dlon, 3)}


def _err_word(e):
  n = type(e).__name__.lower()
  if "timeout" in n:
    return "zaman aşımı"
  if "connection" in n:
    return "bağlantı kurulamadı"
  return "ulaşılamadı"


def _from_opensky(bearer, radius_km):
  """(states, hata_metni). Hata yoksa metin ''."""
  headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
  try:
    r = requests.get(OPENSKY_URL, params=bbox_for(radius_km + 10), headers=headers,
                     timeout=OPENSKY_TIMEOUT)
  except requests.RequestException as e:
    return None, f"OpenSky {_err_word(e)}"
  if r.status_code == 429:
    return None, "OpenSky günlük sorgu sınırı doldu"
  if r.status_code != 200:
    return None, f"OpenSky hata kodu {r.status_code}"
  try:
    return r.json().get("states") or [], ""
  except ValueError:
    return None, "OpenSky yanıtı okunamadı"


def _num(x):
  return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def adsblol_to_states(js):
  """adsb.lol (readsb) yanıtını OpenSky 'state vector' biçimine çevirir."""
  now = time.time()
  out = []
  for a in (js or {}).get("ac") or []:
    try:
      lat, lon = _num(a.get("lat")), _num(a.get("lon"))
      hexid = str(a.get("hex") or "").lower()
      if lat is None or lon is None or not hexid or hexid.startswith("~"):
        continue
      alt = a.get("alt_baro")
      ground = alt == "ground"
      alt_ft = None if ground else _num(alt)
      alt_m = None if alt_ft is None else alt_ft / 3.28084
      geo_ft = _num(a.get("alt_geom"))
      gs = _num(a.get("gs"))
      vr = _num(a.get("baro_rate"))
      if vr is None:
        vr = _num(a.get("geom_rate"))
      seen = _num(a.get("seen_pos")) or 0.0
      tp = now - seen
      out.append([hexid, str(a.get("flight") or "").strip(), "", tp, tp, lon, lat, alt_m, ground,
                  None if gs is None else gs * 0.514444, _num(a.get("track")),
                  None if vr is None else vr / 196.85, None,
                  None if geo_ft is None else geo_ft / 3.28084, None, False, 0])
    except Exception:  # tek bozuk kayıt tüm listeyi düşürmesin
      continue
  return out


def _from_adsblol(radius_km):
  nm = min(250, max(1, math.ceil((radius_km + 10) / 1.852)))
  url = ADSBLOL_URL.format(lat=AIRPORT_LAT, lon=AIRPORT_LON, nm=nm)
  try:
    r = requests.get(url, timeout=8)
  except requests.RequestException as e:
    return None, f"adsb.lol {_err_word(e)}"
  if r.status_code != 200:
    return None, f"adsb.lol hata kodu {r.status_code}"
  try:
    return adsblol_to_states(r.json()), ""
  except ValueError:
    return None, "adsb.lol yanıtı okunamadı"


_TCACHE = {}          # (bearer, yarıçap) -> (zaman, sonuç)   (tüm oturumlar için ortak)
STALE_OK_S = 120      # sayfa geçişinde bu kadar eski veri anında gösterilir, arka planda tazelenir


def fetch_states(bearer, radius_km=NEAR_KM, allow_stale=False):
  """(states, durum_mesajı, epoch). FETCH_TTL sn önbellek. allow_stale=True iken (sayfa geçişi)
  eski ama başarılı veri beklemeden verilir, tazesi arka planda çekilir."""
  key = (bearer, radius_km)
  hit = _TCACHE.get(key)
  now = time.time()
  if hit:
    age = now - hit[0]
    if age < FETCH_TTL:
      return hit[1]
    if allow_stale and age < STALE_OK_S and hit[1][1] == "ok":
      with _BG_LOCK:
        busy = ("traffic", key) in _BG["logo"]
        _BG["logo"].add(("traffic", key))

      def work():
        try:
          _TCACHE[key] = (time.time(), _fetch_states_live(bearer, radius_km))
        except Exception:
          pass
        finally:
          with _BG_LOCK:
            _BG["logo"].discard(("traffic", key))
      if not busy:
        _spawn(work)
      return hit[1]
  res = _fetch_states_live(bearer, radius_km)
  _TCACHE[key] = (time.time(), res)
  return res


def _fetch_states_live(bearer, radius_km=NEAR_KM):
  """Önce OpenSky, ulaşılamazsa ücretsiz adsb.lol. Hata olsa da uygulama çökmez;
  kullanılan kaynak _SRC['last_source'] içinde tutulur."""
  now = time.time()
  pref = str(secret("TRAFFIC_SOURCE", "auto")).strip().lower()
  if pref == "adsblol":
    order = ["adsblol"]
  elif pref == "opensky":
    order = ["opensky"]
  elif now < _SRC["os_down_until"]:
    order = ["adsblol", "opensky"]
  else:
    order = ["opensky", "adsblol"]
  errors = []
  for src in order:
    if src == "opensky":
      states, err = _from_opensky(bearer, radius_km)
      if err:
        _SRC["os_down_until"] = time.time() + OPENSKY_DOWN_S
    else:
      states, err = _from_adsblol(radius_km)
    if not err:
      _SRC["last_source"] = "OpenSky Network" if src == "opensky" else "adsb.lol"
      return states, "ok", time.time()
    errors.append(err)
  _SRC["last_source"] = ""
  return [], " · ".join(errors), time.time()


@st.cache_resource
def get_store():
  """Tüm oturumlar için ortak önbellek (rota, uçak, logo, fotoğraf)."""
  return {}


def cached(store, key, ttl_ok, ttl_fail, fn):
  """Basit TTL önbelleği. Boş sonuç kısa süre, dolu sonuç uzun süre saklanır."""
  now = time.time()
  hit = store.get(key)
  if hit and hit[0] > now:
    return hit[1]
  val = fn()
  failed = (not val) or (isinstance(val, dict) and val.get("_state") == "err")
  store[key] = (now + (ttl_fail if failed else ttl_ok), val)
  if len(store) > 3000:
    for k in [k for k, v in store.items() if v[0] < now]:
      store.pop(k, None)
  return val


def _get_json(url, timeout=3):
  try:
    r = requests.get(url, timeout=timeout)
    if r.status_code == 200:
      return r.json()
  except (requests.RequestException, ValueError):
    pass
  return None


def _get_json_ex(url, timeout=3):
  """('ok'|'none'|'err', json). 404 = kayıt gerçekten yok ('none'); ağ/sunucu hatası = 'err'."""
  try:
    r = requests.get(url, timeout=timeout)
    if r.status_code == 200:
      return "ok", r.json()
    if r.status_code == 404:
      return "none", None
  except (requests.RequestException, ValueError):
    pass
  return "err", None


def lookup_route(callsign, store):
  """adsbdb: çağrı kodundan rota (kalkış/varış, havayolu).

  Sonuç sözlüğü: rota varsa adsbdb 'flightroute' alanları; yoksa {"_state": "none"};
  geçici hata ise {"_state": "err"} (kısa süre saklanır, uçak gizlenmez)."""
  def go():
    state, j = _get_json_ex(f"{ADSBDB}/callsign/{callsign}")
    if state == "err":
      return {"_state": "err"}
    resp = (j or {}).get("response")
    fr = (resp.get("flightroute") or {}) if isinstance(resp, dict) else {}
    if fr and (fr.get("origin") or fr.get("destination")):
      return fr
    return {"_state": "none"}
  return cached(store, ("route", callsign), 900, 120, go)


def lookup_aircraft(icao24, store):
  """adsbdb: uçak kaydı (tür, üretici, tescil, fotoğraf)."""
  def go():
    j = _get_json(f"{ADSBDB}/aircraft/{icao24}") or {}
    resp = j.get("response")
    return (resp.get("aircraft") or {}) if isinstance(resp, dict) else {}
  return cached(store, ("ac", icao24), 86400, 120, go)


def lookup_photo(icao24, store):
  """planespotters.net: adsbdb'de fotoğraf yoksa yedek kaynak."""
  def go():
    j = _get_json(f"https://api.planespotters.net/pub/photos/hex/{icao24}") or {}
    ph = (j.get("photos") or [None])[0]
    if not ph:
      return {}
    src = (ph.get("thumbnail_large") or ph.get("thumbnail") or {}).get("src", "")
    return {"src": src, "credit": ph.get("photographer", "")} if src else {}
  return cached(store, ("photo", icao24), 86400, 300, go)


def fetch_logo(key, iata, store):
  """Önce assets/logos/<KEY>.*, yoksa internetten indirip base64 olarak gömer."""
  def go():
    mimes = {"png": "image/png", "svg": "image/svg+xml", "webp": "image/webp",
             "jpg": "image/jpeg"}
    for ext, mime in mimes.items():
      p = LOGO_DIR / f"{key}.{ext}"
      if p.exists():
        return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"
    if not iata:
      return ""
    for tpl in LOGO_URLS:
      try:
        r = requests.get(tpl.format(iata=iata), timeout=4)
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and ctype.startswith("image") and len(r.content) > 300:
          return f"data:{ctype.split(';')[0]};base64,{base64.b64encode(r.content).decode()}"
      except requests.RequestException:
        continue
    return ""
  return cached(store, ("logo", key, iata), 7 * 86400, 3600, go)


@st.cache_data(ttl=600, show_spinner=False)
def fetch_weather():
  try:
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": HOME_LAT,
            "longitude": HOME_LON,
            "current": "temperature_2m,weather_code,wind_speed_10m,wind_direction_10m",
            "timezone": "Europe/Amsterdam",
        },
        timeout=4,
    )
    if r.status_code == 200:
      c = r.json()["current"]
      emoji, text = WMO.get(c.get("weather_code"), ("🌡️", ""))
      return {
          "temp": round(c["temperature_2m"]),
          "emoji": emoji,
          "text": text,
          "wind": round(c.get("wind_speed_10m", 0)),
          "wind_dir": c.get("wind_direction_10m"),
      }
  except (requests.RequestException, ValueError, KeyError):
    pass
  return None


# =============================================================================
# UÇUŞ NESNESİ OLUŞTURMA
# =============================================================================


def airport_view(a):
  if not a:
    return None
  return {
      "iata": a.get("iata_code") or a.get("icao_code") or "?",
      "icao": a.get("icao_code"),
      "city": a.get("municipality") or a.get("name") or "",
      "flag": flag(a.get("country_iso_name")),
      "lat": a.get("latitude"),
      "lon": a.get("longitude"),
  }


def enrich_geometry(f):
  """Evden uzaklık, yaklaşıyor mu, tahmini geçiş süresi, görünürlük."""
  f["dist_home"] = haversine_km(f["lat"], f["lon"], HOME_LAT, HOME_LON)
  to_home = bearing_deg(f["lat"], f["lon"], HOME_LAT, HOME_LON)
  f["approaching"] = angle_diff(f["track"], to_home) < 60 and f["speed"] > 80
  f["eta_min"] = (f["dist_home"] / f["speed"] * 60) if f["approaching"] else None
  f["visible"] = f["dist_home"] <= CFG["visible_km"] and f["alt_ft"] <= CFG["visible_alt"]
  if f["vrate"] > 1:
    f["phase"] = "Tırmanıyor ⬆"
  elif f["vrate"] < -1:
    f["phase"] = "Alçalıyor ⬇"
  else:
    f["phase"] = "Düz uçuyor ➡"
  if f["dir"] == "TRN":
    f["phase"] = "Yukarıdan geçiyor ➡"
  return f


def resolve_airline(prefix, route, ac):
  """(anahtar, ad, IATA) döndürür."""
  key = ALIASES.get(prefix, prefix)
  ral = (route or {}).get("airline") or {}
  if key in AIRLINES:
    return key, AIRLINES[key][0], AIRLINES[key][3]
  name = ral.get("name") or ac.get("registered_owner") or (prefix or "Bilinmiyor")
  return (key or ral.get("icao") or ""), name, ral.get("iata") or ""


def _inbound(s, lat, lon):
  """Alçalıyor ve havalimanına doğru gidiyor mu?"""
  if s[10] is None or (s[11] or 0) > -1.0:
    return False
  to_airport = bearing_deg(lat, lon, AIRPORT_LAT, AIRPORT_LON)
  return angle_diff(s[10], to_airport) <= 30


def _candidates(states, overflights=False, coverage_km=NEAR_KM):
  """Hangi uçaklar işlenecek?
    near    : havalimanına 50 km içinde, 10.000 ft altı
    transit : (seçenek açıksa) evden 30 km içinde, yüksekte geçenler
    inbound : 50 km dışında ama EIN'e doğru alçalanlar (kapsama genişse)
  """
  out = []
  for s in states:
    lon, lat = s[5], s[6]
    if lat is None or lon is None or s[8]:  # konum yok ya da yerde
      continue
    alt_m = s[7] if s[7] is not None else s[13]
    alt_ft = round((alt_m or 0) * 3.28084)
    d_air = haversine_km(lat, lon, AIRPORT_LAT, AIRPORT_LON)
    d_home = haversine_km(lat, lon, HOME_LAT, HOME_LON)
    if d_air <= NEAR_KM and alt_ft <= MAX_SHOW_ALT_FT:
      kind = "near"
    elif overflights and d_home <= CFG["overflight_km"]:
      kind = "transit"
    elif (NEAR_KM < d_air <= coverage_km and alt_ft <= INBOUND_MAX_ALT_FT
          and _inbound(s, lat, lon)):
      kind = "inbound"
    else:
      continue
    out.append((s, alt_ft, kind, d_air))
  return out


def build_flights(states, store, overflights=False, coverage_km=NEAR_KM, show_unknown=False, stats=None):
  """stats (sözlük) verilirse stats["hidden_unknown"] = rotası bilinmediği için gizlenen uçak sayısı."""
  hidden = 0
  cands = _candidates(states, overflights, coverage_km)
  callsigns = sorted({(c[0][1] or "").strip() for c in cands} - {""})
  hexes = sorted({c[0][0] for c in cands})
  with ThreadPoolExecutor(ENRICH_WORKERS) as pool:
    routes = dict(zip(callsigns, pool.map(lambda c: lookup_route(c, store), callsigns)))
    acs = dict(zip(hexes, pool.map(lambda h: lookup_aircraft(h, store), hexes)))

  flights = []
  for s, alt_ft, kind, d_air in cands:
    icao24 = s[0]
    callsign = (s[1] or "").strip()
    lon, lat = s[5], s[6]
    route = routes.get(callsign) or {}
    pending = route.get("_state") == "err"           # geçici hata: uçağı gizleme, tekrar denenecek
    if route.get("_state"):
      route = {}
    has_route = bool(route.get("origin") or route.get("destination"))
    if not has_route and not pending and not show_unknown:
      hidden += 1                                    # rotası bilinmiyor: listede/haritada gösterme
      continue
    ac = acs.get(icao24) or {}
    prefix = callsign[:3].upper() if callsign[:3].isalpha() else ""
    akey, aname, aiata = resolve_airline(prefix, route, ac)
    origin = airport_view(route.get("origin"))
    dest = airport_view(route.get("destination"))
    to_ein = bool(dest and dest["icao"] == AIRPORT_ICAO)
    from_ein = bool(origin and origin["icao"] == AIRPORT_ICAO)

    # Uzaktan gelenler yalnızca EIN'e iniyorsa tutulur
    if kind == "inbound" and not (to_ein or (not has_route and d_air <= 80)):
      continue

    vrate = s[11] or 0
    if to_ein:
      direction = "ARR"
    elif from_ein:
      direction = "DEP"
    elif has_route or kind == "transit":  # rotası bilinen ve EIN ile ilgisi olmayan
      direction = "TRN"
    else:
      direction = "ARR" if vrate < 0 else "DEP"
    if direction == "TRN" and not overflights:
      continue

    tcode = ac.get("icao_type") or ""
    tinfo = AIRCRAFT_TYPES.get(tcode)
    if tinfo:
      tname, seats, fact = tinfo
    else:
      tname = " ".join(x for x in [ac.get("manufacturer"), ac.get("type")] if x) or "Bilinmiyor"
      seats, fact = None, ""
    capacity = seat_text(akey, tcode, seats)

    progress = None
    if origin and dest and origin["lat"] and dest["lat"]:
      d1 = haversine_km(origin["lat"], origin["lon"], lat, lon)
      d2 = haversine_km(lat, lon, dest["lat"], dest["lon"])
      if d1 + d2 > 0:
        progress = max(0, min(100, round(d1 / (d1 + d2) * 100)))

    f = {
        "id": icao24, "label": callsign or icao24, "callsign": callsign or icao24,
        "lat": lat, "lon": lon, "alt_ft": alt_ft,
        "speed": round((s[9] or 0) * 3.6), "track": s[10] or 0, "vrate": vrate,
        "airline_key": akey, "airline": aname, "airline_iata": aiata, "logo": "",
        "dir": direction, "origin": origin, "dest": dest, "progress": progress,
        "type_code": tcode, "type_name": tname, "capacity": capacity, "fact": fact,
        "reg": ac.get("registration") or "", "photo": ac.get("url_photo_thumbnail") or "",
        "photo_credit": "", "country": s[2] or "", "tpos": s[3] or s[4] or 0,
        "route_known": has_route, "route_pending": pending,
    }
    flights.append(enrich_geometry(f))
  if stats is not None:
    stats["hidden_unknown"] = hidden
  return flights


_BG = {"logo": set(), "threads": []}
_BG_LOCK = threading.Lock()


def _spawn(fn, *args):
  t = threading.Thread(target=fn, args=args, daemon=True, name="radar-bg")
  with _BG_LOCK:
    _BG["threads"] = [x for x in _BG["threads"] if x.is_alive()] + [t]
  t.start()
  return t


_WARM = {"t": 0.0, "busy": False}
WARM_EVERY_S = 25


def warm_radar(store, bearer, cov_km):
  """Radar dışındaki sayfalardayken (ör. açılış sayfası Terminal) trafik verisini, rota ve uçak
  kayıtlarını arka planda ısıtır: Radar sekmesine geçildiğinde hepsi hazır olur."""
  now = time.time()
  with _BG_LOCK:
    if _WARM["busy"] or now - _WARM["t"] < WARM_EVERY_S:
      return
    _WARM["busy"] = True
    _WARM["t"] = now

  def work():
    try:
      res = _fetch_states_live(bearer, cov_km)
      _TCACHE[(bearer, cov_km)] = (time.time(), res)
      if res[1] == "ok":
        fl = build_flights(res[0], store, False, cov_km, True)
        attach_logos(fl, store)
    except Exception:
      pass
    finally:
      with _BG_LOCK:
        _WARM["busy"] = False
  _spawn(work)


def join_background(timeout=10):
  """Testler için: bekleyen arka plan işlerinin bitmesini bekler."""
  for t in list(_BG["threads"]):
    t.join(timeout)


def peek_logo(key, iata, store):
  """Beklemeden logo: önbellekte varsa verir, yoksa arka planda indirmeyi başlatır.
  (logo, bekliyor_mu) döndürür."""
  ck = ("logo", key, iata)
  hit = store.get(ck)
  if hit and hit[0] > time.time():
    return hit[1], False
  with _BG_LOCK:
    if ck in _BG["logo"]:
      return (hit[1] if hit else ""), True
    _BG["logo"].add(ck)

  def work():
    try:
      fetch_logo(key, iata, store)
    except Exception:
      pass
    finally:
      with _BG_LOCK:
        _BG["logo"].discard(ck)
  _spawn(work)
  return (hit[1] if hit else ""), True


def attach_logos(flights, store):
  """Logoyu beklemeden bağlar: önbellekte olan hemen gelir, olmayan arka planda indirilir
  (o ana kadar renkli harf rozeti görünür)."""
  logos = {}
  for k in sorted({(f["airline_key"], f["airline_iata"]) for f in flights
                   if f["airline_key"] or f["airline_iata"]}):
    logos[k] = peek_logo(k[0], k[1], store)[0]
  for f in flights:
    f["logo"] = logos.get((f["airline_key"], f["airline_iata"]), "")
  return flights


def infer_runway(states, wind_dir=None):
  """Aktif pisti tahmin eder (03 = kuzeydoğuya, 21 = güneybatıya doğru).

  Önce havalimanına 10 km içindeki uçakların gidiş yönüne bakar (canlı).
  Yeterli uçak yoksa rüzgâr yönüne göre tahmin eder (uçaklar rüzgâra karşı iner)."""
  votes = {"03": 0, "21": 0}
  for s in states:
    lon, lat, track = s[5], s[6], s[10]
    if lat is None or lon is None or track is None:
      continue
    if haversine_km(lat, lon, AIRPORT_LAT, AIRPORT_LON) > RUNWAY_NEAR_KM:
      continue
    alt_m = s[7] if s[7] is not None else s[13]
    alt_ft = (alt_m or 0) * 3.28084
    spd = (s[9] or 0) * 3.6
    if s[8]:  # yerde
      if spd < 70:  # taksi yapıyor, pistte değil
        continue
      w = 2
    else:
      if alt_ft > 3000 or spd < 120:
        continue
      w = 1
    if angle_diff(track, RUNWAY_AXIS) <= 25:
      votes["03"] += w
    elif angle_diff(track, RUNWAY_AXIS + 180) <= 25:
      votes["21"] += w
  total = votes["03"] + votes["21"]
  if total >= 2 and max(votes.values()) / total >= 0.75:
    return {"rwy": "03" if votes["03"] > votes["21"] else "21", "source": "live", "n": total}
  if wind_dir is not None:
    h03 = math.cos(math.radians(angle_diff(wind_dir, RUNWAY_AXIS)))
    h21 = math.cos(math.radians(angle_diff(wind_dir, RUNWAY_AXIS + 180)))
    if abs(h03 - h21) > 0.3:
      return {"rwy": "03" if h03 > h21 else "21", "source": "wind", "n": 0}
  return {"rwy": None, "source": "", "n": 0}


def demo_flights(overflights=False):
  """Gece uçuş olmadığında arayüzü denemek için örnek uçaklar."""
  ath = {"iata": "ATH", "icao": "LGAV", "city": "Athens", "flag": "🇬🇷", "lat": 37.936, "lon": 23.947}
  ein = {"iata": "EIN", "icao": "EHEH", "city": "Eindhoven", "flag": "🇳🇱",
         "lat": AIRPORT_LAT, "lon": AIRPORT_LON}
  ayt = {"iata": "AYT", "icao": "LTAI", "city": "Antalya", "flag": "🇹🇷", "lat": 36.899, "lon": 30.8}
  agp = {"iata": "AGP", "icao": "LEMG", "city": "Málaga", "flag": "🇪🇸", "lat": 36.675, "lon": -4.499}
  base = [
      ("TRA6710", "TRA", "Transavia", "ARR", ath, ein, 51.5050, 5.5200, 215, 2400, 275, 3, -4, "B738", "PH-HXA", 82),
      ("RYR4123", "RYR", "Ryanair", "ARR", agp, ein, 51.5300, 5.5350, 215, 4200, 300, 3, -6, "B738", "EI-DWA", 70),
      ("TUI412", "TUI", "TUI", "DEP", ein, ayt, 51.4700, 5.4300, 30, 1800, 250, 3, 8, "B38M", "PH-TFA", 5),
  ]
  out = []
  for (cs, ak, an, d, o, de, lat, lon, trk, alt, spd, _, vr, tc, reg, prog) in base:
    tname, seats, fact = AIRCRAFT_TYPES[tc]
    cap = seat_text(ak, tc, seats)
    f = {"id": f"demo-{cs}", "label": cs, "callsign": cs, "lat": lat, "lon": lon,
         "alt_ft": alt, "speed": spd, "track": trk, "vrate": vr, "airline_key": ak,
         "airline": an, "dir": d, "origin": o, "dest": de, "progress": prog,
         "type_code": tc, "type_name": tname, "capacity": cap, "fact": fact,
         "reg": reg, "photo": "", "photo_credit": "", "country": "", "tpos": 0,
         "airline_iata": AIRLINES[ak][3], "logo": ""}
    out.append(enrich_geometry(f))
  if overflights:
    fra = {"iata": "FRA", "icao": "EDDF", "city": "Frankfurt", "flag": "🇩🇪", "lat": 50.033, "lon": 8.571}
    lhr = {"iata": "LHR", "icao": "EGLL", "city": "London", "flag": "🇬🇧", "lat": 51.47, "lon": -0.454}
    tname, seats, fact = AIRCRAFT_TYPES["A320"]
    cap = seat_text("DLH", "A320", seats)
    out.append(enrich_geometry({
        "id": "demo-DLH4AB", "label": "DLH4AB", "callsign": "DLH4AB", "lat": 51.53, "lon": 5.40,
        "alt_ft": 36000, "speed": 830, "track": 285, "vrate": 0, "airline_key": "DLH",
        "airline": "Lufthansa", "dir": "TRN", "origin": fra, "dest": lhr, "progress": 38,
        "type_code": "A320", "type_name": tname, "capacity": cap, "fact": fact,
        "reg": "D-AIZZ", "photo": "", "photo_credit": "", "country": "", "tpos": 0,
        "airline_iata": "LH", "logo": ""}))
  return sorted(out, key=lambda x: x["dist_home"])


# =============================================================================
# HTML PARÇALARI
# =============================================================================


def logo_html(f, size="md"):
  cls = f"logo logo-{size}"
  if f.get("logo"):
    return (f"<span class='{cls} logo-img'><img src='{f['logo']}' "
            f"alt='{esc(f['airline'])}'></span>")
  _, bg, fg, _i = AIRLINES.get(f["airline_key"], (f["airline"], "#2b3558", "#ffffff", ""))
  return f"<span class='{cls}' style='background:{bg};color:{fg}'>{esc(f['airline'])}</span>"


def dir_badge(f):
  if f["dir"] == "TRN":
    return "<span class='badge trn'>GEÇİŞ ➡</span>"
  if f["dir"] == "ARR":
    return "<span class='badge arr'>GELİŞ ⬇</span>"
  return "<span class='badge dep'>KALKIŞ ⬆</span>"


def route_short(f):
  o, d = f["origin"], f["dest"]
  if not (o or d):
    return "Rota aranıyor…" if f.get("route_pending") else "Rota bilinmiyor"
  left = f"{o['flag']} {esc(o['iata'])}" if o else "❓"
  right = f"{d['flag']} {esc(d['iata'])}" if d else "❓"
  return f"{left} → {right}"


def eta_text(f):
  if f["eta_min"] is None:
    return f"Evden {f['dist_home']:.1f} km"
  if f["eta_min"] < 1:
    return "Şimdi bahçenin üstünde!"
  return f"≈ {round(f['eta_min'])} dk sonra bahçede"


def topbar_html(weather, now, counts, mode, status):
  dot = {"live": "live", "demo": "demo"}.get(mode, "err")
  label = {"live": "Canlı", "demo": "Demo", "err": "Bağlantı yok"}.get(mode, "Canlı")
  w = (f"<span class='chip'>{weather['emoji']} <b>{weather['temp']}°C</b> · {esc(weather['text'])}"
       f" · 💨 {weather['wind']} km/sa</span>") if weather else ""
  warn = f"<span class='chip'>⚠️ {esc(status)}</span>" if status not in ("ok", "") else ""
  trn = f" · ➡ {counts['trn']}" if counts["trn"] else ""
  hid = (f"<span class='chip' title='Rotası bilinmeyen uçaklar listede ve haritada gösterilmiyor (⚙️ ile açılabilir)'>"
         f"🙈 <b>{counts['hidden']}</b></span>") if counts.get("hidden") else ""
  return f"""
  <div class='topbar'>
    <div class='brand'>🧑‍✈️ Atlas'ın Uçak Gözlem Kulesi ✈️<small>Blixembosch bahçesinden Eindhoven gökyüzü · bugün hangi uçaklar geçiyor? 🔭</small></div>
    <div class='chips'>
      {warn}{w}
      <span class='chip'>✈ <b>{counts['total']}</b> uçak · ⬇ {counts['arr']} · ⬆ {counts['dep']}{trn} · 👀 {counts['vis']}</span>
      <span class='chip' title='Tarama alanındaki toplam uçak (filtre öncesi)'>📡 <b>{counts['raw']}</b></span>{hid}
      <span class='chip' title='Veri yenileme sıklığı (yaklaşan uçak varken hızlanır)'>🔄 <b>{counts['refresh']} sn</b></span>
      <span class='chip'>🕘 <b>{now.strftime('%H:%M:%S')}</b></span>
      <span class='chip'><span class='dot {dot}'></span><b>{label}</b></span>
    </div>
  </div>"""


def runway_html(info):
  rwy = info["rwy"]
  if not rwy:
    return ("<div class='strip'><span class='ic'>🧭</span><span class='tx'>Aktif pist henüz belli değil"
            "<span class='sub'>· yakında uçak yok</span></span></div>")
  src = {"live": "canlı", "wind": "rüzgâr tahmini", "demo": "demo"}.get(info["source"], "")
  if rwy == "21":
    txt = "<b>Pist 21</b> · 🛬 kuzeydoğudan iniyor (bahçe tarafı) · 🛫 güneybatıya kalkıyor"
  else:
    txt = "<b>Pist 03</b> · 🛫 kuzeydoğuya kalkıyor (bahçe tarafı) · 🛬 güneybatıdan iniyor"
  return (f"<div class='strip'><span class='ic'>🧭</span><span class='tx'>{txt}"
          f"<span class='sub'>· {src}</span></span></div>")


def next_banner_html(flights, updated):
  cand = [f for f in flights if f["eta_min"] is not None and f["alt_ft"] <= CFG["visible_alt"] * 1.6]
  if not cand:
    return (f"<div class='strip'><span class='ic'>🔭</span><span class='tx'>Şu an bahçeye yaklaşan uçak yok"
            f"<span class='sub'>· {updated}</span></span></div>")
  f = min(cand, key=lambda x: x["eta_min"])
  o = f["origin"]
  frm = f"{o['flag']} {esc(o['city'])}" if (o and f["dir"] == "ARR") else ""
  verb = f"{frm}'dan geliyor" if frm else ("kalkış yaptı" if f["dir"] == "DEP" else "yaklaşıyor")
  return (f"<div class='strip hot'><span class='ic'>👀</span><span class='tx'>Sıradaki: <b>{esc(f['callsign'])}</b>"
          f" · {esc(f['airline'])} · {verb} · <b>{eta_text(f)}</b>"
          f"<span class='sub'>· {fmt_int(f['alt_ft'])} ft</span></span></div>")


def detail_html(f):
  if f is None:
    return ("<div class='panel'><div class='empty'><div class='big'>😴</div>"
            "Şu an koridorda uçak yok.<br>Haritadan ya da alttaki kartlardan bir uçak seçince"
            " burada detayları görünür.</div></div>")
  o, d = f["origin"], f["dest"]
  prog = f["progress"]

  def ap(a):
    if not a:
      return "<div class='ap'><div class='fl'>❓</div><div class='code'>?</div><div class='city'>bilinmiyor</div></div>"
    return (f"<div class='ap'><div class='fl'>{a['flag']}</div><div class='code'>{esc(a['iata'])}</div>"
            f"<div class='city'>{esc(a['city'])}</div></div>")

  if prog is not None:
    bar = (f"<div class='prog'><div class='prog-fill' style='width:{prog}%'></div>"
           f"<span class='prog-plane' style='left:{prog}%'>✈</span></div>")
  else:
    bar = "<div class='prog'></div>"

  photo = ""
  if f["photo"]:
    who = f"{esc(f['photo_credit'])} · " if f.get("photo_credit") else ""
    photo = (f"<img class='ph' src='{esc(f['photo'])}'>"
             f"<div class='credit'>📷 {who}planespotters.net</div>")

  vis = ("<span class='badge vis'>👀 Bahçeden görünür</span>" if f["visible"]
         else "<span class='badge far'>Uzakta</span>")
  reg = f" · {esc(f['reg'])}" if f["reg"] else ""
  fact = f"<div class='fact'>💡 {esc(f['fact'])}</div>" if f["fact"] else ""
  alt_m = round(f["alt_ft"] * 0.3048)
  return f"""
  <div class='panel'>
    <div class='head'>{logo_html(f, 'xl')}<div style='text-align:right'>{dir_badge(f)}<br><span style='display:inline-block;margin-top:6px'>{vis}</span></div></div>
    <div class='cs'>{esc(f['callsign'])}</div>
    <div class='al'>{esc(f['airline'])} · {esc(f['type_name'])}{reg}</div>
    {photo}
    <div class='route'>{ap(o)}{bar}{ap(d)}</div>
    <div class='grid2'>
      <div class='stat'><small>Yükseklik</small><b>{fmt_int(f['alt_ft'])} ft</b> <span style='color:#8b97b8;font-size:.8rem'>({fmt_int(alt_m)} m)</span></div>
      <div class='stat'><small>Hız</small><b>{fmt_int(f['speed'])} km/sa</b> <span style='color:#8b97b8;font-size:.8rem'>({fmt_int(f['speed'] / 1.852)} kt)</span></div>
      <div class='stat'><small>Evden uzaklık</small><b>{f['dist_home']:.1f} km</b></div>
      <div class='stat'><small>Koltuk</small><b>{esc(f['capacity'])}</b></div>
    </div>
    <div class='status2'>
      <div class='sbox a'>{esc(f['phase'])}</div>
      <div class='sbox b'>{eta_text(f)}</div>
    </div>
    {fact}
  </div>"""


def card_html(f, selected):
  cls = "fcard sel" if selected else "fcard"
  vis = "👀 görünür" if f["visible"] else ("geçiş" if f["dir"] == "TRN" else "uzakta")
  return f"""
  <div class='{cls}'>
    <div class='r1'>{logo_html(f, 'md')}{dir_badge(f)}</div>
    <div class='cs'>{esc(f['callsign'])}</div>
    <div class='rt'>{route_short(f)}</div>
    <div class='meta'>{esc(f['type_name'])} · {fmt_int(f['alt_ft'])} ft · {vis}</div>
    <div class='meta'>🛩️ {fmt_int(f['speed'])} km/sa · 💺 {esc(f['capacity'])}</div>
    <div class='meta'>{eta_text(f)}</div>
  </div>"""


# =============================================================================
# HARİTA
# =============================================================================


SEL_COLOR = "#facc15"  # seçili uçağın rengi (sarı)


def plane_icon(f, selected):
  color = SEL_COLOR if selected else {"ARR": "#38bdf8", "DEP": "#fb923c", "TRN": "#a78bfa"}.get(
      f["dir"], "#38bdf8")
  size = 46 if selected else 34
  opacity = 1 if (f["visible"] or selected) else 0.55
  ring = ""
  if selected:
    ring = (f"<div style='position:absolute;inset:-3px;border:2px solid {SEL_COLOR};"
            "border-radius:50%;background:rgba(250,204,21,.16);"
            f"box-shadow:0 0 16px {SEL_COLOR}'></div>")
  svg = (f"<svg viewBox='0 0 24 24' width='{size}' height='{size}' style='position:relative;"
         f"transform:rotate({f['track']}deg);filter:drop-shadow(0 0 3px {color})'>"
         f"<path fill='{color}' stroke='#0b1020' stroke-width='.6' d='{PLANE_PATH}'/></svg>")
  html_ = (f"<div style='position:relative;width:{size}px;height:{size}px;opacity:{opacity}'>"
           f"{ring}{svg}</div>")
  return folium.DivIcon(html=html_, icon_size=(size, size), icon_anchor=(size // 2, size // 2),
                        class_name="plane-icon")


TIP_CSS = """<style>
.leaflet-tooltip.plane-tip{background:rgba(13,20,43,.94);color:#fff;border:1px solid rgba(255,255,255,.16);
  border-radius:999px;padding:5px 12px 5px 11px;box-shadow:0 6px 18px rgba(0,0,0,.45);
  font:800 12.5px/1 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;letter-spacing:.05em;white-space:nowrap;}
.leaflet-tooltip.plane-tip:after{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;
  margin-left:8px;vertical-align:1px;background:#38bdf8;box-shadow:0 0 8px currentColor;color:#38bdf8;}
.leaflet-tooltip.plane-tip.dep:after{background:#fb923c;color:#fb923c;}
.leaflet-tooltip.plane-tip.trn:after{background:#a78bfa;color:#a78bfa;}
.leaflet-tooltip.plane-tip.sel{border-color:#facc15;background:rgba(40,32,6,.95);color:#fde68a;}
.leaflet-tooltip.plane-tip.sel:after{background:#facc15;color:#facc15;}
.leaflet-tooltip-top.plane-tip:before{border-top-color:rgba(13,20,43,.94);}
.leaflet-tooltip-bottom.plane-tip:before{border-bottom-color:rgba(13,20,43,.94);}
.leaflet-tooltip-left.plane-tip:before{border-left-color:rgba(13,20,43,.94);}
.leaflet-tooltip-right.plane-tip:before{border-right-color:rgba(13,20,43,.94);}
.leaflet-tooltip-top.plane-tip.sel:before{border-top-color:rgba(40,32,6,.95);}
</style>"""


def plane_tip(f, selected):
  """Uçak etiketi: metin çağrı kodu kalır (tıklama eşleştirmesi buna bağlı), görünüm CSS ile."""
  cls = "plane-tip " + ("sel" if selected else {"ARR": "arr", "DEP": "dep", "TRN": "trn"}.get(f["dir"], "arr"))
  return folium.Tooltip(f["label"], sticky=False, direction="top", offset=(0, -20),
                        permanent=bool(selected), class_name=cls)


def legend_html(overflights):
  def pl(color, extra=""):
    return (f"<svg viewBox='0 0 24 24' width='20' height='20' style='{extra}'>"
            f"<path fill='{color}' stroke='#0b1020' stroke-width='.6' d='{PLANE_PATH}'/></svg>")
  items = [
      "<span class='lg'><span class='lgdot'></span>Biz</span>",
      f"<span class='lg'>{pl('#38bdf8')}Gelen</span>",
      f"<span class='lg'>{pl('#fb923c')}Giden</span>",
      f"<span class='lg'>{pl(SEL_COLOR)}Seçili</span>",
  ]
  if overflights:
    items.append(f"<span class='lg'>{pl('#a78bfa')}Geçen</span>")
  items += [
      f"<span class='lg'>{pl('#38bdf8', 'opacity:.45')}Uzakta</span>",
      "<span class='lg'><span class='lgring blue'></span>Görüş alanı</span>",
      "<span class='lg'><span class='lgring grey'></span>Tarama sınırı</span>",
  ]
  return f"<div class='legend'>{''.join(items)}</div>"


class Motion(MacroElement if MacroElement else object):
  """Harita içinde çalışan küçük JS: uçakları hız ve yönlerine göre sürekli kaydırır.
  Sunucuya/OpenSky'ye hiçbir istek atmaz; yeni veri gelince konumlar düzelir."""

  def __init__(self, entries):
    super().__init__()
    self._name = "Motion"
    self.entries = entries
    self.tick = MOTION_TICK_MS
    self.max_age = MOTION_MAX_AGE_S
    self._template = Template(
        "{% macro script(this, kwargs) %}"
        "(function(){"
        "var E=[{{ this.entries }}];var t0=Date.now();"
        "function tick(){var dt=(Date.now()-t0)/1000;"
        "E.forEach(function(e){var a=Math.min(e.age+dt,{{ this.max_age }});var d=e.v*a;"
        "var r=e.trk*Math.PI/180;"
        "e.m.setLatLng([e.lat+d*Math.cos(r)/111.2,"
        "e.lon+d*Math.sin(r)/(111.2*Math.cos(e.lat*Math.PI/180))]);});}"
        "tick();setInterval(tick,{{ this.tick }});"
        "})();"
        "{% endmacro %}")


def build_map(flights, sel_id, cov_km=NEAR_KM, view_km=35, view=None):
  loc = [view["lat"], view["lng"]] if view else [HOME_LAT, HOME_LON]
  m = folium.Map(location=loc, zoom_start=view["zoom"] if view else MAP_ZOOM, tiles=None,
                 control_scale=True)
  m.get_root().html.add_child(folium.Element(
      "<style>.leaflet-control-scale-line:nth-child(2){display:none!important}"
      ".leaflet-control-scale-line{background:rgba(255,255,255,.85)!important}</style>"))
  m.get_root().html.add_child(folium.Element(TIP_CSS))
  folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
  folium.TileLayer("CartoDB dark_matter", name="Koyu harita", show=False).add_to(m)

  dlat = view_km / 111.2
  dlon = view_km / (111.2 * math.cos(math.radians(HOME_LAT)))
  if not view:  # kullanıcı haritayı kaydırmadıysa ilk görünümü sığdır
    m.fit_bounds([[HOME_LAT - dlat, HOME_LON - dlon], [HOME_LAT + dlat, HOME_LON + dlon]])

  folium.Circle([AIRPORT_LAT, AIRPORT_LON], radius=cov_km * 1000, color="#64748b", weight=1,
                dash_array="2 7", fill=False,
                tooltip=f"Tarama sınırı (~{cov_km} km)").add_to(m)

  if CORRIDOR_ON:
    c0 = (AIRPORT_LAT, AIRPORT_LON)
    c1 = dest_point(*c0, CORRIDOR_HEADING, CORRIDOR_LEN_KM)
    pts = [
        dest_point(*c0, CORRIDOR_HEADING - 90, CORRIDOR_HALF_WIDTH_KM),
        dest_point(*c1, CORRIDOR_HEADING - 90, CORRIDOR_HALF_WIDTH_KM),
        dest_point(*c1, CORRIDOR_HEADING + 90, CORRIDOR_HALF_WIDTH_KM),
        dest_point(*c0, CORRIDOR_HEADING + 90, CORRIDOR_HALF_WIDTH_KM),
    ]
    folium.Polygon(pts, color="#7c4dff", weight=1, dash_array="6", fill=True,
                   fill_color="#7c4dff", fill_opacity=0.10,
                   tooltip="Kuzey koridoru (yaklaşık)").add_to(m)

  folium.Circle([HOME_LAT, HOME_LON], radius=CFG["visible_km"] * 1000, color="#3b82f6", weight=1,
                dash_array="4", fill=True, fill_opacity=0.06,
                tooltip=f"Bahçeden görüş alanı (~{CFG['visible_km']:.0f} km)").add_to(m)
  folium.CircleMarker([HOME_LAT, HOME_LON], radius=9, color="#ffffff", weight=2, fill=True,
                      fill_color="#3b82f6", fill_opacity=1,
                      tooltip="🏠 Biz buradayız").add_to(m)
  folium.CircleMarker([AIRPORT_LAT, AIRPORT_LON], radius=5, color="#94a3b8", fill=True,
                      fill_opacity=0.9, tooltip="Eindhoven Havalimanı (EIN)").add_to(m)

  now = time.time()
  entries = []
  for f in flights:
    mk = folium.Marker([f["lat"], f["lon"]], icon=plane_icon(f, f["id"] == sel_id),
                       tooltip=plane_tip(f, f["id"] == sel_id))
    mk.add_to(m)
    if f["speed"] > 60:
      age = min(max(0.0, now - f["tpos"]), MOTION_MAX_AGE_S) if f.get("tpos") else 0.0
      entries.append("{m:%s,lat:%.5f,lon:%.5f,trk:%.1f,v:%.5f,age:%.1f}" % (
          mk.get_name(), f["lat"], f["lon"], f["track"], f["speed"] / 3600.0, age))
  if entries:
    Motion(",".join(entries)).add_to(m)
  folium.LayerControl(collapsed=True).add_to(m)
  return m


# =============================================================================
# YENİ SAYFALARIN HTML PARÇALARI  (giriş, terminal, gözlem defteri)
# =============================================================================
import re  # noqa: E402

PAGES = ["🛰️ Radar", "🛫 Terminal", "📒 Gözlem Defteri"]
DEFAULT_PAGE = PAGES[1]      # açılışta Terminal: veritabanından anında dolar, Radar sekmeye geçince yüklenir
APP_VERSION = "v0.3.13"
CHANGELOG = [
    ("v0.3.13", "Radar önceden ısıtılır: Terminal açıkken trafik/rota/uçak verisi arka planda hazırlanır"),
    ("v0.3.12", "Sürüm izi; havalimanı kodu açıklaması"),
    ("v0.3.11", "Açılışta Terminal; 'Şimdi' görünümü (−60/+30 dk)"),
    ("v0.3.10", "Sürüm değişince tarife otomatik çekilir"),
    ("v0.3.8", "AeroDataBox yeni yanıt biçimi (departure/arrival) desteği"),
    ("v0.3.5", "Modern uçak etiketi"),
    ("v0.3.4", "Kapsama 50/100/200 km"),
    ("v0.3.1", "OpenSky yoksa adsb.lol yedeği"),
]


def secret(name, default=""):
  """secrets.toml / Streamlit Cloud 'Secrets' değeri; yoksa default."""
  try:
    v = st.secrets[name]
  except Exception:
    return default
  return default if v is None else v


def login_card_html():
  return ("<div class='login-card'><div class='big'>🧑‍✈️</div>"
          "<h1>Atlas'ın Uçak Gözlem Kulesi</h1>"
          "<p>Devam etmek için şifreyi gir ✈️</p></div>")


def login_ui(st_, state):
  _, mid, _ = st_.columns([1, 1.15, 1])
  with mid:
    st_.markdown(login_card_html(), unsafe_allow_html=True)
    if state.get("misconfigured"):
      st_.error("Uygulama şifresi tanımlı değil. Streamlit → Settings → Secrets bölümüne "
                "`APP_PASSWORD = \"...\"` ekleyin.")
      return None
    with st_.form("login_form", clear_on_submit=True, border=False):
      pw = st_.text_input("Şifre", type="password", placeholder="Şifre", label_visibility="collapsed")
      sent = st_.form_submit_button("Giriş yap", use_container_width=True)
    if state.get("locked"):
      st_.warning(f"Çok fazla yanlış deneme. {state['locked']} sn sonra tekrar deneyin.")
    elif state.get("error"):
      st_.error(state["error"])
    return pw if sent else None


def _cls(x):
  return re.sub(r"[^A-Za-z0-9]", "", str(x or ""))


def fids_logo_css(logos):
  """Her havayolu logosu sayfada yalnızca bir kez (CSS sınıfı olarak) gömülür."""
  rules = [f".alogo.k-{_cls(k)}{{background-image:url('{v}');}}" for k, v in logos.items() if v]
  return f"<style>{''.join(rules)}</style>" if rules else ""


def airline_key_for(row):
  icao = (row.get("airline_icao") or "").upper()
  key = ALIASES.get(icao, icao)
  if not key:
    num = (row.get("callsign") or "")[:3].upper()
    key = ALIASES.get(num, num) if num.isalpha() else ""
  return key or (row.get("airline_iata") or "")


def fids_logo_cell(row, logos):
  key = airline_key_for(row)
  if logos.get(key):
    return f"<span class='alogo k-{_cls(key)}'></span>"
  _, bg, fg, _i = AIRLINES.get(key, (row.get("airline") or "", "#2b3558", "#ffffff", ""))
  txt = esc((row.get("airline_iata") or key or "?")[:3])
  return f"<span class='alogo txt' style='background:{bg};color:{fg}'>{txt}</span>"


def fids_row_html(r, direction, logos, is_next=False):
  cls = ["frow", "fgrid", "arr" if direction == "ARR" else "dep"]
  if r["status_kind"] == "done":
    cls.append("done")
  if r["status"] in ("canceled", "canceleduncertain"):
    cls.append("canc")
  if is_next:
    cls.append("next")
  eff = f"<small>→ {esc(r['eff_hm'])}</small>" if r["eff_hm"] else ""
  gate = ""
  if direction == "DEP":
    g = r.get("gate")
    gate = f"<div class='c-gate{'' if g else ' na'}'>{esc(g) if g else '–'}</div>"
  code = r.get("other_iata") or r.get("other_icao") or ""
  dl = f"<div class='c-dl {esc(r['delay_kind'])}'>{esc(r['delay_txt']) or '–'}</div>"
  return (f"<div class='{' '.join(cls)}'>"
          f"<div class='c-time'><b>{esc(r['sched_hm'])}</b>{eff}</div>"
          f"<div class='c-fl'>{fids_logo_cell(r, logos)}<div><b>{esc(r['number_disp'])}</b>"
          f"<small>{esc(r.get('airline') or '')}</small></div></div>"
          f"<div class='c-pl'><span class='fg'>{flag(r.get('other_cc'))}</span><div><b>{esc(r['place_disp'])}</b>"
          f"<small>{esc(code)}</small></div></div>"
          f"{gate}"
          f"<div class='c-st'><span class='pill {esc(r['status_kind'])}'>{esc(r['status_label'])}</span></div>"
          f"{dl}</div>")


def fids_panel_html(direction, rows, total, logos, empty_msg):
  arr = direction == "ARR"
  title = "🛬 Varış" if arr else "🛫 Kalkış"
  sub = "Arrivals" if arr else "Departures"
  col1 = "Nereden" if arr else "Nereye"
  gate_h = "" if arr else "<div style='text-align:center'>Kapı</div>"
  cls = "arr" if arr else "dep"
  head = (f"<div class='tphead {cls}'><div class='nm'>{title}<small>{sub}</small></div>"
          f"<div class='ct'>{len(rows)} / {total} uçuş</div></div>")
  if not rows:
    return f"<div class='tpanel'>{head}<div class='tempty'>{empty_msg}</div></div>"
  cols = (f"<div class='fgrid fcols {cls}'><div>Saat</div><div>Uçuş</div><div>{col1}</div>{gate_h}"
          f"<div>Durum</div><div style='text-align:right'>Gecikme</div></div>")
  nxt = next((i for i, r in enumerate(rows) if r["status_kind"] != "done"), None)
  body = "".join(fids_row_html(r, direction, logos, i == nxt) for i, r in enumerate(rows))
  return f"<div class='tpanel'>{head}{cols}{body}</div>"


def term_head_html(now, mode, age_min):
  if mode == "demo":
    pill = "<span class='livepill demo'><i></i>Demo tarife</span>"
  elif age_min is None:
    pill = "<span class='livepill none'><i></i>Veri yok</span>"
  elif age_min <= 180:
    ago = "az önce" if age_min < 2 else f"{age_min} dk önce"
    pill = f"<span class='livepill ok'><i></i>Güncel · {ago}</span>"
  else:
    h = age_min // 60
    pill = f"<span class='livepill old'><i></i>Eski veri · {h} sa önce</span>"
  return (f"<div class='term-head'><div><div class='tt'>Eindhoven Airport<span title='EIN = IATA kodu (yolcu/bilet kodu) · EHEH = ICAO kodu (havacılık/uçuş kontrol kodu)'>EIN · EHEH</span></div>"
          f"<div class='ts'>Varış ve kalkış bilgi ekranı · {now.strftime('%d.%m.%Y')}</div></div>"
          f"<div class='tr'>{pill}<div class='clock'>{now.strftime('%H:%M')}</div></div></div>")


def kpi_html(stats):
  def top(x):
    return f"<span>{esc(x[0])} · {x[1]}×</span>" if x else "<span>henüz yok</span>"
  return ("<div class='kpis'>"
          f"<div class='kpi'><small>Bugün</small><b>{stats['today']}</b><span>görülen uçak</span></div>"
          f"<div class='kpi'><small>Son 7 gün</small><b>{stats['week']}</b><span>görülen uçak</span></div>"
          f"<div class='kpi'><small>Toplam</small><b>{stats['total']}</b><span>{stats['days']} günde</span></div>"
          f"<div class='kpi'><small>En çok görülen</small><b style='font-size:1.15rem;padding-top:8px'>"
          f"{esc(stats['top_airline'][0]) if stats['top_airline'] else '—'}</b>{top(stats['top_type'])}</div>"
          "</div>")


def bars_html(per_day, days):
  mx = max([per_day.get(d, 0) for d in days] + [1])
  names = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
  out = []
  for d in days:
    n = per_day.get(d, 0)
    wd = names[datetime.strptime(d, "%Y-%m-%d").weekday()]
    out.append(f"<div class='bar'><b>{n}</b><i style='height:{max(3, round(n / mx * 70))}px'></i><small>{wd}</small></div>")
  return f"<div class='box'><h4>Son 7 gün</h4><div class='bars'>{''.join(out)}</div></div>"


def sighting_html(r):
  d = {"ARR": "<span class='badge arr'>GELİŞ ⬇</span>", "DEP": "<span class='badge dep'>KALKIŞ ⬆</span>",
       "TRN": "<span class='badge trn'>GEÇİŞ ➡</span>"}.get(r.get("direction"), "")
  route = " → ".join(x for x in (r.get("origin_iata"), r.get("dest_iata")) if x) or "rota ?"
  when = (r.get("last_seen") or "")[:16].replace("T", " ")
  extra = " · ".join(x for x in (r.get("type_name"), r.get("reg")) if x)
  dist = f" · en yakın {r['min_dist_km']:.1f} km" if r.get("min_dist_km") is not None else ""
  return (f"<div class='sight'>{d}<div class='sd'><b>{esc(r.get('callsign') or r.get('icao24'))}</b> "
          f"· {esc(r.get('airline') or '')}<small>{esc(route)} · {esc(extra)}{dist}</small></div>"
          f"<div class='tm'>{esc(when[5:])}</div></div>")


def sync_text(sync, now_ts):
  if sync["mode"] == "local":
    return ("💾 Yerel kayıt (GitHub bağlı değil). Streamlit Cloud yeniden başladığında bu kayıtlar silinir; "
            "kalıcı olması için secrets içine GITHUB_TOKEN ekleyin.")
  if sync["error"]:
    return f"⚠️ GitHub `{esc(sync['branch'])}` dalı: {esc(sync['error'])}"
  if sync["last_ok"]:
    mins = max(0, int((now_ts - sync["last_ok"]) // 60))
    return f"☁️ GitHub `{esc(sync['branch'])}` dalına son yedek {mins} dk önce" + (" · bekleyen değişiklik var" if sync["dirty"] else "")
  return f"☁️ GitHub `{esc(sync['branch'])}` dalı bağlı · henüz yedek alınmadı" + (" (bekleyen değişiklik var)" if sync["dirty"] else "")


# =============================================================================
# ANA UYGULAMA
# =============================================================================


def select_flight(fid):
  """'İncele' düğmesi: uçağı seç ve haritayı yeni anahtarla çiz (eski tıklama değeri silinsin)."""
  st.session_state["sel"] = fid
  st.session_state["_map_gen"] = st.session_state.get("_map_gen", 0) + 1


def keep(defaults):
  """Sayfalar arası geçişte, ekrandan kalkan bileşenlerin değerini korur (Streamlit onları siler)."""
  ss = st.session_state
  for k, d in defaults.items():
    if k not in ss:
      ss[k] = ss.get("_p_" + k, d)


def remember(keys):
  ss = st.session_state
  for k in keys:
    if k in ss:
      ss["_p_" + k] = ss[k]


def apply_home_override():
  """Depo herkese açıksa ev konumunu kodda değil secrets içinde tutabilirsin."""
  global HOME_LAT, HOME_LON
  try:
    lat, lon = float(secret("HOME_LAT", "")), float(secret("HOME_LON", ""))
  except (TypeError, ValueError):
    return
  if -90 <= lat <= 90 and -180 <= lon <= 180:
    HOME_LAT, HOME_LON = lat, lon


@st.cache_resource(show_spinner=False)
def get_db():
  """Tek veritabanı nesnesi (tüm oturumlar için). İlk çağrıda `data` dalından çeker."""
  return radar_db.open_db(lambda k, d="": str(secret(k, d)))


def page_radar(db, store, demo, refresh_s_box):
  ss = st.session_state
  keep({"f_over": False, "f_cov": list(COVERAGE)[0], "f_visk": VISIBLE_KM, "f_visa": VISIBLE_ALT_FT,
        "f_ovk": OVERFLIGHT_KM, "f_unk": False, "f_view": "Hepsi", "f_q": ""})
  auth = "auth" if get_bearer() else "anon"
  active = ss.get("_active", False)
  refresh_s = (REFRESH_ACTIVE if active else REFRESH_IDLE)[auth]
  refresh_s_box.append(refresh_s)

  ss.setdefault("sel", None)
  ss.setdefault("_map_gen", 0)

  tm = {}
  t_page = time.time()

  # Yerleşim iskeleti (kod sırasından bağımsız, ekrandaki sırayı belirler)
  c_top = st.container()
  c_next = st.container()
  c_main = st.container()
  c_strip = st.container()

  # --- Filtre / arama / seçenekler ---
  with c_strip:
   with st.container(key="toolbar"):
    f1, f2, f3, f4, f5 = st.columns([2.6, 3.2, 2.1, 1.7, 0.6], vertical_alignment="center")
    with f3:
      overflights = st.toggle("Üstümüzden geçenler", key="f_over",
                              help="Yüksekte (10.000 ft üstü) evimizin yakınından geçen uçaklar; haritada mor.")
    with f4:
      if ss["f_cov"] not in COVERAGE:
        ss["f_cov"] = list(COVERAGE)[0]
      cov_label = st.selectbox("Kapsama", list(COVERAGE), key="f_cov", label_visibility="collapsed",
                               help="Tarama alanı. Geniş seçeneklerde Eindhoven'a inmek üzere alçalan "
                                    "uçaklar uzaktan görünür.")
    with f5:
      with st.popover("⚙️"):
        vis_km = st.slider("Görüş yarıçapı (km)", 2.0, 10.0, step=0.5, key="f_visk",
                           help="Bu mesafedeki uçaklar 'bahçeden görünür' sayılır.")
        vis_alt = st.slider("Görünür irtifa (ft)", 2000, 10000, step=500, key="f_visa")
        ovf_km = st.slider("Geçiş mesafesi (km)", 5, 80, step=5, key="f_ovk",
                           help="'Üstümüzden geçenler' açıkken evden bu mesafedeki uçaklar gösterilir. "
                                "Küçük değer = sadece tam tepemizden geçenler.")
        show_unknown = st.toggle("Rotası bilinmeyenleri de göster", key="f_unk",
                                 help="Kapalıyken rotası (nereden–nereye) bulunamayan uçaklar listede ve "
                                      "haritada gösterilmez.")
    with f1:
      views = ["Hepsi", "Varış", "Kalkış"] + (["Geçiş"] if overflights else [])
      if ss["f_view"] not in views:
        ss["f_view"] = "Hepsi"
      view = st.radio("Filtre", views, horizontal=True, key="f_view", label_visibility="collapsed")
    with f2:
      query = st.text_input("Ara", key="f_q", placeholder="🔍 Ara: HV6710, Transavia, Athens, 737, PH-HXK...",
                            label_visibility="collapsed")
  remember(["f_over", "f_cov", "f_visk", "f_visa", "f_ovk", "f_unk", "f_view", "f_q"])
  CFG["visible_km"], CFG["visible_alt"], CFG["overflight_km"] = vis_km, vis_alt, ovf_km
  cov_km, view_km = COVERAGE[cov_label]

  # --- Veri ---
  weather = fetch_weather()
  wind_dir = weather.get("wind_dir") if weather else None
  bstats = {"hidden_unknown": 0}
  if demo:
    all_flights = attach_logos(demo_flights(overflights), store)
    status, fetched, mode, raw_n = "ok", time.time(), "demo", len(all_flights)
    runway = {"rwy": "21", "source": "demo", "n": 0}
  else:
    fetch_km = max(cov_km, ovf_km + 12) if overflights else cov_km  # ev havalimanından ~9 km uzakta
    t1 = time.time()
    states, status, fetched = fetch_states(get_bearer(), fetch_km,
                                           allow_stale=bool(ss.get("_switched")))
    tm["veri"] = time.time() - t1
    raw_n = len(states)
    t1 = time.time()
    all_flights = attach_logos(
        build_flights(states, store, overflights, cov_km, show_unknown, bstats), store)
    tm["uçaklar"] = time.time() - t1
    mode = "live" if status == "ok" else "err"
    runway = infer_runway(states, wind_dir)
  updated = datetime.fromtimestamp(fetched, TZ).strftime("%H:%M:%S")

  # Bahçeden görünen uçakları Gözlem Defteri'ne yaz (demo hariç)
  if not demo and status == "ok":
    try:
      day = datetime.now(TZ).strftime("%Y-%m-%d")
      items = []
      for f in all_flights:
        if f["visible"] and f.get("route_known"):
          o, d = f["origin"], f["dest"]
          items.append({
              "day": day, "icao24": f["id"], "callsign": f["callsign"], "airline": f["airline"],
              "airline_key": f["airline_key"], "airline_iata": f["airline_iata"],
              "type_code": f["type_code"], "type_name": f["type_name"], "reg": f["reg"],
              "direction": f["dir"], "origin_iata": o["iata"] if o else None,
              "origin_city": o["city"] if o else None, "dest_iata": d["iata"] if d else None,
              "dest_city": d["city"] if d else None, "dist_km": round(f["dist_home"], 2),
              "alt_ft": f["alt_ft"]})
      if items:
        db.record_sightings(items, datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S"))
    except Exception:  # defter hatası radarı asla durdurmasın
      pass

  # Yaklaşan (≤25 km, alçak) uçak varsa bir sonraki turda daha sık yenile
  ss["_active"] = any(
      f["approaching"] and f["dist_home"] <= 25 and f["alt_ft"] <= MAX_SHOW_ALT_FT
      for f in all_flights)

  # Kart sırası: önce bahçeden görünenler, sonra en yakın gelecekler
  flights = sorted(all_flights, key=lambda f: (
      not f["visible"], f["eta_min"] if f["eta_min"] is not None else 99, f["dist_home"]))
  if view == "Varış":
    flights = [f for f in flights if f["dir"] == "ARR"]
  elif view == "Kalkış":
    flights = [f for f in flights if f["dir"] == "DEP"]
  elif view == "Geçiş":
    flights = [f for f in flights if f["dir"] == "TRN"]
  if query.strip():
    q = query.strip().lower()

    def hit(f):
      parts = [f["callsign"], f["airline"], f["type_name"], f["type_code"], f["reg"],
               f["airline_iata"]]
      cs = f["callsign"]
      if f["airline_iata"] and cs[:3].isalpha() and len(cs) > 3:
        parts.append(f["airline_iata"] + cs[3:])  # TRA6710 -> HV6710
      for a in (f["origin"], f["dest"]):
        if a:
          parts += [a["iata"], a["city"]]
      return any(q in str(p).lower() for p in parts)

    flights = [f for f in flights if hit(f)]

  counts = {
      "total": len(flights),
      "arr": sum(f["dir"] == "ARR" for f in flights),
      "dep": sum(f["dir"] == "DEP" for f in flights),
      "trn": sum(f["dir"] == "TRN" for f in flights),
      "vis": sum(f["visible"] for f in flights),
      "raw": raw_n,
      "hidden": bstats["hidden_unknown"],
      "refresh": refresh_s,
  }

  # --- Seçili uçağı belirle ---
  ids = [f["id"] for f in flights]
  if ss["sel"] not in ids:
    vis_first = [f for f in flights if f["visible"]] or flights
    ss["sel"] = vis_first[0]["id"] if vis_first else None

  # --- Üst bar + sıradaki uçak ---
  with c_top:
    st.markdown(topbar_html(weather, datetime.now(TZ), counts, mode, status),
                unsafe_allow_html=True)
  with c_next:
    n1, n2 = st.columns([1.15, 1])
    with n1:
      st.markdown(next_banner_html(flights, updated), unsafe_allow_html=True)
    with n2:
      st.markdown(runway_html(runway), unsafe_allow_html=True)

  # --- Harita + detay paneli ---
  with c_main:
    col_map, col_panel = st.columns([2.2, 1])
    with col_map:
      t1 = time.time()
      m = build_map(flights, ss["sel"], cov_km, view_km)
      tm["harita"] = time.time() - t1
      out = st_folium(m, height=MAP_HEIGHT, use_container_width=True,
                      returned_objects=["last_object_clicked_tooltip"],
                      key=f"radar_map_{ss['_map_gen']}")
      clicked = ((out or {}).get("last_object_clicked_tooltip") or "").strip()
      hit_f = next((f for f in flights if f["label"] == clicked), None) if clicked else None
      if hit_f:
        ss["sel"] = hit_f["id"]
        ss["_map_gen"] += 1  # eski tıklamayı unut, haritayı seçili renkle yeniden çiz
        st.rerun()
      st.markdown(legend_html(overflights), unsafe_allow_html=True)
    with col_panel:
      selected = next((f for f in flights if f["id"] == ss["sel"]), None)
      if selected and not selected["photo"] and not demo:  # fotoğraf yoksa yedek kaynak
        ph = lookup_photo(selected["id"], store)
        if ph:
          selected = {**selected, "photo": ph["src"], "photo_credit": ph.get("credit", "")}
      st.markdown(detail_html(selected), unsafe_allow_html=True)

  # --- Kart şeridi ---
  with c_strip:
    if flights:
      per_row = 4
      shown = flights[:12]
      for i in range(0, len(shown), per_row):
        cols = st.columns(per_row)
        for col, f in zip(cols, shown[i:i + per_row]):
          with col:
            st.markdown(card_html(f, f["id"] == ss["sel"]), unsafe_allow_html=True)
            st.button("İncele", key=f"btn_{f['id']}", on_click=select_flight,
                      args=(f["id"],), use_container_width=True)
    else:
      hid = counts["hidden"]
      extra = (f" Rotası bilinmediği için {hid} uçak gizlendi (⚙️ menüsünden gösterebilirsin)." if hid else "")
      st.info("Şu an listelenecek uçak yok." + extra + " Arayüzü denemek için üstteki “Demo modu”nu aç.")

    st.markdown(
        f"<div class='foot'>Uçak konumu: {esc(_SRC['last_source'] or 'OpenSky Network / adsb.lol')} · adsbdb · Open-Meteo · "
        "Harita: © OpenStreetMap katkıcıları, © CARTO · Rota/tür bilgisi bazı uçaklarda eksik olabilir."
        f" · ⏱ {' · '.join(f'{k} {v:.1f}' for k, v in tm.items())} · toplam {time.time() - t_page:.1f} sn</div>",
        unsafe_allow_html=True,
    )
  if any(k and k[0] == "logo" for k in list(_BG["logo"])):   # logolar iniyor: kısa süre sonra yenile
    refresh_s_box[-1] = min(refresh_s_box[-1], 5)


def _more_rows():
  st.session_state["fids_n"] = min(60, st.session_state.get("fids_n", 20) + 10)



def page_terminal(db, store, demo, refresh_s_box):
  ss = st.session_state
  refresh_s_box.append(60)
  keep({"fids_q": "", "fids_n": 20})
  now = fids.now_local()
  key = str(secret("AERODATABOX_KEY", "")).strip()
  host = str(secret("AERODATABOX_HOST", "")).strip() or fids.ADB_HOST
  try:
    monthly = int(float(secret("ADB_MONTHLY_UNITS", fids.DEFAULT_MONTHLY_UNITS)))
  except (TypeError, ValueError):
    monthly = fids.DEFAULT_MONTHLY_UNITS

  t0 = time.time()
  if not demo and key and db.meta_get("fids_parser") != APP_VERSION:
    db.meta_set(fids_parser=APP_VERSION)
    if not db.fids_between("DEP", fids.to_iso(now - timedelta(hours=1)), fids.to_iso(now + timedelta(hours=12))):
      with st.spinner("Tarife yeni biçimle çekiliyor…"):
        fids.refresh(db, key, now, host=host, monthly_units=monthly, force=True)
      db.maybe_push()
  if not demo and key:
    bs0 = fids.budget_state(db, now, monthly)
    due, _why = fids.due_for_refresh(db, now, bs0)
    if due:
      if fids.data_age_min(db, now) is None:      # hiç veri yok: ilk seferde bekle
        with st.spinner("Tarife yükleniyor…"):
          fids.refresh(db, key, now, host=host, monthly_units=monthly)
        db.maybe_push()
      else:                                      # veri var: arka planda güncelle, ekranı bekletme
        def _bg():
          fids.refresh(db, key, fids.now_local(), host=host, monthly_units=monthly)
          db.maybe_push()
        _spawn(_bg)

  q1, q2 = st.columns([3, 1.2], vertical_alignment="center")
  with q2:
    if not demo and key and st.button("🔄 Tarifeyi yenile", key="fids_force", use_container_width=True,
                                       help="Tarifeyi hemen çeker (2 kota birimi harcar)."):
      with st.spinner("Tarife çekiliyor…"):
        _r = fids.refresh(db, key, now, host=host, monthly_units=monthly, force=True)
      db.maybe_push()
      ss["fids_force_msg"] = (f"Çekme sonucu: {'başarılı' if _r.get('fetched') else 'veri alınamadı'} · "
                              f"neden: {_r.get('reason') or '-'} · çağrı: {_r.get('calls', 0)}"
                              + (f" · hata: {_r['error']}" if _r.get("error") else ""))
  with q1:
    query = st.text_input("Ara", key="fids_q", label_visibility="collapsed",
                          placeholder="🔍 Uçuş no, havayolu, şehir, kapı: HV5101, Ryanair, Malaga, B3...")
  limit = int(ss.get("fids_n", 20))
  keep({"fids_view": "Şimdi"})
  view = st.radio("Görünüm", ["Şimdi", "Tüm gün"], key="fids_view", horizontal=True, label_visibility="collapsed",
                  help="Şimdi: inenler/kalkanlar (son 60 dk), inmekte/kalkmakta olanlar ve önümüzdeki 30 dk.")
  remember(["fids_q", "fids_n", "fids_view"])
  win = (60, 30) if view == "Şimdi" else None

  res = {"error": "" if demo else (db.meta_get("fids_last_error") or "")}
  if demo:
    mode, age = "demo", None
    dep, dep_total = fids.select_demo("DEP", now, limit, query)
    arr, arr_total = fids.select_demo("ARR", now, limit, query)
  else:
    mode, age = "live", fids.data_age_min(db, now)
    dep, dep_total = fids.select_board(db, "DEP", now, limit, query=query, window=win)
    arr, arr_total = fids.select_board(db, "ARR", now, limit, query=query, window=win)

  # Logolar: beklemeden (önbellekte olanlar hemen, olmayanlar arka planda indirilir)
  pairs = sorted({(airline_key_for(r), r.get("airline_iata") or "") for r in dep + arr} - {("", "")})
  logos, pending = {}, False
  for k_, i_ in pairs:
    v, p_ = peek_logo(k_, i_, store)
    logos[k_] = v
    pending = pending or p_
  if pending:
    refresh_s_box[-1] = 5      # logolar gelince hemen göster (sonra 60 sn'ye döner)

  st.markdown(fids_logo_css(logos) + term_head_html(now, mode, age), unsafe_allow_html=True)

  if not demo and not key and not (dep or arr):
    empty = ("<div class='big'>🔑</div>Tarife verisi için ücretsiz bir AeroDataBox anahtarı gerekiyor.<br>"
             "Streamlit Secrets içine <b>AERODATABOX_KEY</b> ekleyin (RapidAPI → AeroDataBox → Basic plan).<br>"
             "Arayüzü denemek için üstteki <b>Demo modu</b>nu açabilirsiniz.")
  elif not demo and query.strip():
    empty = "<div class='big'>🔍</div>Aramanızla eşleşen uçuş yok."
  elif not demo:
    empty = ("<div class='big'>🛩️</div>Önümüzdeki saatler için kayıtlı uçuş yok."
             + (f"<br><small>{esc(res['error'])}</small>" if res.get("error") else ""))
  else:
    empty = "<div class='big'>🔍</div>Aramanızla eşleşen uçuş yok."

  cA, cD = st.columns(2)
  with cA:
    st.markdown(fids_panel_html("ARR", arr, arr_total, logos, empty), unsafe_allow_html=True)
  with cD:
    st.markdown(fids_panel_html("DEP", dep, dep_total, logos, empty), unsafe_allow_html=True)

  if max(arr_total, dep_total) > limit and limit < 60:
    b1, b2, b3 = st.columns([1, 1, 1])
    with b2:
      st.button("Daha fazla göster (+10)", on_click=_more_rows, use_container_width=True, key="fids_more")

  if res.get("error") and not demo:
    st.markdown(f"<div class='tnote warn'>⚠️ Tarife güncellenemedi: {esc(res['error'])} "
                "· Son kayıtlı veri gösteriliyor.</div>", unsafe_allow_html=True)
  if not demo and key:
    with st.popover("🛠 Tanı"):
      st.markdown(f"**Sürüm:** {APP_VERSION}")
      if ss.get("fids_force_msg"):
        st.markdown(f"**Son düğme basışı:** {ss['fids_force_msg']}")
      st.markdown("**Son tarife çekme:**")
      st.code(db.meta_get("fids_last_diag") or "henüz çekilmedi", language=None)
      st.caption("Bu metin yalnızca yanıtın yapısını içerir (anahtar/şifre içermez).")
  if demo:
    foot = "Demo tarifesi örnek verilerdir; gerçek uçuşları göstermez."
  else:
    bs = fids.budget_state(db, now, monthly)
    foot = (f"Tarife: AeroDataBox · bu ay {bs['used']}/{bs['cap']} kota birimi kullanıldı · "
            f"yaklaşık {bs['interval_h']:.1f} saatte bir yenilenir")
  st.markdown(f"<div class='foot'>{esc(foot)} · Saatler Hollanda saatidir. Gecikme = planlanan ile "
              f"tahmini/gerçekleşen saat farkı. · sayfa {time.time() - t0:.1f} sn</div>", unsafe_allow_html=True)


def _backup_now():
  st.session_state["_backup_req"] = True


def page_diary(db, store, demo, refresh_s_box):
  ss = st.session_state
  refresh_s_box.append(120)
  now = datetime.now(TZ)
  today = now.strftime("%Y-%m-%d")
  days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
  stats = db.sighting_stats(today, days[0])
  st.markdown("<div class='term-head'><div><div class='tt'>📒 Gözlem Defteri</div>"
              "<div class='ts'>Bahçeden görülen uçaklar otomatik kaydedilir</div></div></div>",
              unsafe_allow_html=True)
  st.markdown(kpi_html(stats), unsafe_allow_html=True)
  cL, cR = st.columns([1.5, 1])
  with cL:
    recent = db.recent_sightings(30)
    if recent:
      st.markdown("".join(sighting_html(r) for r in recent), unsafe_allow_html=True)
    else:
      st.markdown("<div class='box'><div class='tempty'><div class='big'>🔭</div>"
                  "Henüz kayıt yok. Bahçeden görünür bir uçak geçince burada listelenir.</div></div>",
                  unsafe_allow_html=True)
  with cR:
    st.markdown(bars_html(stats["per_day"], days), unsafe_allow_html=True)
    sync = db.sync_status()
    st.markdown(f"<div class='box'><h4>Veritabanı</h4><div style='font-size:.82rem;color:#cdd5ea'>"
                f"{sync_text(sync, time.time())}</div></div>", unsafe_allow_html=True)
    if sync["mode"] == "github":
      st.button("☁️ Şimdi yedekle", on_click=_backup_now, use_container_width=True, key="backup_btn")
      if ss.pop("_backup_req", False):
        db.maybe_push(force=True, wait=True)
        st.rerun()


def main():
  st.set_page_config(page_title="Atlas'ın Uçak Gözlem Kulesi", page_icon="🧑‍✈️", layout="wide")
  st.markdown(CSS, unsafe_allow_html=True)

  # 1) Şifre kapısı: giriş yapılmadan hiçbir veri/API çağrısı ve otomatik yenileme başlamaz
  if not radar_auth.gate(st, secret, login_ui=login_ui):
    st.stop()

  if folium is None or st_folium is None:
    st.error("Eksik paket: `pip install folium streamlit-folium`")
    st.stop()
  apply_home_override()
  db = get_db()
  db.maybe_push()
  store = get_store()

  # 2) Gezinme
  keep({"page": DEFAULT_PAGE, "demo": False})
  with st.container(key="nav"):
    n1, n2, n3 = st.columns([5, 1.5, 1], vertical_alignment="center")
    with n1:
      if st.session_state["page"] not in PAGES:
        st.session_state["page"] = DEFAULT_PAGE
      page = st.radio("Sayfa", PAGES, horizontal=True, key="page", label_visibility="collapsed")
    with n2:
      demo = st.toggle("Demo modu", key="demo", help="Gece uçak yokken arayüzü denemek için örnek veri.")
    with n3:
      if st.button("Çıkış", use_container_width=True, key="logout_btn"):
        radar_auth.logout(st)
        st.rerun()
  remember(["page", "demo"])

  # 3) Sayfa
  st.session_state["_switched"] = st.session_state.get("_last_page") != page
  st.session_state["_last_page"] = page
  box = []
  if page != PAGES[0] and not demo:
    _cov = st.session_state.get("f_cov")
    warm_radar(store, get_bearer(), COVERAGE[_cov if _cov in COVERAGE else list(COVERAGE)[0]][0])
  fn = {PAGES[0]: page_radar, PAGES[1]: page_terminal, PAGES[2]: page_diary}[page]
  fn(db, store, demo, box)

  with st.popover(f"ℹ️ {APP_VERSION}"):
    st.markdown("**Sürüm geçmişi**")
    for v_, t_ in CHANGELOG:
      st.markdown(f"- **{v_}** · {t_}")

  # 4) Otomatik yenileme (sayfaya göre; en sonda ki sayfa hatası yenilemeyi engellemesin diye değil,
  #    sayfanın kendi aralığı belli olduktan sonra kurulur)
  if st_autorefresh is not None and box:
    st_autorefresh(interval=box[0] * 1000, key=f"refresh_{PAGES.index(page)}")


if __name__ == "__main__":
  main()
