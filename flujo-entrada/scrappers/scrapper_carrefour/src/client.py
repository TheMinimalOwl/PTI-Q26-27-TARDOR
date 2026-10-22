import os
import requests

TIMEOUT = 15

def fetch(url: str) -> tuple[int | None, str, dict]:
    headers = {
        "User-Agent": os.getenv(
            "USER_AGENT",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        return r.status_code, r.text, dict(r.headers)
    except requests.RequestException as e:
        return None, "", {"error": str(e)}
