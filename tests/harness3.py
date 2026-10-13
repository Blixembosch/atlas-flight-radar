"""Sahte streamlit/folium/requests ile Radar.py v0.3'ü uçtan uca çalıştırır.

Gerçek Streamlit davranışlarından taklit edilenler (hataları yakalamak için):
  * Bileşen değeri session_state[key]'de tutulur; ekranda çizilmeyen bileşenin anahtarı silinir.
  * Bileşen çizildikten sonra aynı çalıştırmada session_state[key] atamak istisna fırlatır.
  * radio/selectbox'ta seçenek dışı değer istisna fırlatır.
  * st.rerun() / st.stop() gerçekteki gibi akışı keser.
"""
import sys, os, types, time, importlib.util, tempfile, functools, base64
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, PROJ)

class Rerun(Exception): pass
class StreamlitAPIException(Exception): pass

class Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False

class SS(dict):
    fake = None
    def __setitem__(self, k, v):
        if SS.fake and k in SS.fake.rendered:
            raise StreamlitAPIException(f"session_state.{k} bileşen çizildikten sonra değiştirilemez")
        super().__setitem__(k, v)
    def setdefault(self, k, v=None):
        if k not in self: super().__setitem__(k, v)
        return self[k]
    def _force(self, k, v): super().__setitem__(k, v)

