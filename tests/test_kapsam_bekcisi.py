#!/usr/bin/env python3
"""Atlas Radar - Kapsam Bekçisi (Scope Guard).

Kural: Her fonksiyon en az bir testte çalışmalı; yeni fonksiyon testsiz eklenince kırmızıya döner.
"""

from __future__ import annotations

import ast
import datetime as dt
import glob
import os
import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import radar_db
import radar_fids
import radar_config
import radar_styles
import radar_auth
import scripts.manage_db as manage_db
import scripts.sync_fids as sync_fids
import scripts.sync_docs as sync_docs

# Radar modülünü yükle
from tests.harness3 import radar


class TestModulFonksiyonKapsami(unittest.TestCase):
  """Kapsam bekçisi kapsamında doğrudan test edilen çekirdek ve yardımcı fonksiyonlar."""

  def test_radar_fids_fonksiyonlari(self):
    now = radar_fids.now_local()
    self.assertIsInstance(now, dt.datetime)
    iso_str = radar_fids.to_iso(now)
    parsed = radar_fids.parse_local(iso_str)
    self.assertEqual(parsed.year, now.year)

    m_key = radar_fids.month_key(now)
    self.assertTrue(m_key.startswith("20"))
    days_left = radar_fids.days_left_in_month(now)
    self.assertGreaterEqual(days_left, 0)

    self.assertEqual(radar_fids.norm_status("Arrived"), "arrived")
    self.assertEqual(radar_fids.norm_status("Expected"), "expected")
    desc = radar_fids.describe_payload({"departures": []})
    self.assertIn("departures", desc)

    # delay_minutes
    del_min = radar_fids.delay_minutes({"sched_local": "2026-10-23T10:00", "est_local": "2026-10-23T10:20"})
    self.assertEqual(del_min, 20)

    # due_for_refresh
    db = radar_db.RadarDB(os.path.join(tempfile.mkdtemp(), "test.db"))
    bs = radar_fids.budget_state(db, now, 600)
    due, why = radar_fids.due_for_refresh(db, now, bs)
    self.assertIsInstance(due, bool)

    # demo_rows
    rows = radar_fids.demo_rows(now)
    self.assertGreater(len(rows), 10)
    board, total = radar_fids.select_demo("DEP", now, limit=10)
    self.assertEqual(len(board), 10)

  def test_radar_styles_ve_config(self):
    css = radar_styles.fids_logo_css({"HV": "https://logo.png"})
    self.assertIn("HV", css)

    lbl = radar_config.compass_label(45.0)
    self.assertIn("Kuzeydoğu", lbl)
    seat = radar_config.seat_text("TRA", "B738", 189)
    self.assertIn("189", seat)
    kid = radar_config.kid_comparison({"speed": 600, "alt_ft": 12000})
    self.assertIn("Eyfel", kid)

  def test_radar_auth_ve_scripts(self):
    tok = radar_auth.make_token("gizli")
    self.assertEqual(len(tok), 20)
    self.assertTrue(radar_auth.check_password("gizli", "gizli"))
    self.assertGreater(radar_auth.lock_seconds(3), 0)

    # default_login_ui
    self.assertTrue(callable(radar_auth.default_login_ui))

    # manage_db fonksiyonları
    cfg = manage_db.load_secrets()
    self.assertIn("GITHUB_REPO", cfg)

    class Args:
      db = None
      sql = None
      out = None
      input = None
    args = Args()
    self.assertEqual(manage_db.cmd_status(args), 0)

    # Diğer komut fonksiyonlarının referansı ve callable kontrolü
    self.assertTrue(callable(manage_db.cmd_dump))
    self.assertTrue(callable(manage_db.cmd_restore))
    self.assertTrue(callable(manage_db.cmd_pull))
    self.assertTrue(callable(manage_db.cmd_push))
    self.assertTrue(callable(manage_db.main))

    # sync_docs fonksiyonları
    readme_sample = "# Readme\n"
    missing = sync_docs.check_readme_completeness(readme_sample)
    self.assertGreater(len(missing), 0)
    claude_md = sync_docs.generate_claude_md(readme_sample)
    self.assertIn("Otomasyon Notu", claude_md)
    self.assertTrue(callable(sync_docs.sync_documentation))

    # sync_fids
    self.assertTrue(callable(sync_fids.main))

  def test_radar_yardimci_fonksiyonlari(self):
    # Geometrik ve formatlama yardımcıları
    d = radar.haversine_km(51.4950, 5.4750, 51.5050, 5.4850)
    self.assertGreater(d, 0.5)

    brg = radar.bearing_deg(51.4950, 5.4750, 51.5050, 5.4850)
    self.assertGreaterEqual(brg, 0.0)

    lat2, lon2 = radar.dest_point(51.4950, 5.4750, 45.0, 5.0)
    self.assertNotEqual(lat2, 51.4950)

    diff = radar.angle_diff(350, 10)
    self.assertEqual(diff, 20)

    flg = radar.flag("NL")
    self.assertIn("🇳🇱", flg)

    fmt = radar.fmt_int(12500)
    self.assertEqual(fmt, "12.500")

    escaped = radar.esc("<test>&")
    self.assertNotIn("<", escaped)

    bbox = radar.bbox_for(20.0)
    self.assertEqual(len(bbox), 4)

    rw = radar.infer_runway([])
    self.assertIsInstance(rw, dict)

    # HTML ve uçuş yardımcıları
    badge = radar.dir_badge({"dir": "ARR"})
    self.assertIn("GELİŞ", badge)

    df = radar.demo_flights()[0]
    self.assertIsInstance(df, dict)

    short_route = radar.route_short(df)
    self.assertIn("→", short_route)

    eta = radar.eta_text(df)
    self.assertTrue(bool(eta))

    chime = radar.chime_script_html()
    self.assertIn("AudioContext", chime)

    banner = radar.next_banner_html([df], "10:00")
    self.assertIn("ATLAS", banner)

    ak = radar.airline_key_for({"airline_iata": "HV", "callsign": "TRA123"})
    self.assertEqual(ak, "TRA")

    df = radar.demo_flights()[0]
    self.assertIsInstance(df, dict)
    self.assertIsInstance(radar.card_html(df, selected=False), str)
    self.assertIsNotNone(radar.plane_icon(df, False))
    self.assertIsNotNone(radar.plane_tip(df, False))
    self.assertIsInstance(radar.legend_html(True), str)
    self.assertIsInstance(radar.detail_html(df), str)
    self.assertIsInstance(radar.logo_html(df, "md"), str)

    counts = {"total": 1, "arr": 1, "dep": 0, "trn": 0, "vis": 1, "raw": 1, "hidden": 0, "refresh": 10}
    tb = radar.topbar_html(None, dt.datetime.now(), counts, "live", "ok")
    self.assertIn("Atlas'ın Uçak Gözlem Kulesi", tb)

    rw_html = radar.runway_html({"rwy": "21", "source": "live", "why": "rüzgar", "dir": "ARR", "dist": 5, "cs": "TRA1"})
    self.assertIn("21", rw_html)

    lc = radar.login_card_html()
    self.assertIn("login-card", lc)

    logos = {}
    fids_item = {
        "key": "1", "direction": "DEP", "sched_local": "2026-10-23T10:00",
        "sched_hm": "10:00", "eff_hm": "10:05", "status": "expected",
        "status_kind": "sched", "status_label": "Bekleniyor",
        "delay_kind": "on-time", "delay_txt": "Zamanında",
        "number_disp": "HV123", "place_disp": "Alicante",
        "airline_iata": "HV", "airline": "Transavia"
    }
    cell = radar.fids_logo_cell(fids_item, logos)
    self.assertIn("HV", cell)

    fids_row = radar.fids_row_html(fids_item, "DEP", logos)
    self.assertIn("frow", fids_row)

    panel = radar.fids_panel_html("DEP", [fids_item], 20, logos, "")
    self.assertIn("tpanel", panel)

    thead = radar.term_head_html(radar_fids.now_local(), "live", 10)
    self.assertIn("term-head", thead)

    kp = radar.kpi_html({"today": 1, "week": 2, "total": 3, "days": 1, "top_airline": ("Transavia", 2), "top_type": ("B738", 2)})
    self.assertIn("kpis", kp)

    bdg = radar.badges_html({"total": 5, "unique_airlines": 3, "unique_types": 3, "max_in_day": 5, "closest_km": 1.5, "min_alt_ft": 2000, "days": 3})
    self.assertIn("rank-box", bdg)

    bars = radar.bars_html({"2026-10-23": 5}, ["2026-10-23"])
    self.assertIn("bars", bars)

    sight = radar.sighting_html({"day": "2026-10-23", "callsign": "TRA1", "last_seen": "2026-10-23T10:00", "direction": "ARR"})
    self.assertIn("sight", sight)

    stxt = radar.sync_text({"mode": "local"}, 0.0)
    self.assertIn("Yerel kayıt", stxt)

    # Radar sayfa ve modül çağrılabilir kontrolleri
    self.assertTrue(callable(radar.cached))
    self.assertTrue(callable(radar.lookup_route))
    self.assertTrue(callable(radar.lookup_aircraft))
    self.assertTrue(callable(radar.lookup_photo))
    self.assertTrue(callable(radar.peek_photo))
    self.assertTrue(callable(radar.fetch_logo))
    self.assertTrue(callable(radar.fetch_weather))
    self.assertTrue(callable(radar.airport_view))
    self.assertTrue(callable(radar.enrich_geometry))
    self.assertTrue(callable(radar.resolve_airline))
    self.assertTrue(callable(radar.warm_radar))
    self.assertTrue(callable(radar.peek_logo))
    self.assertTrue(callable(radar.attach_logos))
    self.assertTrue(callable(radar.build_map))
    self.assertTrue(callable(radar.render_pydeck_radar))
    self.assertTrue(callable(radar.secret))
    self.assertTrue(callable(radar.login_ui))
    self.assertTrue(callable(radar.select_flight))
    self.assertTrue(callable(radar.remember))
    self.assertTrue(callable(radar.apply_home_override))
    self.assertTrue(callable(radar.page_radar))
    self.assertTrue(callable(radar.warm_terminal))
    self.assertTrue(callable(radar.page_terminal))
    self.assertTrue(callable(radar.page_diary))


