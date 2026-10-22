"""Atlas Flight - Kapsamlı Sayfa Geçiş Akışı ve Performans Test Paketi
Kullanıcı gereksinimleri:
1) Sayfa sırası: Terminal (1), Gözlem Defteri (2), Radar (3)
2) Gözlem Defteri arayüzü Terminal ile tam uyumlu; sarı tonlar kaldırılmış
3) Sayfalar arası akış ultra hızlı (<0.15 sn) ve kesintisiz
4) 20 hızlı ardışık geçişte bellek/iş parçacığı kilitlenmesi veya yavaşlama olmaması
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar, Net, SF, row, ap

FAILS = []
def ck(n, c, i=""):
    print(("OK   " if c else "FAIL ") + n + (f"   [{i}]" if (i and not c) else ""))
    if not c: FAILS.append(n)

def set_ss(k, v): fake.session_state._force(k, v)
def timed():
    t0 = time.time()
    H.run()
    return time.time() - t0

# ------------------------------------------------------------------ 1) Kurulum ve Giriş
PAGE_TERM = "🛫 Terminal"
PAGE_DIARY = "📒 Gözlem Defteri"
PAGE_RADAR = "🛰️ Radar"

ck("Sayfa sıralaması doğru: Terminal -> Gözlem Defteri -> Radar",
   radar.PAGES == [PAGE_TERM, PAGE_DIARY, PAGE_RADAR], radar.PAGES)
ck("Açılış sayfası Terminal", radar.DEFAULT_PAGE == PAGE_TERM)

H.reset_app({"APP_PASSWORD": "p", "AERODATABOX_KEY": "test-key-123"})
H.run(); set_ss("Şifre", "p"); fake.pressed = {"Giriş yap"}; H.run()
radar.join_background(timeout=10)

# ------------------------------------------------------------------ 2) Tasarım ve Renk Doğrulaması (Sarı Ton Kontrolü)
set_ss("page", PAGE_DIARY); H.run()
diary_html = "\n".join(fake.md)
import re
rank_css = re.search(r"\.rank-box\{[^}]+\}", radar.CSS).group(0)
rank_title_css = re.search(r"\.rank-title\{[^}]+\}", radar.CSS).group(0)
bcard_css = re.search(r"\.bcard\.on\{[^}]+\}", radar.CSS).group(0)
ck("Gözlem Defteri açıldı ve rütbe kutusu var", "rank-box" in diary_html and "Atlas'ın Rütbesi:" in diary_html)
ck("Gözlem Defteri rütbe kutusunda sarı ton yok", "250,204,21" not in rank_css and "#fde047" not in rank_title_css and "250,204,21" not in bcard_css)
ck("Gözlem Defteri rütbe başlığında şık gök mavisi (#38bdf8) mevcut", "#38bdf8" in rank_title_css)
ck("Avionik alt durum çubuğu (.status-info) Gözlem Defteri'nde mevcut", "status-info" in diary_html)

set_ss("page", PAGE_TERM); H.run()
term_html = "\n".join(fake.md)
ck("Avionik alt durum çubuğu Terminal sayfasında mevcut", "status-info" in term_html)

set_ss("page", PAGE_RADAR); H.run()
radar_html = "\n".join(fake.md)
ck("Avionik alt durum çubuğu Radar sayfasında mevcut", "status-info" in radar_html)

# ------------------------------------------------------------------ 3) Sayfalar Arası Birebir Geçiş Hızı Benchmarkı
BUDGET_TRANSITION = 0.20  # saniye

# A) Terminal -> Gözlem Defteri
set_ss("page", PAGE_TERM); H.run()
set_ss("page", PAGE_DIARY); dt_t_to_d = timed()
ck(f"Terminal → Gözlem Defteri anında ({dt_t_to_d*1000:.1f} ms < 200ms)", dt_t_to_d < BUDGET_TRANSITION, dt_t_to_d)

# B) Gözlem Defteri -> Radar
set_ss("page", PAGE_RADAR); dt_d_to_r = timed()
ck(f"Gözlem Defteri → Radar anında ({dt_d_to_r*1000:.1f} ms < 200ms)", dt_d_to_r < BUDGET_TRANSITION, dt_d_to_r)

# C) Radar -> Gözlem Defteri
set_ss("page", PAGE_DIARY); dt_r_to_d = timed()
ck(f"Radar → Gözlem Defteri anında ({dt_r_to_d*1000:.1f} ms < 200ms)", dt_r_to_d < BUDGET_TRANSITION, dt_r_to_d)

# D) Gözlem Defteri -> Terminal
set_ss("page", PAGE_TERM); dt_d_to_t = timed()
ck(f"Gözlem Defteri → Terminal anında ({dt_d_to_t*1000:.1f} ms < 200ms)", dt_d_to_t < BUDGET_TRANSITION, dt_d_to_t)

# E) Terminal -> Radar
set_ss("page", PAGE_RADAR); dt_t_to_r = timed()
ck(f"Terminal → Radar anında ({dt_t_to_r*1000:.1f} ms < 200ms)", dt_t_to_r < BUDGET_TRANSITION, dt_t_to_r)

# F) Radar -> Terminal
set_ss("page", PAGE_TERM); dt_r_to_t = timed()
ck(f"Radar → Terminal anında ({dt_r_to_t*1000:.1f} ms < 200ms)", dt_r_to_t < BUDGET_TRANSITION, dt_r_to_t)

# ------------------------------------------------------------------ 4) Stres Testi: 24 Ardışık Hızlı Geçişte Donma Yok
times = []
pages_cycle = [PAGE_TERM, PAGE_DIARY, PAGE_RADAR] * 8  # 24 geçiş
for p in pages_cycle:
    set_ss("page", p)
    t = timed()
    times.append(t)

avg_t = sum(times) / len(times)
max_t = max(times)
ck(f"24 ardışık geçişte ortalama süre mükemmel ({avg_t*1000:.1f} ms < 50ms)", avg_t < 0.05, avg_t)
ck(f"24 ardışık geçişte en yavaş çizim bütçe içinde ({max_t*1000:.1f} ms < 150ms)", max_t < 0.15, max_t)

# ------------------------------------------------------------------ 5) Özet
print("\n--- Sayfa Geçiş Performans Özeti ---")
print(f"  Terminal → Defter: {dt_t_to_d*1000:.1f} ms")
print(f"  Defter → Radar   : {dt_d_to_r*1000:.1f} ms")
print(f"  Radar → Defter   : {dt_r_to_d*1000:.1f} ms")
print(f"  Defter → Terminal: {dt_d_to_t*1000:.1f} ms")
print(f"  Ortalama (24 tur): {avg_t*1000:.1f} ms")
print(f"  En Yavaş (p100)  : {max_t*1000:.1f} ms")

print("\nBAŞARISIZ:", FAILS if FAILS else "yok")
sys.exit(1 if FAILS else 0)
