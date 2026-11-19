"""Free Bing web translation through the canonical host."""

import os
import threading


_clients = threading.local()


def translate_text(text: str, *, from_language: str, to_language: str, timeout: float) -> str:
    client = getattr(_clients, "bing", None)
    if client is None:
        # The package geolocates at import time unless a default is set.
        os.environ.setdefault("translators_default_region", "CN")
        from translators.server import Bing

        # cn.bing.com redirects the translation POST with 301. Requests
        # follows it as a GET and the adapter receives an empty response.
        client = _clients.bing = Bing(server_region="EN")
    return client.bing_api(
        text,
        from_language=from_language,
        to_language=to_language,
        timeout=timeout,
        if_print_warning=False,
    )