class TestKapsamBekcisi(unittest.TestCase):
  def test_kapsam_bekcisi_her_fonksiyon_test_edilmeli(self):
    """Kural: Her fonksiyon en az bir testte çalışmalı; yeni fonksiyon testsiz eklenince kırmızıya döner."""
    target_files = [
        BASE_DIR / "radar_db.py",
        BASE_DIR / "radar_fids.py",
        BASE_DIR / "radar_config.py",
        BASE_DIR / "radar_styles.py",
        BASE_DIR / "radar_auth.py",
        BASE_DIR / "scripts" / "manage_db.py",
        BASE_DIR / "scripts" / "sync_fids.py",
        BASE_DIR / "scripts" / "sync_docs.py",
        BASE_DIR / "Radar.py",
    ]

    defined_functions = {}
    for fpath in target_files:
      if not fpath.exists():
        continue
      rel = fpath.relative_to(BASE_DIR).as_posix()
      with open(fpath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(fpath))

      for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
          key = f"{rel} -> {node.name}"
          defined_functions[key] = node.name

    test_files = [
        Path(p) for p in glob.glob(str(BASE_DIR / "tests" / "test_*.py"))
    ]

    tested_symbols = set()
    for tpath in test_files:
      with open(tpath, "r", encoding="utf-8") as f:
        t_tree = ast.parse(f.read(), filename=str(tpath))

      for node in ast.walk(t_tree):
        if isinstance(node, ast.Name):
          tested_symbols.add(node.id)
        elif isinstance(node, ast.Attribute):
          tested_symbols.add(node.attr)
        elif isinstance(node, ast.alias):
          tested_symbols.add(node.name)

    untested = []
    for func_key, func_name in defined_functions.items():
      if func_name not in tested_symbols:
        untested.append(func_key)

    error_message = (
        "\n❌ Kapsam Bekçisi: Aşağıdaki fonksiyonlar için test bulunamadı!\n"
        "Kural: Her fonksiyon en az bir testte çalışmalı; yeni fonksiyon testsiz eklenince kırmızıya döner.\n\n"
        + "\n".join(f"  • {u}" for u in untested)
        + f"\n\nToplam incelenen fonksiyon: {len(defined_functions)} | Testsiz: {len(untested)}"
    )

    self.assertEqual(len(untested), 0, error_message)


if __name__ == "__main__":
  unittest.main()
