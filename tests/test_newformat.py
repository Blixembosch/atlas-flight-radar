import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import radar_fids as F
T=lambda l:{"utc":"x","local":l}
js={"departures":[{"departure":{"scheduledTime":T("2026-10-13 18:05+02:00"),"revisedTime":T("2026-10-13 18:20+02:00"),"runwayTime":T("2026-10-13 18:25+02:00"),"gate":"B3","quality":[]},
 "arrival":{"airport":{"icao":"LEMG","iata":"AGP","name":"Malaga","municipalityName":"Málaga","countryCode":"ES"},"scheduledTime":T("2026-10-13 21:00+02:00")},
 "number":"HV 5101","callSign":"TRA5101","status":"Departed","codeshareStatus":"IsOperator","isCargo":False,"aircraft":{"reg":"PH-HXA","model":"Boeing 737-800"},"airline":{"name":"Transavia","iata":"HV","icao":"TRA"}}],
"arrivals":[{"departure":{"airport":{"icao":"LTFJ","iata":"SAW","name":"Sabiha","municipalityName":"Istanbul","countryCode":"TR"},"scheduledTime":T("2026-10-13 14:00+02:00"),"gate":"X"},
 "arrival":{"scheduledTime":T("2026-10-13 18:10+02:00"),"revisedTime":T("2026-10-13 18:12+02:00"),"terminal":"1"},
 "number":"PC 1","status":"Expected","codeshareStatus":"IsOperator","isCargo":False,"aircraft":{"model":"A320"},"airline":{"name":"Pegasus","iata":"PC"}}]}
r=F.parse_adb(js); d=[x for x in r if x["direction"]=="DEP"][0]; a=[x for x in r if x["direction"]=="ARR"][0]
ok = len(r)==2 and d["sched_local"]=="2026-10-13T18:05" and d["other_iata"]=="AGP" and d["gate"]=="B3" and d["actual_local"].endswith("18:25") and d["est_local"].endswith("18:20")
ok = ok and a["sched_local"]=="2026-10-13T18:10" and a["other_iata"]=="SAW" and a["terminal"]=="1" and a["gate"] is None
print("OK   yeni biçim" if ok else "FAIL yeni biçim", r)
print("\nBAŞARISIZ:", "yok" if ok else "yeni biçim"); sys.exit(0 if ok else 1)
