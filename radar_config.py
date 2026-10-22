"""
radar_config.py
  Atlas'ın Uçak Gözlem Kulesi - Sabitler, Konfigürasyon ve Sözlükler.
"""

from pathlib import Path
from zoneinfo import ZoneInfo

# Zaman dilimi ve Coğrafi koordinatlar
TZ = ZoneInfo("Europe/Amsterdam")

HOME_LAT, HOME_LON = 51.4951, 5.4779  # Panorama (5629 TT) civarı; ekranda adres yazmaz.
AIRPORT_LAT, AIRPORT_LON = 51.4501, 5.3743  # Eindhoven Havalimanı
AIRPORT_ICAO = "EHEH"

# OpenSky sorgu kutusu ve filtre parametreleri
NEAR_KM = 50  # havalimanına bu kadar yakın alçak uçaklar her zaman gösterilir
OVERFLIGHT_KM = 30  # "Üstümüzden geçenler": evden bu kadar yakın yüksek uçaklar
INBOUND_MAX_ALT_FT = 25000  # uzaktan gelen (EIN'e alçalan) uçaklar için irtifa sınırı

# Kapsama seçenekleri: etiket -> (tarama yarıçapı km, haritanın gösterdiği yarıçap km)
COVERAGE = {
    "📡 Yakın · 50 km": (50, 40),
    "📡 Geniş · 100 km": (100, 85),
    "📡 Çok geniş · 200 km": (200, 170),
}

# Veri yenileme aralıkları
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
CFG = {"visible_km": VISIBLE_KM, "visible_alt": VISIBLE_ALT_FT, "overflight_km": OVERFLIGHT_KM}

# Kuzey koridoru şeridi (pist 03/21 ekseni)
CORRIDOR_ON = True
CORRIDOR_HEADING = 30  # derece
CORRIDOR_LEN_KM = 14
CORRIDOR_HALF_WIDTH_KM = 1.5

LOGO_DIR = Path(__file__).parent / "assets" / "logos"
ENRICH_WORKERS = 12  # rota/tür/logo sorguları paralel yapılır
RUNWAY_AXIS = 30  # pist 03/21 ekseni (derece)
RUNWAY_NEAR_KM = 10  # pist tespiti için havalimanına bu kadar yakın uçaklara bakılır
LOGO_URLS = [
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
ADSBLOL_URL = "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}"
OPENSKY_TIMEOUT = 2.2
OPENSKY_DOWN_S = 1800

# Çağrı kodunun ilk 3 harfi -> ortak anahtar
ALIASES = {
    "TVF": "TRA", "WMT": "WZZ", "WUK": "WZZ", "TFL": "TUI", "TOM": "TUI",
    "TUY": "TUI", "RUK": "RYR", "RYR": "RYR", "KLC": "KLM", "EZS": "EZY",
    "EJU": "EZY", "CND": "CAI", "CXI": "CAI",
}

# Havayolu bilgileri: anahtar -> (ad, arka plan, yazı rengi, IATA kodu)
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
    "CAI": ("Corendon", "#d91a2a", "#ffffff", "XC"),
    "FHY": ("Freebird", "#e11d48", "#ffffff", "FH"),
    "BAW": ("British Airways", "#1e3a8a", "#ffffff", "BA"),
    "AFR": ("Air France", "#1d4ed8", "#ffffff", "AF"),
    "SAS": ("SAS", "#0f172a", "#38bdf8", "SK"),
    "EWG": ("Eurowings", "#831843", "#ffffff", "EW"),
    "TAP": ("TAP Portugal", "#15803d", "#ffffff", "TP"),
    "IBE": ("Iberia", "#b91c1c", "#fde047", "IB"),
    "SWR": ("SWISS", "#dc2626", "#ffffff", "LX"),
    "AUA": ("Austrian", "#b91c1c", "#ffffff", "OS"),
    "LOT": ("LOT Polish", "#1e3a8a", "#ffffff", "LO"),
    "BTI": ("airBaltic", "#65a30d", "#ffffff", "BT"),
    "NAX": ("Norwegian", "#b91c1c", "#ffffff", "DY"),
}

