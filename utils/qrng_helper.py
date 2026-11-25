import secrets
from urllib.parse import urlsplit

import requests
import streamlit as st


def _fallback_prng(n_bits: int) -> str:
    return ''.join(str(secrets.randbits(1)) for _ in range(n_bits))


def _valid_url(value) -> str | None:
    try:
        url = (value or "").strip().rstrip("/")
        parts = urlsplit(url)

        if parts.scheme in ("http", "https") and parts.hostname:
            return url

    except (AttributeError, ValueError):
        pass

    return None


@st.cache_data(ttl=300, show_spinner=False)
def _resolve_base_url_from_sheet() -> str | None:
    try:
        from google.oauth2 import service_account
        import gspread

        config = st.secrets

        if "gcp" not in config:
            return None

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        creds = service_account.Credentials.from_service_account_info(
            config["gcp"],
            scopes=scope
        )

        client = gspread.authorize(creds)

        sheet = client.open(
            config.get("GOOGLE_SHEET_NAME", "qrng_result_logger")
        ).worksheet(
            config.get("META_URL", "meta_url")
        )

        # Prefer the direct QRNG API URL from A2.
        direct_url = _valid_url(sheet.acell("A2").value)

        if direct_url:
            return direct_url

        # Legacy compatibility: use A1 if A2 is unavailable.
        raw = _valid_url(sheet.acell("A1").value)

        if not raw:
            return None

        if raw.endswith("/ngrok-url"):
            response = requests.get(raw, timeout=5)
            response.raise_for_status()
            return _valid_url(response.text)

        return raw

    except Exception:
        return None


def get_qrng_bits_with_source(n_bits: int) -> tuple[str, bool]:
    """Return (bits, from_qrng)."""

    url = _resolve_base_url_from_sheet()

    if not url:
        st.warning("QRNG URL unavailable – using local PRNG.")
        return _fallback_prng(n_bits), False

    try:
        response = requests.post(
            f"{url}/get_bits/",
            json={"n_bits": n_bits},
            timeout=20
        )

        response.raise_for_status()
        bits = response.json()["bits"]

        if (
            not isinstance(bits, str)
            or len(bits) != n_bits
            or set(bits) - {"0", "1"}
        ):
            raise ValueError("QRNG returned an invalid bit string")

        return bits, True

    except Exception:
        st.warning("QRNG offline or invalid response – using local PRNG.")
        return _fallback_prng(n_bits), False


def get_qrng_bits_from_api(n_bits: int) -> str:
    """Backward-compatible bit-string API."""
    return get_qrng_bits_with_source(n_bits)[0]