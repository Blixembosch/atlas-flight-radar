"""
test_functional_modular.py
  Atlas'ın Uçak Gözlem Kulesi - Modülerlik, Görsel Bütünlük ve Fonksiyonel Test Paketi.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import radar
import radar_config as config
import radar_styles as styles



class TestFunctionalModular(unittest.TestCase):

  def test_radar_config_integrity(self):
    """radar_config içindeki kritik sabitlerin doğruluğu."""
    self.assertEqual(config.AIRPORT_ICAO, "EHEH")
    self.assertIn("H47", config.SPECIAL_TYPES)
    self.assertIn("CH47", config.SPECIAL_TYPES)
    self.assertIn("GRZ", config.SPECIAL_PREFIXES)
    self.assertEqual(config.SPECIAL_PREFIXES["GRZ"][3], "MIL")
    self.assertEqual(config.COVERAGE["📡 Yakın · 50 km"][0], 50)
    self.assertIn("TRA", config.AIRLINES)

  def test_radar_backward_compatibility(self):
    """Radar.py'ın modüllerden sabitleri doğru re-export ettiği ve geriye uyumlu olduğu."""
    self.assertEqual(radar.AIRPORT_ICAO, config.AIRPORT_ICAO)
    self.assertIs(radar.SPECIAL_TYPES, config.SPECIAL_TYPES)
    self.assertIs(radar.SPECIAL_PREFIXES, config.SPECIAL_PREFIXES)
    self.assertIs(radar.AIRCRAFT_TYPES, config.AIRCRAFT_TYPES)
    self.assertIs(radar.COVERAGE, config.COVERAGE)
    self.assertEqual(radar.CSS, styles.CSS)

  def test_visual_styles_and_toolbar_consistency(self):
    """CSS içinde hem radar hem terminal için toolbar ve kart stillerinin varlığı."""
    self.assertIn(".st-key-toolbar", styles.CSS)
    self.assertIn(".fcard", styles.CSS)
    self.assertIn(".sight", styles.CSS)
    self.assertIn(".term-head", styles.CSS)
    self.assertIn("border-color:#38bdf8", styles.CSS)  # hover efekti

  def test_radar_helpers(self):
    """Yön pusulası ve çocuk karşılaştırma fonksiyonları testi."""
    lbl = config.compass_label(0)
    self.assertIn("Kuzey", lbl)
    
    cap = config.seat_text("TRA", "B738")
    self.assertEqual(cap, "~189 koltuk")

    kid = config.kid_comparison({"speed": 350, "alt_ft": 3000})
    self.assertIn("kat", kid)
    self.assertIn("Eyfel", kid)

  def test_special_flight_enrichment(self):
    """Özel ve askeri uçuşların rota aranmadan da doğru tanımlandığı."""
    store = {}
    states = [
        # icao24, callsign, origin_country, time_pos, last_contact, lon, lat, baro_alt, on_ground, vel, track, vert_rate
        ["480849", "GRZLY18", "Netherlands", 0, 0, 5.40, 51.50, 1000, False, 120, 90, 0],
    ]
    # GRZLY18 -> prefix GRZ veya tcode H47
    flights = radar.build_flights(states, store, overflights=False, coverage_km=50, show_unknown=False)
    self.assertEqual(len(flights), 1)
    f = flights[0]
    self.assertEqual(f["dest"]["iata"], "GÖREV")
    self.assertEqual(f["dir"], "ARR")

  def test_transit_overflights_coverage_scaling(self):
    """Kapsama alanı 100/200 km seçildiğinde ve Üstümüzden geçenler açıkken transit uçakların elenmediği."""
    # 51.50, 6.00: evden yaklaşık 45 km uzaklıkta, 32.000 ft transit uçuş
    # 52.00, 6.00: evden yaklaşık 70 km uzaklıkta, 35.000 ft transit uçuş
    s_45km = ["abc1", "DLH123", "Germany", 0, 0, 6.00, 51.50, 9750, False, 220, 90, 0]
    s_70km = ["abc2", "KLM456", "Netherlands", 0, 0, 6.00, 52.00, 10600, False, 240, 90, 0]

    # overflights=False iken yüksek irtifa transit uçuşlar dahil edilmez
    cands_off = radar._candidates([s_45km, s_70km], overflights=False, coverage_km=200)
    self.assertEqual(len(cands_off), 0)

    # overflights=True ve coverage_km=50 iken 45 km'deki transit uçak dahil edilir (eski 30 km kısıtında eleniyordu)
    cands_50 = radar._candidates([s_45km, s_70km], overflights=True, coverage_km=50)
    self.assertEqual(len(cands_50), 1)
    self.assertEqual(cands_50[0][2], "transit")

    # overflights=True ve coverage_km=200 iken her iki transit uçak da dahil edilir
    cands_200 = radar._candidates([s_45km, s_70km], overflights=True, coverage_km=200)
    self.assertEqual(len(cands_200), 2)
    self.assertEqual(cands_200[0][2], "transit")
    self.assertEqual(cands_200[1][2], "transit")


if __name__ == "__main__":

  ok = unittest.main(exit=False).result.wasSuccessful()
  sys.exit(0 if ok else 1)