class FakeSt(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = SS(); SS.fake = self
        self.secrets = {}
        self.rendered = set(); self.widget_keys = set()
        self.reset_run(); self.pressed = set(); self.refresh = None; self.reruns = 0
        self.stopped = False
    def reset_run(self):
        self.md = []; self.infos = []; self.errors = []; self.warnings = []; self.buttons = {}
        self.rendered = set(); self.stopped = False
    def end_run(self):
        for k in list(self.widget_keys - self.rendered):
            dict.pop(self.session_state, k, None)
    # dekoratörler
    def cache_data(self, *a, **k): return a[0] if a and callable(a[0]) else (lambda fn: fn)
    def cache_resource(self, *a, **k):
        def deco(fn):
            memo = {}
            @functools.wraps(fn)
            def w(*args): 
                if args not in memo: memo[args] = fn(*args)
                return memo[args]
            w.memo = memo
            return w
        return deco(a[0]) if a and callable(a[0]) else deco
    def set_page_config(self, **k): self.page = k
    def markdown(self, html, **k): self.md.append(html)
    def caption(self, t, **k): self.md.append(t)
    def info(self, t): self.infos.append(t)
    def error(self, t): self.errors.append(t)
    def warning(self, t): self.warnings.append(t)
    def stop(self): self.stopped = True; raise SystemExit
    def rerun(self): self.reruns += 1; raise Rerun()
    def container(self, key=None, **k): return Ctx()
    def form(self, key, **k): return Ctx()
    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [Ctx() for _ in range(n)]
    def popover(self, *a, **k): return Ctx()
    def spinner(self, *a, **k): return Ctx()
    def code(self, t, **k): self.md.append("<code>" + str(t) + "</code>")
    # --- bileşenler
    def _w(self, key, label, default, options=None):
        k = key or label
        self.rendered.add(k); self.widget_keys.add(k)
        ss = self.session_state
        if k not in ss:
            SS.fake = None; ss[k] = default; SS.fake = self
        v = ss[k]
        if options is not None and v not in options:
            raise StreamlitAPIException(f"{k}: {v!r} seçenekler içinde yok")
        return v
    def radio(self, label, options, key=None, **k): return self._w(key, label, options[0], list(options))
    def selectbox(self, label, options, index=0, key=None, **k):
        o = list(options); return self._w(key, label, o[index], o)
    def toggle(self, label, value=False, key=None, **k): return self._w(key, label, value)
    def text_input(self, label, value="", key=None, **k): return self._w(key, label, value)
    def slider(self, label, mn, mx, value=None, step=None, key=None, **k):
        return self._w(key, label, mn if value is None else value)
    def button(self, label, key=None, on_click=None, args=(), **k):
        self.buttons[key or label] = (on_click, args)
        return (key or label) in self.pressed
    def form_submit_button(self, label, **k):
        self.buttons[label] = (None, ()); return label in self.pressed

fake = FakeSt()
sys.modules["streamlit"] = fake
ar = types.ModuleType("streamlit_autorefresh")
ar.st_autorefresh = lambda interval, key=None: setattr(fake, "refresh", interval)
sys.modules["streamlit_autorefresh"] = ar

# ---- folium sahtesi
class Rec:
    n = 0
    def __init__(self, kind, *a, **k):
        Rec.n += 1; self.kind = kind; self.a = a; self.k = k; self.name = f"{kind}_{Rec.n}"
    def add_to(self, m): m.items.append(self); return self
    def get_name(self): return self.name
class Root:
    class H:
        def __init__(s): s.items = []
        def add_child(s, x): s.items.append(x)
    def __init__(s): s.html = Root.H()
class Map:
    def __init__(self, *a, **k): self.items = []; self.k = k; self.bounds = None; self._root = Root()
    def fit_bounds(self, b): self.bounds = b
    def get_root(self): return self._root
    def markers(self): return [i for i in self.items if i.kind == "Marker"]
folium = types.ModuleType("folium")
folium.Map = Map
for nm in ["TileLayer", "Circle", "CircleMarker", "Polygon", "Marker", "LayerControl"]:
    setattr(folium, nm, (lambda nm: lambda *a, **k: Rec(nm, *a, **k))(nm))
class Tip(str):
    def __new__(cls, t, **k):
        o = str.__new__(cls, t); o.k = k; return o
folium.Tooltip = Tip
folium.DivIcon = lambda html, **k: types.SimpleNamespace(html=html, **k)
folium.Element = lambda t: t
class MacroElement(Rec):
    def __init__(self): Rec.__init__(self, "Macro")
folium.MacroElement = MacroElement
sys.modules["folium"] = folium
be = types.ModuleType("branca.element"); be.MacroElement = MacroElement
be.Template = lambda t: t
sys.modules["branca"] = types.ModuleType("branca"); sys.modules["branca.element"] = be
sf = types.ModuleType("streamlit_folium")
class SF:
    calls = []; click_for_key = {}
    @staticmethod
    def st_folium(m, **k):
        SF.calls.append((m, k)); key = k.get("key")
        return {"last_object_clicked_tooltip": SF.click_for_key.get(key)} if SF.click_for_key.get(key) else {}
sf.st_folium = SF.st_folium
sys.modules["streamlit_folium"] = sf

# ---- requests sahtesi
class Resp:
    def __init__(s, js=None, code=200, ctype="application/json", content=b""):
        s._js = js; s.status_code = code; s.headers = {"content-type": ctype}; s.content = content
    def json(s):
        if s._js is None: raise ValueError("json yok")
        return s._js

class Net:
    states = []; routes = {}; route_err = set(); fail_opensky = False
    aircraft = {}; adb_status = 200; adb_json = None; gh = None
    os_exc = None; adsb = None; adb_delay = 0; logo_delay = 0; os_delay = 0
    calls = {"opensky": 0, "adb": 0, "github": 0, "adsbdb": 0, "adsblol": 0}
    log = []     # (url) tüm istekler
    @classmethod
    def reset(cls):
        cls.states = []; cls.routes = {}; cls.route_err = set(); cls.fail_opensky = False
        cls.aircraft = {}; cls.adb_status = 200; cls.adb_json = None; cls.gh = None
        cls.os_exc = None; cls.adsb = None; cls.adb_delay = 0; cls.logo_delay = 0; cls.os_delay = 0
        cls.calls = {"opensky": 0, "adb": 0, "github": 0, "adsbdb": 0, "adsblol": 0}; cls.log = []

def rget(url, params=None, headers=None, timeout=None, **kw):
    Net.log.append(url)
    if "opensky-network.org/api/states" in url:
        Net.calls["opensky"] += 1
        if Net.os_delay: time.sleep(Net.os_delay)
        if Net.os_exc: raise Net.os_exc
        return Resp({"states": Net.states}, 500 if Net.fail_opensky else 200)
    if "api.adsb.lol" in url:
        Net.calls["adsblol"] += 1
        if Net.adsb is None: return Resp(None, 503)
        return Resp(Net.adsb)
    if "aerodatabox" in url:
        Net.calls["adb"] += 1
        if Net.adb_delay: time.sleep(Net.adb_delay)
        return Resp(Net.adb_json if Net.adb_json is not None else {}, Net.adb_status)
    if "/callsign/" in url:
        Net.calls["adsbdb"] += 1
        cs = url.rsplit("/", 1)[1]
        if cs in Net.route_err: raise Exception("zaman aşımı")
        if cs in Net.routes: return Resp({"response": {"flightroute": Net.routes[cs]}})
        return Resp({"response": "unknown callsign"}, 404)
    if "/aircraft/" in url:
        h = url.rsplit("/", 1)[1]
        return Resp({"response": {"aircraft": Net.aircraft.get(h, {})}})
    if "planespotters" in url: return Resp({"photos": []})
    if "open-meteo" in url:
        return Resp({"current": {"temperature_2m": 12.4, "weather_code": 3, "wind_speed_10m": 20, "wind_direction_10m": 215}})
    if url.endswith(".png") or "avs.io" in url:
        if Net.logo_delay: time.sleep(Net.logo_delay)
        return Resp(None, 200, "image/png", b"x" * 500)
    return Resp(None, 404)

def rrequest(method, url, **kw):
    Net.log.append(url)
    if "api.github.com" in url:
        Net.calls["github"] += 1
        return Net.gh.request(method, url, **kw)
    raise AssertionError("beklenmeyen istek " + url)

rq = types.ModuleType("requests"); rq.get = rget; rq.post = rget; rq.request = rrequest
rq.RequestException = Exception
sys.modules["requests"] = rq

# ---- uygulamayı yükle (veritabanı geçici klasörde)
import radar_db
_orig_open = radar_db.open_db
DBDIR = tempfile.mkdtemp()
def _open(secret, path=None, http=None):
    return _orig_open(secret, path=os.path.join(DBDIR, "radar.db"), http=http)
radar_db.open_db = _open

FETCH_TTL_TEST = 0
spec = importlib.util.spec_from_file_location("radar", os.path.join(PROJ, "Radar.py"))
radar = importlib.util.module_from_spec(spec); spec.loader.exec_module(radar)
radar.DEFAULT_PAGE = radar.PAGES[0]   # mevcut testler Radar ile başlar; varsayılan ayrıca test edilir
radar.FETCH_TTL = 0   # testlerde her çalıştırmada taze veri

def run():
    """Bir Streamlit çalıştırması (rerun'da yeniden çalışır). Dönüş: rerun sayısı."""
    for i in range(6):
        fake.reset_run()
        try:
            radar.main()
        except Rerun:
            fake.end_run(); fake.pressed = set(); continue
        except SystemExit:
            pass
        fake.end_run(); fake.pressed = set(); return i
    raise RuntimeError("rerun döngüsü!")

def press(key):
    cb, args = fake.buttons[key]
    if cb: cb(*args)
    fake.pressed = {key}
    return run()

class Timeout(Exception): pass

def reset_app(secrets=None):
    """Yeni tarayıcı oturumu + yeni sunucu durumu."""
    import shutil
    Net.reset(); radar._SRC.update(os_down_until=0.0, last_source="")
    for f in os.listdir(DBDIR): 
        p = os.path.join(DBDIR, f)
        if os.path.isfile(p): os.remove(p)
    fake.session_state.clear(); fake.widget_keys = set(); fake.rendered = set()
    fake.secrets = dict(secrets or {}); fake.refresh = None; fake.pressed = set(); fake.reruns = 0
    radar.get_db.memo.clear(); radar.get_store.memo.clear(); radar._TCACHE.clear(); radar._BG["logo"].clear()
    for k in list(radar.__dict__.get("_x", {})): pass
    SF.calls.clear(); SF.click_for_key.clear()

def new_session():
    """Aynı sunucu, yeni tarayıcı sekmesi."""
    fake.session_state.clear(); fake.widget_keys = set(); fake.rendered = set(); fake.refresh = None

def login(pw="gizli"):
    fake.session_state._force("Şifre", pw); fake.pressed = {"Giriş yap"}; return run()

def ap(i, ic, c, iso, la, lo): return {"iata_code": i, "icao_code": ic, "municipality": c, "country_iso_name": iso, "latitude": la, "longitude": lo}
def row(h, cs, lat, lon, ft, kmh, trk, vr, tp=None):
    m = ft / 3.28084; tp = tp or time.time() - 4
    return [h, cs, "NL", tp, tp, lon, lat, m, False, kmh / 3.6, trk, vr, None, m, None, False, 0]

# ---- AeroDataBox taklidi: şimdiye göre 12 saatlik tarife
def adb_payload(n=32, base_now=None):
    from zoneinfo import ZoneInfo
    now = (base_now or datetime.now(ZoneInfo("Europe/Amsterdam"))).replace(tzinfo=None, second=0, microsecond=0)
    def fl(i, d):
        t = now - timedelta(hours=1) + timedelta(minutes=14 * i + (5 if d == "dep" else 0))
        rev = (t + timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M+02:00") if i % 4 == 1 else None
        mv = {"airport": {"icao": "LEMG", "iata": "AGP" if i % 2 else "IST", "municipalityName": "Malaga" if i % 2 else "İstanbul", "countryCode": "ES" if i % 2 else "TR"},
              "scheduledTime": {"utc": "x", "local": t.strftime("%Y-%m-%d %H:%M+02:00")}}
        if rev: mv["revisedTime"] = {"utc": "x", "local": rev}
        if d == "dep": mv["gate"] = f"B{1 + i % 9}"
        return {"movement": mv, "number": f"HV {5000 + i}" if d == "dep" else f"FR {100 + i}",
                "status": "Expected", "callSign": f"TRA{5000 + i}",
                "aircraft": {"model": "Boeing 737-800", "reg": "PH-HZA"},
                "airline": {"name": "Transavia" if d == "dep" else "Ryanair", "iata": "HV" if d == "dep" else "FR", "icao": "TRA" if d == "dep" else "RYR"}}
    return {"departures": [fl(i, "dep") for i in range(n)], "arrivals": [fl(i, "arr") for i in range(n)]}

# ---- GitHub taklidi (test_db_auth'taki ile aynı)
from fakes import FakeGH  # noqa
