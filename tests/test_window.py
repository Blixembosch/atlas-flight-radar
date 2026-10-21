import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import datetime, timedelta
import radar_fids as F
import radar_db as R, tempfile
now = F.now_local()
db = R.RadarDB(os.path.join(tempfile.mkdtemp(), "db", "radar.db"))
def row(k, d, mins, status="Expected", est=None, act=None):
  t = lambda m: F.to_iso(now + timedelta(minutes=m))
  return dict(key=k, direction=d, number=k, sched_local=t(mins), est_local=t(est) if est is not None else None,
              actual_local=t(act) if act is not None else None, status=F.norm_status(status))
db.upsert_fids([row("old", "DEP", -120, "Departed", act=-115), row("just", "DEP", -20, "Departed", act=-15),
                row("now", "DEP", 5, "Boarding"), row("soon", "DEP", 25), row("later", "DEP", 90),
                row("late", "DEP", -30, "Expected", est=20),   # planlanan geçmiş ama tahmini 20 dk sonra
                row("landed", "ARR", -40, "Arrived", act=-35), row("far", "ARR", 200)], F.to_iso(now))
dep, _ = F.select_board(db, "DEP", now, window=(60, 30)); arr, _ = F.select_board(db, "ARR", now, window=(60, 30))
got = [r["key"] for r in dep]
ok = got == ["just", "now", "late", "soon"] or sorted(got) == sorted(["just", "now", "late", "soon"])
ok = ok and [r["key"] for r in arr] == ["landed"]
all_, _ = F.select_board(db, "DEP", now, limit=50)
ok = ok and "later" in [r["key"] for r in all_]

# Gece saatlerinde (-60..+30 dk içinde hiç uçuş yokken) ekran boş kalmamalı, son/sıradaki uçuşları göstermeli
db_night = R.RadarDB(os.path.join(tempfile.mkdtemp(), "db", "radar_night.db"))
db_night.upsert_fids([row("evening", "DEP", -180, "Departed", act=-175), row("morning", "DEP", 480, "Expected")], F.to_iso(now))
night_dep, _ = F.select_board(db_night, "DEP", now, window=(60, 30))
ok = ok and [r["key"] for r in night_dep] == ["evening", "morning"]

print(("OK   " if ok else "FAIL ") + "şimdi penceresi ve gece geri dönüşü", got, [r["key"] for r in arr])
print("\nBAŞARISIZ:", "yok" if ok else "pencere"); sys.exit(0 if ok else 1)
