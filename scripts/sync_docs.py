#!/usr/bin/env python3
"""Atlas Radar - Dokümantasyon Senkronizasyon ve Bütünlük Otomasyonu.

Bu betik:
1. Projedeki tüm sayfaları, çekirdek modülleri, araçları, iş akışlarını ve fonksiyonları inceler.
2. README.md dosyasının eksiksizliğini doğrular (Doküman Bekçisi standardı).
3. CLAUDE.md ve README.md belgelerini tek bir ana kaynak (README.md) etrafında birleştirir
   ve her güncelleme sonrası otomatik olarak senkronize tutar.

Kullanım:
  python3 scripts/sync_docs.py         # Dokümantasyonu doğrula ve CLAUDE.md'yi senkronize et
  python3 scripts/sync_docs.py --check # Yalnızca bütünlük ve senkronizasyon kontrolü yap (CI)
"""

import argparse
import ast
import glob
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README_FILE = ROOT / "README.md"
CLAUDE_FILE = ROOT / "CLAUDE.md"

REQUIRED_SECTIONS = [
    ("Sayfalar", ["Terminal", "Gözlem Defteri", "Anı Defteri", "Radar"]),
    ("Çekirdek Modüller", [
        "Radar.py", "radar_db.py", "radar_fids.py",
        "radar_config.py", "radar_styles.py", "radar_auth.py", "radar_motion.py"
    ]),
    ("Araçlar & Betikler", ["scripts/manage_db.py", "scripts/sync_fids.py", "scripts/sync_docs.py"]),
    ("İş Akışları (Workflows)", ["tests.yml", "sync_data.yml", "Kurulum"]),
    ("Veritabanı & data Dalı", ["data dalı", "radar.sql", "radar.db", "iterdump", "schema.sql"]),
    ("Anı Defteri Modülü", ["Anı Defteri", "Uçak Avcısı", "Rozet", "Rütbe"]),
    ("Bekçi Sistemleri", ["Kapsam Bekçisi", "Doküman Bekçisi"]),
]


def check_readme_completeness(readme_text: str) -> list[str]:
  """README.md dosyasının gerekli tüm konuları kapsadığını doğrular."""
  missing = []
  lower_text = readme_text.lower()
  for category, items in REQUIRED_SECTIONS:
    for item in items:
      if item.lower() not in lower_text:
        missing.append(f"[{category}] -> {item}")
  return missing


def generate_claude_md(readme_text: str) -> str:
  """README.md'den geliştirici ve AI asistan odaklı CLAUDE.md dosyasını otomatik üretir."""
  header = (
      "# CLAUDE.md — Atlas'ın Uçak Gözlem Kulesi (Geliştirici & Mimari Özeti)\n\n"
      "> 🤖 **Otomasyon Notu:** Bu dosya `README.md` ana belgesi ile birleştirilmiştir ve "
      "`scripts/sync_docs.py` tarafından otomatik olarak senkronize tutulur. "
      "Değişikliklerinizi doğrudan `README.md` üzerinde yapınız.\n\n"
      "---\n\n"
  )
  return header + readme_text


def sync_documentation(check_only: bool = False) -> int:
  if not README_FILE.exists():
    print(f"❌ Hata: {README_FILE} bulunamadı!")
    return 1

  readme_text = README_FILE.read_text(encoding="utf-8")
  missing = check_readme_completeness(readme_text)

  if missing:
    print("❌ Doküman Bekçisi Uyarısı: README.md içerisinde eksik konular var:")
    for m in missing:
      print(f"  • {m}")
    if check_only:
      return 1
  else:
    print("✅ README.md tüm sayfa, çekirdek modül, araç, workflow ve Anı Defteri kapsamını eksiksiz içeriyor.")

  claude_content = generate_claude_md(readme_text)

  if check_only:
    if not CLAUDE_FILE.exists() or CLAUDE_FILE.read_text(encoding="utf-8") != claude_content:
      print("⚠️ CLAUDE.md ve README.md senkronize değil! 'python3 scripts/sync_docs.py' çalıştırın.")
      return 1
    print("✅ CLAUDE.md ve README.md tam senkronize durumda.")
    return 0

  # Otomatik güncelle
  CLAUDE_FILE.write_text(claude_content, encoding="utf-8")
  print(f"✅ CLAUDE.md başarıyla README.md ile birleştirildi ve güncellendi ({len(claude_content)} bayt).")
  return 0


def main():
  p = argparse.ArgumentParser(description="Dokümantasyon Senkronizasyon ve Bütünlük Otomasyonu")
  p.add_argument("--check", action="store_true", help="Yalnızca senkronizasyonu ve kapsamı doğrula")
  args = p.parse_args()
  return sync_documentation(check_only=args.check)


if __name__ == "__main__":
  sys.exit(main())
