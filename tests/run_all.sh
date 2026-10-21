#!/usr/bin/env bash
# Tüm birim, fonksiyonel ve performans testlerini çalıştırır (Streamlit/GitHub/AeroDataBox sahte; internet gerekmez).
set -eo pipefail
cd "$(dirname "$0")/.."
for t in test_db_auth test_fids test_app test_radar_flow test_traffic test_async test_switch; do
  echo "== $t"
  out="$(python3 "tests/$t.py")"
  echo "$out" | grep -E "FAIL|❌|BAŞARISIZ|SONUÇ" || true
done
echo "TÜM BİRİM VE AKIŞ TESTLERİ GEÇTİ"
python3 tests/test_terminal_diag.py
python3 tests/test_newformat.py
python3 tests/test_window.py
python3 tests/test_default_page.py
python3 tests/test_warm.py
python3 tests/test_perf.py

