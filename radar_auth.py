"""
Atlas'ın Uçak Gözlem Kulesi - uygulama şifresi.

* Şifre koddan değil Streamlit secrets içindeki APP_PASSWORD değerinden okunur.
* APP_PASSWORD tanımlı DEĞİLSE uygulama KİLİTLİ kalır (güvenli varsayılan); yerel geliştirmede
  RADAR_ALLOW_NO_PASSWORD = true yazılırsa şifresiz açılır.
* Karşılaştırma sabit zamanlıdır; art arda yanlış denemede kısa bekleme uygulanır.
* Giriş yapılmadan hiçbir API çağrısı / otomatik yenileme başlamaz (çağıran taraf `gate()` False
  dönünce `st.stop()` çağırmalıdır).
"""
from __future__ import annotations

import hmac
import time

MAX_FREE_TRIES = 3          # bu kadar yanlıştan sonra bekleme başlar
LOCK_STEP_S = 5             # her ek yanlış denemede +5 sn
LOCK_MAX_S = 60


def _norm(s) -> bytes:
  return str(s or "").strip().encode("utf-8")


def check_password(entered, expected) -> bool:
  """Sabit zamanlı karşılaştırma. Beklenen şifre boşsa her zaman False."""
  exp = _norm(expected)
  if not exp:
    return False
  return hmac.compare_digest(_norm(entered), exp)


def lock_seconds(fails: int) -> int:
  if fails < MAX_FREE_TRIES:
    return 0
  return min(LOCK_MAX_S, (fails - MAX_FREE_TRIES + 1) * LOCK_STEP_S)


def gate(st, secret, login_ui=None, now=time.time) -> bool:
  """True ise içeri alınmıştır. False ise giriş ekranı çizilmiştir; çağıran `st.stop()` yapmalı.

  st: streamlit modülü (testte sahte). secret(name, default) -> str.
  login_ui(st, state) -> girilen şifre (None = form gönderilmedi). Verilmezse sade bir form çizilir.
  """
  ss = st.session_state
  if ss.get("auth_ok"):
    return True

  expected = secret("APP_PASSWORD", "")
  if not expected:
    if str(secret("RADAR_ALLOW_NO_PASSWORD", "")).strip().lower() in ("1", "true", "yes", "evet"):
      ss["auth_ok"] = True
      return True
    state = {"locked": 0, "error": "", "misconfigured": True}
    (login_ui or default_login_ui)(st, state)
    return False

  fails = int(ss.get("auth_fails", 0))
  until = float(ss.get("auth_until", 0.0))
  remaining = max(0, int(round(until - now())))
  state = {"locked": remaining, "error": ss.get("auth_error", ""), "misconfigured": False}
  entered = (login_ui or default_login_ui)(st, state)

  if entered is None:
    return False
  if remaining > 0:
    return False

  if check_password(entered, expected):
    ss["auth_ok"] = True
    ss["auth_fails"] = 0
    ss["auth_until"] = 0.0
    ss["auth_error"] = ""
    st.rerun()
    return True

  fails += 1
  ss["auth_fails"] = fails
  wait = lock_seconds(fails)
  ss["auth_until"] = now() + wait
  ss["auth_error"] = ("Şifre yanlış." if wait == 0
                      else f"Şifre yanlış. {wait} sn sonra tekrar deneyin.")
  st.rerun()
  return False


def logout(st):
  for k in ("auth_ok", "auth_fails", "auth_until", "auth_error"):
    st.session_state.pop(k, None)


def default_login_ui(st, state):
  """Sade giriş formu (Radar.py kendi süslü sürümünü verir)."""
  if state.get("misconfigured"):
    st.error("Uygulama şifresi tanımlı değil. Streamlit secrets içine APP_PASSWORD ekleyin.")
    return None
  with st.form("login_form", clear_on_submit=True):
    pw = st.text_input("Şifre", type="password")
    sent = st.form_submit_button("Giriş")
  if state.get("error"):
    st.error(state["error"])
  return pw if sent else None
