"""
radar_styles.py
  Atlas'ın Uçak Gözlem Kulesi - Tasarım, CSS ve HTML Sunum Parçaları.
"""

import re
from html import escape as esc
from radar_config import SPECIAL_PREFIXES, AIRLINES

CSS = """
<style>
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
#MainMenu, footer{visibility:hidden;}
.stApp{background:#0b1020;color:#f1f5f9;}
.block-container{padding:.9rem 1.3rem 1.5rem!important;max-width:1600px;}
:root{--card:#121a33;--line:#2a3b68;--muted:#cbd5e1;--arr:#38bdf8;--dep:#fb923c;--ok:#22c55e;}

/* Streamlit varsayılan uyarı / bilgi kutularını yüksek kontrastlı yap */
div[data-testid="stAlert"]{background:#16244f !important;border:1px solid #38bdf8 !important;border-radius:12px !important;box-shadow:0 4px 18px rgba(0,0,0,0.3) !important;}
div[data-testid="stAlert"] p, div[data-testid="stAlert"] div{color:#f8fafc !important;font-weight:600 !important;font-size:0.95rem !important;}
div[data-testid="stAlert"] svg{color:#38bdf8 !important;}

/* Üst bar */
.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;
  background:linear-gradient(120deg,#1d2a6b 0%,#3b2a8c 55%,#7a2a6a 100%);
  border:1px solid rgba(255,255,255,.2);border-radius:18px;padding:12px 20px;}
.brand{font-size:1.35rem;font-weight:800;letter-spacing:-.3px;color:#fff;}
.brand small{display:block;font-size:.76rem;font-weight:500;color:#e2e8f0;opacity:.95;letter-spacing:0;}
.chips{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}
.chip{background:rgba(10,14,32,.6);border:1px solid rgba(255,255,255,.22);border-radius:12px;
  padding:6px 12px;font-size:.84rem;font-weight:700;color:#ffffff;white-space:nowrap;}
.chip b{color:#ffffff;font-weight:800;}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:middle;}
.dot.live{background:#ef4444;box-shadow:0 0 0 0 rgba(239,68,68,.7);animation:pulse 1.6s infinite;}
.dot.demo{background:#f59e0b;} .dot.err{background:#cbd5e1;}
@keyframes pulse{70%{box-shadow:0 0 0 9px rgba(239,68,68,0);}100%{box-shadow:0 0 0 0 rgba(239,68,68,0);}}

/* Tek satırlık bilgi şeritleri (sıradaki uçak, aktif pist) */
.strip{display:flex;align-items:center;gap:10px;margin:10px 0 12px;padding:8px 16px;min-height:40px;
  background:var(--card);border:1px solid var(--line);border-radius:12px;font-size:.9rem;
  white-space:nowrap;overflow:hidden;color:#f1f5f9;font-weight:600;}
.strip .ic{font-size:1.15rem;flex:none;}
.strip .tx{overflow:hidden;text-overflow:ellipsis;min-width:0;color:#f8fafc;}
.strip .sub{color:#93c5fd;font-size:.82rem;font-weight:600;margin-left:8px;}
.strip b{color:#ffffff;font-weight:800;}
.strip.hot{border-color:rgba(56,189,248,.65);background:linear-gradient(90deg,rgba(56,189,248,.22),rgba(124,77,255,.14));}
.strip.garden-now{border-color:#22c55e;background:linear-gradient(90deg,rgba(34,197,94,.32),rgba(250,204,21,.18));
  box-shadow:0 0 20px rgba(34,197,94,.35);}

/* Logo */
.logo{display:inline-flex;align-items:center;justify-content:center;border-radius:12px;font-weight:900;
  letter-spacing:.3px;box-shadow:0 2px 8px rgba(0,0,0,.35);overflow:hidden;}
.logo-xl{height:56px;min-width:140px;padding:0 18px;font-size:1.35rem;}
.logo-md{height:46px;min-width:120px;padding:0 10px;font-size:.92rem;}
.logo.logo-img{background:#eef0f4;}
.logo-img img{max-height:100%;max-width:100%;object-fit:contain;padding:6px 4px;}

/* Sağ detay paneli */
.panel{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px 18px;min-height:640px;box-sizing:border-box;}
.panel .head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px;}
.panel .cs{font-size:1.75rem;font-weight:800;color:#ffffff;line-height:1.05;}
.panel .al{color:#cbd5e1;font-size:.95rem;font-weight:600;margin-top:2px;}
.panel .ph{width:100%;border-radius:12px;margin:6px 0 2px;max-height:140px;object-fit:cover;}
.panel .credit{font-size:.72rem;color:#94a3b8;font-weight:600;margin-bottom:4px;}
.route{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:8px 0 4px;}
.route .ap{text-align:center;min-width:0;}
.route .code{font-size:1.65rem;font-weight:800;color:#ffffff;}
.route .city{font-size:.85rem;color:#cbd5e1;font-weight:600;}
.route .fl{font-size:1.6rem;}
.prog{position:relative;flex:1;height:5px;background:var(--line);border-radius:4px;margin:0 6px;}
.prog-fill{height:100%;background:linear-gradient(90deg,#38bdf8,#7c4dff);border-radius:4px;}
.prog-plane{position:absolute;top:-11px;transform:translateX(-50%);font-size:1.1rem;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;}
.stat{background:#0e1630;border:1px solid var(--line);border-radius:12px;padding:10px 14px;}
.stat small{display:block;color:#93c5fd;font-size:.72rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;}
.stat b{font-size:1.18rem;color:#ffffff;font-weight:800;}
.badge{display:inline-block;border-radius:8px;padding:5px 11px;font-size:.75rem;font-weight:800;}
.badge.arr{background:#0369a1;color:#f0f9ff;} .badge.dep{background:#c2410c;color:#fff7ed;}
.badge.trn{background:#4c1d95;color:#f5f3ff;} .badge.vis{background:#15803d;color:#ffffff;} .badge.far{background:#1e293b;color:#cbd5e1;}
.status2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;}
.sbox{border-radius:12px;padding:10px;text-align:center;font-weight:700;font-size:.9rem;}
.sbox.a{background:#166534;color:#f0fdf4;font-weight:800;} .sbox.b{background:#0e1630;border:1px solid var(--line);color:#f1f5f9;}
.compass-box{margin-top:8px;background:linear-gradient(120deg,rgba(14,116,144,.35),rgba(30,58,138,.35));
  border:1px solid rgba(56,189,248,.45);border-radius:12px;padding:10px 14px;font-size:.88rem;color:#f0f9ff;font-weight:600;}
.compass-box b{color:#fde047;font-weight:800;}
.fids-match{margin-top:8px;background:#0e1630;border:1px solid rgba(251,146,60,.5);border-radius:12px;
  padding:10px 14px;font-size:.85rem;color:#f8fafc;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;}
.fact{margin-top:8px;font-size:.88rem;color:#f1f5f9;background:#0e1630;border:1px solid rgba(124,77,255,.38);border-radius:12px;padding:11px 14px;line-height:1.5;}
.fact b{color:#ffffff;font-weight:800;}
.empty{text-align:center;color:#cbd5e1;padding:80px 10px;font-size:1rem;}
.empty .big{font-size:3.2rem;}

/* Kart şeridi */
.fcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:8px;}
.fcard.sel{border-color:#38bdf8;box-shadow:0 0 0 2px rgba(56,189,248,.45);}
.fcard .r1{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;}
.fcard .cs{font-weight:800;color:#ffffff;font-size:1.08rem;}
.fcard .rt{margin-top:8px;font-weight:700;color:#ffffff;font-size:.95rem;}
.fcard .meta{margin-top:5px;font-size:.82rem;font-weight:600;color:#cbd5e1;}

/* Filtre çubuğu: tek bir kart, tüm öğeler aynı yükseklikte */
.st-key-toolbar{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:10px 16px;margin:0 0 14px;}
.st-key-toolbar [data-testid="stHorizontalBlock"]{gap:14px;align-items:center;}
.st-key-toolbar [data-testid="stElementContainer"]{margin:0;}
.st-key-toolbar [data-testid="stRadio"] [role="radiogroup"]{gap:6px 16px;flex-wrap:nowrap;}
.st-key-toolbar [data-testid="stRadio"] label{white-space:nowrap;}
.st-key-toolbar [data-testid="stRadio"] label p{color:#f8fafc !important;font-weight:700 !important;}
.st-key-toolbar [data-baseweb="input"],.st-key-toolbar [data-baseweb="select"]>div{
  min-height:42px;background:#0e1630;border:1px solid #3b82f6;border-radius:10px;color:#ffffff !important;}
.st-key-toolbar input{height:40px;color:#ffffff !important;font-weight:600 !important;}
.st-key-toolbar input::placeholder{color:#94a3b8 !important;}
.st-key-toolbar [data-testid="stToggle"] label,.st-key-toolbar [data-testid="stToggle"] p{white-space:nowrap;color:#f8fafc !important;font-weight:700 !important;}
.st-key-toolbar [data-testid="stPopover"] button,.st-key-toolbar [data-testid="stPopoverButton"]{
  min-height:42px;width:100%;justify-content:center;}
div.stButton>button{border-radius:10px;font-weight:800;background:#1b2750;color:#ffffff;border:1px solid #3b82f6;}
div.stButton>button:hover{border-color:#38bdf8;color:#fff;background:#243266;}
[data-testid="stBaseButton-secondary"],[data-testid="stPopoverButton"],[data-testid="stBaseButton-secondary"] p,[data-testid="stPopoverButton"] p{background:#1b2750 !important;color:#ffffff !important;border-color:#3b82f6 !important;font-weight:700 !important;}
[data-testid="stBaseButton-secondary"]:hover{border-color:#38bdf8 !important;background:#243266 !important;}
.legend{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:8px 0 22px;padding:8px 16px;
  background:var(--card);border:1px solid var(--line);border-radius:12px;font-size:.82rem;font-weight:700;color:#f8fafc;}
.lg{display:inline-flex;align-items:center;gap:7px;white-space:nowrap;color:#f8fafc;}
.lgdot{width:13px;height:13px;border-radius:50%;background:#3b82f6;border:2px solid #fff;display:inline-block;}
.lgring{width:16px;height:16px;border-radius:50%;display:inline-block;box-sizing:border-box;}
.lgring.blue{border:2px dashed #38bdf8;background:rgba(56,189,248,.18);}
.lgring.grey{border:2px dotted #cbd5e1;}
.foot{text-align:center;color:#94a3b8;font-size:.82rem;font-weight:600;margin-top:16px;}
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
  padding:7px 18px;margin:0;cursor:pointer;transition:all .12s ease;position:relative;}
.st-key-nav [data-testid="stRadio"] label>div:first-child{position:absolute;opacity:0;width:0;height:0;pointer-events:none;}
.st-key-nav [data-testid="stRadio"] label p{font-weight:800;font-size:.95rem;color:#f8fafc;white-space:nowrap;margin:0;}
.st-key-nav [data-testid="stRadio"] label:hover{border-color:#38bdf8;}
.st-key-nav [data-testid="stRadio"] label:has(input:checked){background:linear-gradient(120deg,#2b3a9a,#6a35b8);
  border-color:rgba(255,255,255,.35);box-shadow:0 0 14px rgba(56,189,248,0.35);}
.st-key-nav [data-testid="stRadio"] label:has(input:checked) p{color:#fff;}
.st-key-nav [data-testid="stToggle"] p{white-space:nowrap;font-weight:700;font-size:.9rem;color:#f8fafc;}

/* Giriş ekranı */
.login-card{text-align:center;background:linear-gradient(160deg,#16204a,#1b1740);border:1px solid var(--line);
  border-radius:22px;padding:30px 24px 18px;margin:9vh 0 12px;box-shadow:0 18px 50px rgba(0,0,0,.4);}
.login-card .big{font-size:3.2rem;line-height:1;}
.login-card h1{font-size:1.45rem;margin:10px 0 4px;color:#fff;font-weight:800;letter-spacing:-.3px;}
.login-card p{color:#cbd5e1;font-size:.92rem;font-weight:600;margin:0 0 6px;}

/* Terminal (varış / kalkış) */
.term-head{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;
  background:linear-gradient(120deg,#0f2a55 0%,#12306b 50%,#1b2a74 100%);border:1px solid rgba(255,255,255,.18);
  border-radius:18px;padding:14px 22px;margin-bottom:12px;}
.term-head .tt{font-size:1.5rem;font-weight:800;color:#fff;letter-spacing:-.3px;}
.term-head .tt span{font-size:.85rem;font-weight:800;color:#38bdf8;margin-left:10px;letter-spacing:.08em;}
.term-head .ts{font-size:.85rem;color:#cbd5e1;font-weight:600;margin-top:2px;}
.term-head .tr{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.clock{font-size:2rem;font-weight:800;color:#fff;font-variant-numeric:tabular-nums;letter-spacing:.02em;}
.livepill{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:6px 14px;font-size:.82rem;font-weight:800;
  background:rgba(10,14,32,.7);border:1px solid rgba(255,255,255,.24);color:#fff;white-space:nowrap;}
.livepill i{width:9px;height:9px;border-radius:50%;display:inline-block;background:#cbd5e1;}
.livepill.ok i{background:#22c55e;box-shadow:0 0 10px #22c55e;} .livepill.old i{background:#f59e0b;}
.livepill.demo i{background:#f59e0b;} .livepill.none i{background:#ef4444;}
.tpanel{background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 8px 28px rgba(0,0,0,.22);}
.tphead{display:flex;justify-content:space-between;align-items:center;padding:12px 18px;
  border-bottom:1px solid var(--line);}
.tphead.arr{background:linear-gradient(90deg,rgba(56,189,248,.25),rgba(56,189,248,0));}
.tphead.dep{background:linear-gradient(90deg,rgba(251,146,60,.28),rgba(251,146,60,0));}
.tphead .nm{font-size:1.18rem;font-weight:800;color:#fff;} .tphead .nm small{color:#93c5fd;font-weight:700;font-size:.82rem;margin-left:8px;}
.tphead .ct{font-size:.82rem;color:#cbd5e1;font-weight:700;}
.fgrid{display:grid;align-items:center;gap:10px;padding:0 16px;}
.fgrid.arr{grid-template-columns:70px minmax(0,1.5fr) minmax(0,1.5fr) 118px 70px;}
.fgrid.dep{grid-template-columns:70px minmax(0,1.5fr) minmax(0,1.5fr) 46px 118px 70px;}
.fcols{padding-top:10px;padding-bottom:10px;font-size:.74rem;font-weight:900;letter-spacing:.09em;text-transform:uppercase;
  color:#93c5fd;border-bottom:1px solid var(--line);background:#0f1730;}
.frow{min-height:54px;border-bottom:1px solid rgba(42,59,104,.7);transition:background .1s ease;}
.frow:hover{background:rgba(56,189,248,.08);}
.frow.done{opacity:.65;} .frow.canc .c-fl b,.frow.canc .c-time b{text-decoration:line-through;}
.frow.next{background:linear-gradient(90deg,rgba(250,204,21,.14),rgba(250,204,21,0));box-shadow:inset 4px 0 0 #facc15;}
.c-time b{display:block;font-size:1.1rem;color:#fff;font-variant-numeric:tabular-nums;line-height:1.1;font-weight:800;}
.c-time small{display:block;font-size:.76rem;color:#fde047;font-weight:800;font-variant-numeric:tabular-nums;}
.c-fl,.c-pl{display:flex;align-items:center;gap:10px;min-width:0;}
.c-fl div,.c-pl div{min-width:0;}
.c-fl b,.c-pl b{display:block;color:#ffffff;font-size:.96rem;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.c-fl small,.c-pl small{display:block;color:#cbd5e1;font-size:.78rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.fg{font-size:1.45rem;flex:none;}
.alogo{flex:none;width:46px;height:32px;border-radius:8px;background:#ffffff center/contain no-repeat;
  background-origin:content-box;padding:3px;box-sizing:border-box;box-shadow:0 1px 4px rgba(0,0,0,.45);}
.alogo.txt{display:inline-flex;align-items:center;font-size:.75rem;font-weight:900;padding:0;justify-content:center;}
.c-gate{text-align:center;font-weight:800;color:#ffffff;font-size:.95rem;}
.c-gate.na{color:#94a3b8;font-weight:700;}
.pill{display:inline-block;border-radius:999px;padding:4px 10px;font-size:.78rem;font-weight:800;white-space:nowrap;}
.pill.ok{background:rgba(34,197,94,.22);color:#4ade80;} .pill.warn{background:rgba(245,158,11,.24);color:#fde047;}
.pill.bad{background:rgba(239,68,68,.24);color:#f87171;} .pill.info{background:rgba(56,189,248,.2);color:#7dd3fc;}
.pill.done{background:rgba(148,163,184,.2);color:#e2e8f0;}
.c-dl{text-align:right;font-weight:800;font-size:.88rem;font-variant-numeric:tabular-nums;color:#94a3b8;}
.c-dl.warn{color:#fde047;} .c-dl.bad{color:#f87171;} .c-dl.ok{color:#4ade80;}
.tempty{text-align:center;color:#cbd5e1;padding:40px 16px;font-size:.95rem;line-height:1.6;font-weight:600;}
.tempty .big{font-size:2.8rem;}
.tfoot{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:10px 18px;font-size:.78rem;color:#94a3b8;font-weight:600;}
.tnote{margin:10px 0 0;padding:10px 16px;border-radius:12px;background:var(--card);border:1px solid var(--line);font-size:.85rem;color:#f1f5f9;font-weight:600;}
.tnote.warn{border-color:rgba(245,158,11,.6);}

/* Gözlem defteri & Avcı Rozetleri */
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px;}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 16px;}
.kpi small{display:block;color:#93c5fd;font-size:.74rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;}
.kpi b{display:block;font-size:2rem;color:#fff;line-height:1.15;font-weight:800;}
.kpi span{font-size:.82rem;color:#cbd5e1;font-weight:600;}
.rank-box{background:linear-gradient(120deg,#1e293b,#1e1b4b);border:1px solid rgba(250,204,21,.45);
  border-radius:16px;padding:14px 18px;margin-bottom:12px;}
.rank-head{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px;}
.rank-title{font-size:1.15rem;font-weight:800;color:#fde047;}
.badge-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px;}
.bcard{background:#0e1630;border:1px solid var(--line);border-radius:12px;padding:8px 10px;text-align:center;opacity:.55;}
.bcard.on{opacity:1;border-color:rgba(250,204,21,.6);background:linear-gradient(160deg,#172554,#1e1b4b);}
.bcard .bi{font-size:1.55rem;display:block;line-height:1.1;}
.bcard b{display:block;font-size:.82rem;color:#fff;font-weight:800;margin-top:3px;}
.bcard small{display:block;font-size:.72rem;color:#cbd5e1;font-weight:600;line-height:1.25;margin-top:2px;}
.bars{display:flex;align-items:flex-end;gap:10px;height:110px;padding:10px 6px 0;}
.bar{flex:1;text-align:center;display:flex;flex-direction:column;justify-content:flex-end;height:100%;}
.bar i{display:block;border-radius:8px 8px 3px 3px;background:linear-gradient(180deg,#38bdf8,#6d4aff);min-height:3px;}
.bar b{font-size:.82rem;color:#fff;font-weight:800;margin-bottom:3px;} .bar small{font-size:.72rem;color:#cbd5e1;font-weight:600;margin-top:4px;}
.sight{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--line);
  border-radius:14px;padding:10px 14px;margin-bottom:8px;transition:transform .12s ease,border-color .12s ease;}
.sight:hover{transform:translateY(-1px);border-color:#38bdf8;}
.sight .sd{flex:1;min-width:0;} .sight b{color:#fff;font-weight:800;} .sight small{display:block;color:#cbd5e1;font-weight:600;font-size:.8rem;}
.sight .tm{font-variant-numeric:tabular-nums;color:#93c5fd;font-weight:800;font-size:.86rem;white-space:nowrap;}
.box{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 18px;margin-bottom:12px;}
.box h4{margin:0 0 6px;color:#fff;font-size:1rem;font-weight:800;}

@media (max-width:900px){
  .kpis,.badge-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
  .fgrid.arr,.fgrid.dep{grid-template-columns:52px minmax(0,1.25fr) minmax(0,1.15fr) auto;gap:8px;padding:0 12px;}
  .fgrid .c-dl,.fgrid .c-gate,.fgrid .alogo,.fcols>div:last-child{display:none;}
  .fgrid.dep.fcols>div:nth-child(4){display:none;}
  .c-pl .fg{font-size:1.1rem;}
  .clock{font-size:1.5rem;}
}
/* Yenileme ve sekme geçişlerinde ekranın soluklaşmasını (dimming) engelle */
[data-stale="true"],[data-testid="stAppViewBlockContainer"] [data-stale="true"],div[data-stale="true"],iframe[data-stale="true"]{
  opacity:1 !important;filter:none !important;transition:none !important;
}
</style>
"""

def _cls(x):
  return re.sub(r"[^A-Za-z0-9]", "", str(x or ""))

def fids_logo_css(logos):
  """Her havayolu logosu sayfada yalnızca bir kez (CSS sınıfı olarak) gömülür."""
  rules = [f".alogo.k-{_cls(k)}{{background-image:url('{v}');}}" for k, v in logos.items() if v]
  return f"<style>{''.join(rules)}</style>" if rules else ""
