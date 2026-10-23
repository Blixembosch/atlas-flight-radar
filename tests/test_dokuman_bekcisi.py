#!/usr/bin/env python3
"""Atlas Radar - Doküman Bekçisi (Doc Guard).

Kural: Bu README.md her sayfayı, çekirdek modülü, aracı, workflow'u ve
Anı Defteri modülünü/sekmesini kapsamalı. Eksik varsa kırmızıya döner.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from scripts.sync_docs import check_roadmap_completeness

README_PATH = BASE_DIR / "README.md"
CLAUDE_PATH = BASE_DIR / "CLAUDE.md"
ROADMAP_PATH = BASE_DIR / "ROADMAP.md"


class TestDokumanBekcisi(unittest.TestCase):
  def test_dokuman_bekcisi_readme_kapsami(self):
    """README.md dosyasının tüm sayfa, modül, servis, workflow ve Anı Defterini kapsadığını doğrular."""
    self.assertTrue(README_PATH.exists(), "README.md dosyası bulunamadı!")
    content = README_PATH.read_text(encoding="utf-8")

    # 1. Sayfa Kapsamı
    required_pages = [
        "Terminal",
        "Gözlem Defteri",
        "Anı Defteri",  # Kullanıcı kuralı
        "Radar",
    ]

    # 2. Çekirdek Modüller ve Servisler
    required_modules = [
        "Radar.py",
        "radar_db.py",
        "radar_fids.py",
        "radar_config.py",
        "radar_styles.py",
        "radar_auth.py",
        "radar_motion.py",
    ]

    # 3. Araçlar ve Betikler (Scripts)
    required_tools = [
        "scripts/manage_db.py",
        "scripts/sync_fids.py",
        "scripts/sync_docs.py",
        "ROADMAP.md",
    ]

    # 4. İş Akışları (Workflows)
    required_workflows = [
        "tests.yml",
        "sync_data.yml",
        "Kurulum",
    ]

    # 5. Kalıcı Veri & data Dalı Ayrımı
    required_data = [
        "data dalı",
        "radar.sql",
        "radar.db",
        "iterdump",
        "schema.sql",
    ]

    # 6. Anı Defteri & Gözlem Modülü
    required_diary = [
        "Anı Defteri",
        "Uçak Avcısı",
        "Rozet",
        "Rütbe",
    ]

    # 7. Bekçi Sistemleri
    required_guards = [
        "Kapsam Bekçisi",
        "Doküman Bekçisi",
    ]

    all_checks = {
        "Sayfalar": required_pages,
        "Çekirdek Modüller": required_modules,
        "Araçlar & Betikler": required_tools,
        "İş Akışları (Workflows)": required_workflows,
        "Veri & Kalıcılık": required_data,
        "Anı Defteri & Gözlem": required_diary,
        "Bekçi Sistemleri": required_guards,
    }

    missing_items = []
    lower_content = content.lower()
    for category, items in all_checks.items():
      for item in items:
        if item.lower() not in lower_content:
          missing_items.append(f"[{category}] -> {item}")

    error_message = (
        "\n❌ Doküman Bekçisi: README.md içerisinde eksik kalan bölümler tespit edildi!\n"
        "Kural: Bu README.md her sayfayı, çekirdek modülü, aracı, workflow'u ve Anı Defteri modülünü/sekmesini kapsamalıdır.\n\n"
        + "\n".join(f"  • {m}" for m in missing_items)
        + f"\n\nEksik öğe sayısı: {len(missing_items)}"
    )

    self.assertEqual(len(missing_items), 0, error_message)

  def test_claude_ve_readme_senkronizasyonu(self):
    """CLAUDE.md ile README.md dosyalarının senkronize olduğunu doğrular."""
    self.assertTrue(CLAUDE_PATH.exists(), "CLAUDE.md dosyası bulunamadı!")
    claude_text = CLAUDE_PATH.read_text(encoding="utf-8")
    readme_text = README_PATH.read_text(encoding="utf-8")
    self.assertIn("Otomasyon Notu", claude_text, "CLAUDE.md otomasyon başlığı içermeli!")
    self.assertIn(readme_text.splitlines()[0], claude_text, "CLAUDE.md README içeriğini kapsamalı!")

  def test_roadmap_md_kapsami(self):
    """ROADMAP.md dosyasının var olduğunu, sürüm tablosunu ve gelecek planlarını kapsadığını doğrular."""
    self.assertTrue(ROADMAP_PATH.exists(), "ROADMAP.md dosyası bulunamadı!")
    roadmap_text = ROADMAP_PATH.read_text(encoding="utf-8")
    self.assertIn("# 🗺️ Atlas Flight Radar", roadmap_text)
    self.assertIn("📌 Sürüm Özeti", roadmap_text)
    self.assertIn("🚀 Sürüm Detayları", roadmap_text)
    self.assertIn("🔮 Gelecek Yol Haritası", roadmap_text)

    # Önemli sürüm işaretleri kontrolü
    for ver in ["v0.5.2", "v0.5.1", "v0.5.0", "v0.4.9", "v0.4.0", "v0.1.0"]:
      self.assertIn(ver, roadmap_text, f"ROADMAP.md içinde {ver} sürümü bulunmalı!")

    # Temel modül ve özellik kontrolü
    for feature in ["Terminal", "Gözlem Defteri", "Anı Defteri", "Radar", "Pydeck", "Kapsam Bekçisi", "Doküman Bekçisi"]:
      self.assertIn(feature.lower(), roadmap_text.lower(), f"ROADMAP.md içinde {feature} bulunmalı!")

    # sync_docs check_roadmap_completeness fonksiyonunu test et
    missing = check_roadmap_completeness(roadmap_text)
    self.assertEqual(len(missing), 0, f"ROADMAP.md eksik bölümler: {missing}")
    self.assertTrue(len(check_roadmap_completeness("eksik")) > 0)


if __name__ == "__main__":
  unittest.main()
