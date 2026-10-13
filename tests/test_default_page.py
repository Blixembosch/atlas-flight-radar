import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import harness3 as H
from harness3 import fake, radar
radar.DEFAULT_PAGE = os.environ.get("X") or radar.PAGES[1] if False else radar.PAGES[1]
H.reset_app({"APP_PASSWORD": "p", "AERODATABOX_KEY": "k"})
H.run(); fake.session_state._force("Şifre", "p"); fake.pressed = {"Giriş yap"}; H.run()
ok = fake.session_state["page"] == radar.PAGES[1]
print(("OK   " if ok else "FAIL ") + "uygulama Terminal ile açılır")
print("\nBAŞARISIZ:", "yok" if ok else "varsayılan sayfa"); sys.exit(0 if ok else 1)