# Özel çağrı kodu önekleri (Eindhoven Hava Üssü, Askeri, Ambulans, Polis)
SPECIAL_PREFIXES = {
    "NAF": ("Hollanda Kraliyet Hava Kuvvetleri 🪖", "#3f6212", "#ecfccb", "MIL"),
    "MMF": ("NATO Tanker & Nakliye Filosu (Eindhoven) 🪖", "#3f6212", "#ecfccb", "MIL"),
    "GAF": ("Alman Hava Kuvvetleri 🪖", "#3f6212", "#ecfccb", "MIL"),
    "BAF": ("Belçika Hava Kuvvetleri 🪖", "#3f6212", "#ecfccb", "MIL"),
    "RCH": ("ABD Hava Kuvvetleri (USAF) 🪖", "#3f6212", "#ecfccb", "MIL"),
    "RRR": ("İngiliz Kraliyet Hava Kuvvetleri 🪖", "#3f6212", "#ecfccb", "MIL"),
    "GRZ": ("Hollanda Chinook Filosu (298 Sqn) 🚁", "#3f6212", "#ecfccb", "MIL"),
    "LIF": ("Lifeliner Hava Ambulansı 🚁", "#b91c1c", "#fef2f2", "MED"),
    "ANW": ("ANWB Hava Ambulansı 🚁", "#b91c1c", "#fef2f2", "MED"),
    "ZXP": ("Hollanda Polis Helikopteri 🚁", "#1d4ed8", "#eff6ff", "POL"),
}

SPECIAL_TYPES = {
    "C130", "C30J", "A400", "C17", "F35", "CH47", "H47", "AH64",
    "NH90", "EC35", "H135", "EC45", "H145", "AW139"
}

