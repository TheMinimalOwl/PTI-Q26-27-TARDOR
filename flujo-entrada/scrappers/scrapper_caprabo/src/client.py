"""Cliente HTTP de capraboacasa.com.

No hay API JSON: el catalogo se lee del HTML de las paginas de categoria, que el servidor
genera completo (20 productos por pagina, `?pageNumber=N`). La web pone en cookies la
tienda online que sirve el catalogo (`supermarket.ali.shop`).

Uso academico y sin animo de lucro: una pasada nocturna, peticiones de una en una con
pausa entre ellas y reintentos con espera creciente.
"""
import os
import time

import requests

TIMEOUT = 30
RETRIES = 3
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; academic-price-research)")


class Site:
    def __init__(self, host: str, delay: float):
        self.base = f"https://{host}"
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "es-ES,es;q=0.9",
        })
        self._last = 0.0

    def get(self, path_or_url: str) -> str:
        """GET con pausa minima entre peticiones y reintentos. Lanza si no hay manera."""
        url = path_or_url if path_or_url.startswith("http") else self.base + path_or_url
        last: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.session.get(url, timeout=TIMEOUT)
                r.raise_for_status()
                return r.text
            except requests.RequestException as e:
                last = e
                print(f"   {url} intento {attempt}/{RETRIES}: {e}", flush=True)
                if attempt < RETRIES:
                    time.sleep(10 * attempt)
        raise RuntimeError(f"no he podido leer {url}: {last}")

    def shop(self) -> tuple[str, str]:
        """(id, nombre) de la tienda online que sirve el catalogo, de las cookies."""
        c = self.session.cookies
        return c.get("supermarket.ali.shop") or "default", c.get("supermarket.ali.shopName") or ""
