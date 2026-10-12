#!/usr/bin/env bash
# Tüm testleri çalıştırır (Streamlit/GitHub/AeroDataBox sahte; internet gerekmez).
set -e
cd "$(dirname "$0")/.."
for t in test_db_auth test_fids test_app test_radar_flow test_traffic; do
  echo "== $t"; python3 tests/$t.py | grep -E "FAIL|❌|BAŞARISIZ|SONUÇ" || true
  python3 tests/$t.py >/dev/null
done
echo "TÜM TESTLER GEÇTİ"
