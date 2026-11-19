"""Wire defaults for Bilibili's public Index-Translate API."""

import ssl

API_URL = "https://index-translate.bilibili.com/v1"
USER_AGENT = "Index-Translate-Client/1.0"
ANONYMOUS_KEY = "no_key_required"


def is_public_url(url: object) -> bool:
    return str(url or "").strip().lower().rstrip("/") == API_URL


def tls_context() -> ssl.SSLContext:
    # Match urllib in the official client: use system CAs with verification enabled.
    return ssl.create_default_context()


def openai_headers(api_key: str) -> dict:
    """Match the official UA and omit placeholder auth in per-request headers."""
    headers = {"User-Agent": USER_AGENT}
    if not api_key or api_key == ANONYMOUS_KEY:
        from openai import Omit

        headers["Authorization"] = Omit()
    return headers