# ICAO tür kodu -> (ad, tipik koltuk sayısı, çocuklara göre kısa bilgi)
AIRCRAFT_TYPES = {
    "B737": ("Boeing 737-700", 149, "737 ailesinin çevik ve kısa gövdeli üyesi; kanat uçları yukarı kıvrıktır!"),
    "B738": ("Boeing 737-800", 189, "Dünyanın en popüler yolcu uçağı! Eindhoven'a en çok inen modeldir."),
    "B739": ("Boeing 737-900", 190, "737-800'ün uzatılmış abisi; daha fazla bavul ve yolcu taşır."),
    "B37M": ("Boeing 737 MAX 7", 172, "Yeni nesil 737 MAX ailesinin en kısa ve uzun menzilli üyesi."),
    "B38M": ("Boeing 737 MAX 8", 189, "737'nin yeni nesil, çok daha sessiz modeli; motorlarının arkası tırtıklıdır!"),
    "B39M": ("Boeing 737 MAX 9", 220, "737 MAX ailesinin dev gövdeli uzun üyesi."),
    "A318": ("Airbus A318", 107, "Airbus A320 ailesinin en küçüğü; pilotlar ona 'Bebek Otobüs' (Baby Bus) der!"),
    "A319": ("Airbus A319", 140, "A320 ailesinin kısa ve çevik üyesi; kısa pistlere bile rahatça iner."),
    "A320": ("Airbus A320-200", 180, "Pilot koltuğunda direksiyon yerine oyun kolu (sidestick) olan ilk yolcu uçağı!"),
    "A20N": ("Airbus A320neo", 186, "Devasa yeni motorlarıyla çok az yakıt harcayan, fısıltı kadar sessiz A320!"),
    "A321": ("Airbus A321", 220, "A320'nin uzatılmış gövdeli hali; neredeyse bir futbol sahasının yarısı boyundadır."),
    "A21N": ("Airbus A321neo", 239, "Wizz Air ve Transavia'nın yeni gözdesi; tek koridorlu uçakların en büyüğü!"),
    "BCS1": ("Airbus A220-100", 120, "Büyük pencereli, çok modern ve sessiz bölgesel jet."),
    "BCS3": ("Airbus A220-300", 145, "Balina sesine benzer ilginç motor sesiyle tanınan yeni nesil Airbus!"),
    "E170": ("Embraer 170", 76, "Brezilya yapımı çevik yolcu uçağı; orta koltuğu yoktur, herkes cam veya koridordadır!"),
    "E175": ("Embraer 175", 88, "KLM Cityhopper'ın sık kullandığı Brezilya yapımı bölgesel jet."),
    "E190": ("Embraer 190", 100, "Brezilya yapımı popüler bölgesel jet; ikişerli koltuk düzeniyle çok rahattır."),
    "E195": ("Embraer 195", 120, "Embraer 190'ın uzun versiyonu."),
    "E290": ("Embraer E190-E2", 106, "'Kâr Avcısı' lakaplı, kartal kanatlı yeni nesil süper sessiz jet!"),
    "E295": ("Embraer E195-E2", 132, "KLM'nin yeni kullandığı, dev motorlu Brezilya uçağı."),
    "AT72": ("ATR 72", 70, "Kanatlarında iki büyük pervanesi olan kısa mesafe yolcu uçağı!"),
    "AT76": ("ATR 72-600", 72, "Pervaneleri dışarıdan görünür; bulutların arasından pırpır ederek uçar."),
    "DH8D": ("Dash 8 Q400", 78, "Jet uçakları kadar hızlı uçabilen iki pervaneli süper turboprop!"),
    "CRJ9": ("Bombardier CRJ-900", 90, "Motorları kanatlarında değil, arka kuyruğunun iki yanındadır!"),
    "B763": ("Boeing 767-300", 220, "Okyanusları aşan geniş gövdeli uzun yol uçağı."),
    "B772": ("Boeing 777-200", 300, "Dünyanın en büyük jet motorlarına sahip dev yolcu uçağı!"),
    "B77W": ("Boeing 777-300ER", 350, "Tek bir motorunun içine bir Boeing 737 gövdesi sığabilir!"),
    "B788": ("Boeing 787-8 Dreamliner", 240, "Gövdesi karbon fiberden yapılan, uçarken kanatları yay gibi esneyen uçak!"),
    "B789": ("Boeing 787-9 Dreamliner", 290, "Pencerelerinde güneşlik yerine düğmeyle kararan akıllı camlar vardır!"),
    "B78X": ("Boeing 787-10 Dreamliner", 330, "Dreamliner ailesinin en uzun üyesi!"),
    "A332": ("Airbus A330-200 / MRTT", 250, "Eindhoven üssünde havada başka uçaklara yakıt ikmali yapan tanker modelleri de vardır!"),
    "A333": ("Airbus A330-300", 290, "Kıtalararası uçan çift koridorlu dev Airbus."),
    "A339": ("Airbus A330-900neo", 300, "Kıvrık kanat uçlu yeni nesil geniş gövde Airbus."),
    "A359": ("Airbus A350-900", 300, "Kokpit camları Zorro maskesine benzeyen ultra modern dev uçak!"),
    "A35K": ("Airbus A350-1000", 360, "Arka tekerleklerinde 6'şar lastik bulunan dev kıtalararası uçak!"),
    "A388": ("Airbus A380", 520, "Dünyanın en büyük yolcu uçağı! Baştan sona iki katlı uçan bir saraydır!"),
    "B744": ("Boeing 747-400", 400, "Ön kısmındaki kamburuyla ünlü 'Gökyüzünün Kraliçesi' Jumbo Jet!"),
    "B748": ("Boeing 747-8", 410, "Dünyanın en uzun yolcu ve kargo uçaklarından biri!"),
    "C130": ("Lockheed C-130 Hercules 🪖", 92, "Eindhoven Hava Üssü'nün 4 pervaneli askeri kahramanı! Toprak piste bile inebilir."),
    "C30J": ("C-130J Super Hercules 🪖", 92, "6 kanatlı pervaneleriyle çok güçlü askeri kargo uçağı!"),
    "A400": ("Airbus A400M Atlas 🪖", 116, "Adı da 'Atlas'! Dev pervaneleri ters yönlere dönen süper güçlü askeri nakliye uçağı!"),
    "C17": ("Boeing C-17 Globemaster III 🪖", 102, "İçine koca bir tank veya helikopter sığabilen 4 motorlu dev askeri jet!"),
    "F35": ("Lockheed Martin F-35 Lightning II 🪖", 1, "Ses hızını aşabilen, radarda görünmeyen süper hızlı savaş uçağı!"),
    "CH47": ("Boeing CH-47 Chinook 🚁", 44, "Önde ve arkada iki dev pervanesi olan, kamyon bile taşıyabilen güçlü helikopter!"),
    "H47": ("Boeing CH-47 Chinook 🚁", 44, "Önde ve arkada iki dev pervanesi olan, kamyon bile taşıyabilen güçlü helikopter!"),
    "AH64": ("Boeing AH-64 Apache 🚁", 2, "Kraliyet Hava Kuvvetleri'nin ileri teknoloji keşif ve koruma helikopteri."),
    "NH90": ("NHIndustries NH90 🚁", 20, "Gemilere dahi inebilen modern askeri arama-kurtarma helikopteri."),
    "EC35": ("Airbus H135 Helikopter 🚁", 5, "Çoğunlukla sarı renkli 'Lifeliner' hava ambulansı veya polis helikopteri olarak uçar!"),
    "H135": ("Airbus H135 Helikopter 🚁", 5, "Doktorları trafiğe takılmadan dakikalar içinde olay yerine ulaştıran helikopter!"),
    "EC45": ("Airbus H145 Helikopter 🚁", 8, "Kuyruk pervanesi kapalı (Fenestron) olduğu için çok güvenli ve sessiz helikopter."),
    "H145": ("Airbus H145 Helikopter 🚁", 8, "Arama-kurtarma ve hava ambulansı görevlerinin hızlı yıldızı!"),
    "PC12": ("Pilatus PC-12 🛩️", 9, "İsviçre yapımı, tek pervaneli ama jet kadar hızlı özel uçak!"),
    "C56X": ("Cessna Citation Excel 🛩️", 8, "İş insanlarını ve özel yolcuları taşıyan hızlı özel jet."),
    "GLF5": ("Gulfstream V 🛩️", 14, "Büyük oval pencereli, okyanus aşabilen ultra hızlı özel jet!"),
    "GLF6": ("Gulfstream G650 🛩️", 16, "Neredeyse ses hızına yakın uçabilen dünyanın en hızlı özel jetlerinden biri!"),
}

