import requests

TIMEOUT = 15

def fetch_json(url: str) -> tuple[int | None, dict]:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT)
        if r.status_code != 200:
            return r.status_code, {}
        return r.status_code, r.json()
    except requests.RequestException:
        return None, {}
