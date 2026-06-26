# utils/qrng_helper.py
import requests, secrets, hashlib
import streamlit as st

def _fallback_prng(n_bits: int) -> str:
    return ''.join(str(secrets.randbits(1)) for _ in range(n_bits))

@st.cache_data(ttl=300, show_spinner=False)
def _resolve_base_url_from_sheet() -> str | None:
    try:
        from google.oauth2 import service_account
        import gspread
    except Exception:
        return None

    try:
        SECRETS = st.secrets if "gcp" in st.secrets else None
    except Exception:
        SECRETS = None
    if not SECRETS:
        return None

    gcp_creds = SECRETS["gcp"]
    GOOGLE_SHEET_NAME = SECRETS.get("GOOGLE_SHEET_NAME", "qrng_result_logger")
    META_URL = SECRETS.get("META_URL", "meta_url")

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = service_account.Credentials.from_service_account_info(gcp_creds, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open(GOOGLE_SHEET_NAME).worksheet(META_URL)

    raw = (sheet.acell("A1").value or "").strip().rstrip("/")
    if not raw:
        return None

    base = raw
    if raw.endswith("/ngrok-url") or raw.endswith("ngrok-url"):
        r = requests.get(raw, timeout=5)
        r.raise_for_status()
        base = (r.text or "").strip().rstrip("/")

    if not (base.startswith("http://") or base.startswith("https://")):
        return None
    return base

def get_qrng_bits_from_api(n_bits: int) -> str:
    """
    Always resolve base URL from Google Sheet (secrets). If anything fails,
    return a local PRNG fallback.
    """
    url = _resolve_base_url_from_sheet()
    if not url:
        st.warning("QRNG URL unavailable – using local PRNG.")
        return _fallback_prng(n_bits)

    try:
        resp = requests.post(f"{url.rstrip('/')}/get_bits/", json={"n_bits": n_bits}, timeout=20)
        resp.raise_for_status()
        return resp.json()["bits"]
    except Exception:
        st.toast("QRNG offline — falling back to local PRNG")
        return _fallback_prng(n_bits)