# Havayoluna özel koltuk sayısı: (havayolu, tip) -> koltuk
SEATS_BY_AIRLINE = {
    ("TRA", "B738"): 189, ("TRA", "B737"): 149, ("TRA", "A21N"): 232,
    ("RYR", "B738"): 189, ("RYR", "B38M"): 197,
    ("WZZ", "A320"): 180, ("WZZ", "A20N"): 186, ("WZZ", "A321"): 230, ("WZZ", "A21N"): 239,
    ("EZY", "A319"): 156, ("EZY", "A320"): 180, ("EZY", "A20N"): 186,
    ("PGT", "A20N"): 186, ("PGT", "A21N"): 239, ("PGT", "B738"): 189,
    ("TUI", "B38M"): 189, ("TUI", "B738"): 189, ("TUI", "B788"): 300,
}

COMPASS_TR = [
    ("Kuzey", "⬆️"), ("Kuzeydoğu", "↗️"), ("Doğu", "➡️"), ("Güneydoğu", "↘️"),
    ("Güney", "⬇️"), ("Güneybatı", "↙️"), ("Batı", "⬅️"), ("Kuzeybatı", "↖️"),
]

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


def compass_label(deg):
  idx = int(((deg + 22.5) % 360) // 45)
  name, arrow = COMPASS_TR[idx]
  return f"{arrow} {name}"


def seat_text(airline_key, type_code, default=None):
  """'~189 koltuk' gibi metin; bilinmiyorsa 'Bilinmiyor'."""
  n = SEATS_BY_AIRLINE.get((airline_key, type_code)) or default
  return f"~{n} koltuk" if n else "Bilinmiyor"


def kid_comparison(f):
  """Atlas için hız ve yükseklik karşılaştırması (her uçak için dinamik üretilir)."""
  spd = f.get("speed") or 0
  alt_m = round((f.get("alt_ft") or 0) * 0.3048)
  parts = []
  if spd >= 300:
    cars = max(2, round(spd / 100))
    parts.append(f"🏎️ Otobandaki bir arabadan <b>{cars} kat</b> hızlı!")
  elif spd >= 120:
    parts.append(f"🐆 Bir çitadan bile <b>2 kat</b> hızlı gidiyor!")
  if alt_m >= 600:
    eiffel = max(2, round(alt_m / 300))
    parts.append(f"🗼 Üst üste <b>{eiffel} Eyfel Kulesi</b> yüksekliğinde!")
  elif alt_m >= 90:
    floors = max(10, round(alt_m / 3.5))
    parts.append(f"🏢 Yaklaşık <b>{floors} katlı</b> bir gökdelen boyunda!")
  return " · ".join(parts)

