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



if __name__ == "__main__":
  ok = unittest.main(exit=False).result.wasSuccessful()
  sys.exit(0 if ok else 1)
