"""Cliente HTTP de la tienda online de bonÀrea (www.bonarea-online.com).

La web carga los productos con una llamada interna que devuelve JSON (encontrada con
Playwright, viendo lo que pide el navegador):

    GET  /categories/<slug>/13_300_010_010_020          -> cookie de sesion (ASP.NET)
    POST /ca/shop/ShoppingBody   reference=13*300*010*010*020
         -> {"articles": [...productos de la categoria...], "nivells": [arbol completo], ...}

- Una llamada por categoria hoja devuelve todos sus productos (no hay paginacion).
- La misma respuesta trae el arbol completo de categorias (`nivells`): con la primera
  llamada ya se sabe que recorrer.
- No hace falta login; basta la cookie de sesion anonima.

Uso academico y sin animo de lucro: una pasada nocturna, peticiones de una en una con
pausa entre ellas y reintentos con espera creciente.
"""
import os
import time

import requests

BASE = "https://www.bonarea-online.com"
BODY_URL = f"{BASE}/ca/shop/ShoppingBody"
FIRST = "13*300*010*010*020"  # una hoja cualquiera para arrancar (Alimentacio > Aus > Gall dindi)
TIMEOUT = 60
RETRIES = 3
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; academic-price-research)")


def _page_url(ref: str) -> str:
    return f"{BASE}/categories/x/{ref.replace('*', '_')}"


class Client:
    def __init__(self, delay: float):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "ca-ES,ca;q=0.9,es;q=0.8",
        })
        self._last = 0.0

    def _wait(self) -> None:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def _retry(self, what: str, fn):
        last: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            self._wait()
            try:
                return fn()
            except (requests.RequestException, ValueError, KeyError) as e:
                last = e
                print(f"   {what} intento {attempt}/{RETRIES}: {e}", flush=True)
                if attempt < RETRIES:
                    time.sleep(10 * attempt)
        raise RuntimeError(f"no he podido leer {what}: {last}")

    def start(self) -> None:
        """Abre la sesion anonima (cookies) como haria el navegador."""
        def go():
            r = self.session.get(_page_url(FIRST), timeout=TIMEOUT)
            r.raise_for_status()
        self._retry("sesion", go)

    def body(self, ref: str) -> dict:
        """Respuesta de ShoppingBody para una categoria (`13*300*010*010*020`)."""
        def go():
            r = self.session.post(BODY_URL, data={"reference": ref}, timeout=TIMEOUT, headers={
                "X-Requested-With": "XMLHttpRequest", "Referer": _page_url(ref),
                "Accept": "application/json, text/javascript, */*; q=0.01",
            })
            r.raise_for_status()
            d = r.json()
            if not isinstance(d.get("articles"), list):
                raise ValueError(f"respuesta sin articles: {r.text[:200]}")
            return d
        return self._retry(f"ShoppingBody {ref}", go)


def leaves(nivells: list[dict], exclude: list[str]) -> list[tuple[str, list[str]]]:
    """(identificador, ruta de nombres) de cada categoria hoja, sin las de primer nivel
    excluidas."""
    out: list[tuple[str, list[str]]] = []

    def walk(n: dict, path: list[str]) -> None:
        path = path + [n.get("descripcio", "")]
        children = n.get("children") or []
        if not children and n.get("identifier"):
            out.append((n["identifier"], path))
        for c in children:
            walk(c, path)

    for top in nivells:
        if top.get("descripcio", "").strip().lower() in exclude:
            continue
        walk(top, [])
    return out
