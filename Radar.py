"""
Eindhoven Kuzey Koridoru Uçak Radarı  (v0.2 - tek ekran, harita merkezli)

Kurulum:
    pip install streamlit requests folium streamlit-folium streamlit-autorefresh
Çalıştırma:
    streamlit run Radar.py

Opsiyonel:
  * assets/logos/<KOD>.png|svg|webp  -> havayolu logoları (TRA.png, RYR.svg, WZZ.png, TUI.png ...)
  * .streamlit/secrets.toml          -> OpenSky hesabın varsa günlük sorgu limiti artar:
        opensky_client_id = "..."
        opensky_client_secret = "..."
"""

import base64
import html
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import streamlit as st

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

HOME_LAT, HOME_LON = 51.4951, 5.4779  # Panorama (5629 TT) civarı; ekranda adres yazmaz
AIRPORT_LAT, AIRPORT_LON = 51.4501, 5.3743  # Eindhoven Havalimanı
AIRPORT_ICAO = "EHEH"

# OpenSky sorgu kutusu (havalimanı + kuzey koridoru + ev çevresi)
NEAR_KM = 45  # havalimanına bu kadar yakın alçak uçaklar her zaman gösterilir
OVERFLIGHT_KM = 30  # "Üstümüzden geçenler": evden bu kadar yakın yüksek uçaklar
INBOUND_MAX_ALT_FT = 25000  # uzaktan gelen (EIN'e alçalan) uçaklar için irtifa sınırı
# Kapsama seçenekleri: etiket -> (tarama yarıçapı km, haritanın gösterdiği yarıçap km)
# Not: OpenSky'de 25 derece-kareden küçük sorgu 1 kredi harcar; 200 km hâlâ bunun altında.
COVERAGE = {
    "📡 Yakın · 45 km": (45, 35),
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
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;margin:8px 0 22px;padding:6px 12px;
  background:var(--card);border:1px solid var(--line);border-radius:12px;font-size:.78rem;color:#cdd5ea;}
.lg{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;}
.lgdot{width:12px;height:12px;border-radius:50%;background:#3b82f6;border:2px solid #fff;display:inline-block;}
.lgring{width:16px;height:16px;border-radius:50%;display:inline-block;box-sizing:border-box;}
.lgring.blue{border:1.5px dashed #3b82f6;background:rgba(59,130,246,.12);}
.lgring.grey{border:1.5px dotted #94a3b8;}
.foot{text-align:center;color:#5d6a8c;font-size:.72rem;margin-top:16px;}
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
  try:
    cid = st.secrets["opensky_client_id"]
    sec = st.secrets["opensky_client_secret"]
  except Exception:
    return ""
  try:
    return _opensky_token(cid, sec)
  except Exception:
    return ""


def bbox_for(radius_km):
  """Havalimanı merkezli kare sorgu kutusu."""
  dlat = radius_km / 111.2
  dlon = radius_km / (111.2 * math.cos(math.radians(AIRPORT_LAT)))
  return {"lamin": round(AIRPORT_LAT - dlat, 3), "lamax": round(AIRPORT_LAT + dlat, 3),
          "lomin": round(AIRPORT_LON - dlon, 3), "lomax": round(AIRPORT_LON + dlon, 3)}


@st.cache_data(ttl=FETCH_TTL, show_spinner=False)
def fetch_states(bearer, radius_km=NEAR_KM):
  """(states, durum_mesajı, epoch) döndürür. Hata olsa da uygulama çökmez."""
  headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
  try:
    r = requests.get(OPENSKY_URL, params=bbox_for(radius_km + 10), headers=headers, timeout=7)
  except requests.RequestException:
    return [], "OpenSky'ye ulaşılamıyor", time.time()
  if r.status_code == 429:
    return [], "OpenSky günlük sorgu sınırı doldu", time.time()
  if r.status_code != 200:
    return [], f"OpenSky hata kodu {r.status_code}", time.time()
  try:
    return r.json().get("states") or [], "ok", time.time()
  except ValueError:
    return [], "OpenSky yanıtı okunamadı", time.time()


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
  store[key] = (now + (ttl_ok if val else ttl_fail), val)
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


def lookup_route(callsign, store):
  """adsbdb: çağrı kodundan rota (kalkış/varış, havayolu)."""
  def go():
    j = _get_json(f"{ADSBDB}/callsign/{callsign}") or {}
    resp = j.get("response")
    return (resp.get("flightroute") or {}) if isinstance(resp, dict) else {}
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
    near    : havalimanına 45 km içinde, 10.000 ft altı
    transit : (seçenek açıksa) evden 30 km içinde, yüksekte geçenler
    inbound : 45 km dışında ama EIN'e doğru alçalanlar (kapsama genişse)
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


def build_flights(states, store, overflights=False, coverage_km=NEAR_KM):
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
    ac = acs.get(icao24) or {}
    prefix = callsign[:3].upper() if callsign[:3].isalpha() else ""
    akey, aname, aiata = resolve_airline(prefix, route, ac)
    origin = airport_view(route.get("origin"))
    dest = airport_view(route.get("destination"))
    to_ein = bool(dest and dest["icao"] == AIRPORT_ICAO)
    from_ein = bool(origin and origin["icao"] == AIRPORT_ICAO)

    # Uzaktan gelenler yalnızca EIN'e iniyorsa tutulur
    if kind == "inbound" and not (to_ein or (not route and d_air <= 80)):
      continue

    vrate = s[11] or 0
    if to_ein:
      direction = "ARR"
    elif from_ein:
      direction = "DEP"
    elif route or kind == "transit":  # rotası bilinen ve EIN ile ilgisi olmayan
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
    }
    flights.append(enrich_geometry(f))
  return flights


def attach_logos(flights, store):
  """Her havayolu için logoyu (yerel dosya ya da internetten) bir kez getirir."""
  keys = sorted({(f["airline_key"], f["airline_iata"]) for f in flights
                 if f["airline_key"] or f["airline_iata"]})
  with ThreadPoolExecutor(ENRICH_WORKERS) as pool:
    logos = dict(zip(keys, pool.map(lambda k: fetch_logo(k[0], k[1], store), keys)))
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
    return "Rota bilinmiyor"
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
  return f"""
  <div class='topbar'>
    <div class='brand'>🧑‍✈️ Atlas'ın Uçak Gözlem Kulesi ✈️<small>Blixembosch bahçesinden Eindhoven gökyüzü · bugün hangi uçaklar geçiyor? 🔭</small></div>
    <div class='chips'>
      {warn}{w}
      <span class='chip'>✈ <b>{counts['total']}</b> uçak · ⬇ {counts['arr']} · ⬆ {counts['dep']}{trn} · 👀 {counts['vis']}</span>
      <span class='chip' title='Tarama alanındaki toplam uçak (filtre öncesi)'>📡 <b>{counts['raw']}</b></span>
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
                       tooltip=folium.Tooltip(f["label"]))
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
# ANA UYGULAMA
# =============================================================================


def select_flight(fid):
  """'İncele' düğmesi: uçağı seç ve haritayı yeni anahtarla çiz (eski tıklama değeri silinsin)."""
  st.session_state["sel"] = fid
  st.session_state["_map_gen"] = st.session_state.get("_map_gen", 0) + 1


def main():
  st.set_page_config(page_title="Atlas'ın Uçak Gözlem Kulesi", page_icon="🧑‍✈️", layout="wide")
  st.markdown(CSS, unsafe_allow_html=True)

  if folium is None or st_folium is None:
    st.error("Eksik paket: `pip install folium streamlit-folium`")
    st.stop()
  auth = "auth" if get_bearer() else "anon"
  active = st.session_state.get("_active", False)
  refresh_s = (REFRESH_ACTIVE if active else REFRESH_IDLE)[auth]
  if st_autorefresh is not None:
    st_autorefresh(interval=refresh_s * 1000, key="radar_refresh")

  st.session_state.setdefault("sel", None)
  st.session_state.setdefault("_map_gen", 0)

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
      overflights = st.toggle("Üstümüzden geçenler", value=False,
                              help="Yüksekte (10.000 ft üstü) evimizin yakınından geçen uçaklar; haritada mor.")
    with f4:
      cov_label = st.selectbox("Kapsama", list(COVERAGE), index=0, label_visibility="collapsed",
                               help="Tarama alanı. Geniş seçeneklerde Eindhoven'a inmek üzere alçalan "
                                    "uçaklar uzaktan görünür.")
    with f5:
      with st.popover("⚙️"):
        vis_km = st.slider("Görüş yarıçapı (km)", 2.0, 10.0, VISIBLE_KM, 0.5,
                           help="Bu mesafedeki uçaklar 'bahçeden görünür' sayılır.")
        vis_alt = st.slider("Görünür irtifa (ft)", 2000, 10000, VISIBLE_ALT_FT, 500)
        ovf_km = st.slider("Geçiş mesafesi (km)", 5, 80, OVERFLIGHT_KM, 5,
                           help="'Üstümüzden geçenler' açıkken evden bu mesafedeki uçaklar gösterilir. "
                                "Küçük değer = sadece tam tepemizden geçenler.")
        demo = st.toggle("Demo modu", value=False, help="Gece uçak yokken arayüzü denemek için.")
    with f1:
      views = ["Hepsi", "Varış", "Kalkış"] + (["Geçiş"] if overflights else [])
      view = st.radio("Filtre", views, horizontal=True, label_visibility="collapsed")
    with f2:
      query = st.text_input("Ara", placeholder="🔍 Ara: HV6710, Transavia, Athens, 737, PH-HXK...",
                            label_visibility="collapsed")
  CFG["visible_km"], CFG["visible_alt"], CFG["overflight_km"] = vis_km, vis_alt, ovf_km
  cov_km, view_km = COVERAGE[cov_label]

  # --- Veri ---
  store = get_store()
  weather = fetch_weather()
  wind_dir = weather.get("wind_dir") if weather else None
  if demo:
    all_flights = attach_logos(demo_flights(overflights), store)
    status, fetched, mode, raw_n = "ok", time.time(), "demo", len(all_flights)
    runway = {"rwy": "21", "source": "demo", "n": 0}
  else:
    fetch_km = max(cov_km, ovf_km + 12) if overflights else cov_km  # ev havalimanından ~9 km uzakta
    states, status, fetched = fetch_states(get_bearer(), fetch_km)
    raw_n = len(states)
    all_flights = attach_logos(build_flights(states, store, overflights, cov_km), store)
    mode = "live" if status == "ok" else "err"
    runway = infer_runway(states, wind_dir)
  updated = datetime.fromtimestamp(fetched, TZ).strftime("%H:%M:%S")

  # Yaklaşan (≤25 km, alçak) uçak varsa bir sonraki turda daha sık yenile
  st.session_state["_active"] = any(
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
      "refresh": refresh_s,
  }

  # --- Seçili uçağı belirle ---
  ids = [f["id"] for f in flights]
  if st.session_state["sel"] not in ids:
    vis_first = [f for f in flights if f["visible"]] or flights
    st.session_state["sel"] = vis_first[0]["id"] if vis_first else None

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
      m = build_map(flights, st.session_state["sel"], cov_km, view_km)
      out = st_folium(m, height=MAP_HEIGHT, use_container_width=True,
                      returned_objects=["last_object_clicked_tooltip"],
                      key=f"radar_map_{st.session_state['_map_gen']}")
      clicked = ((out or {}).get("last_object_clicked_tooltip") or "").strip()
      hit_f = next((f for f in flights if f["label"] == clicked), None) if clicked else None
      if hit_f:
        st.session_state["sel"] = hit_f["id"]
        st.session_state["_map_gen"] += 1  # eski tıklamayı unut, haritayı seçili renkle yeniden çiz
        st.rerun()
      st.markdown(legend_html(overflights), unsafe_allow_html=True)
    with col_panel:
      selected = next((f for f in flights if f["id"] == st.session_state["sel"]), None)
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
            st.markdown(card_html(f, f["id"] == st.session_state["sel"]), unsafe_allow_html=True)
            st.button("İncele", key=f"btn_{f['id']}", on_click=select_flight,
                      args=(f["id"],), use_container_width=True)
    else:
      st.info("Şu an listelenecek uçak yok. Arayüzü denemek için ⚙️ menüsünden “Demo modu”nu aç.")

    st.markdown(
        "<div class='foot'>Veri: OpenSky Network · adsbdb · Open-Meteo · "
        "Harita: © OpenStreetMap katkıcıları, © CARTO · Rota/tür bilgisi bazı uçaklarda eksik olabilir.</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
  main()
