"""Cliente HTTP del buscador de Condis (compraonline.condis.es).

La web de Condis no sirve el catalogo ella misma: lo pide al buscador Empathy.co, una API
JSON publica que no necesita sesion. Es lo mismo que hace el navegador:

    GET https://api.empathy.co/search/v1/query/condis/browse
        ?browseField=section&browseValue=Bebidas&store=718&lang=es&rows=500&start=0

- `store`: tienda cuyo catalogo y precios se ven. Sin iniciar sesion la web usa la 718.
- `browseField=store` da el total de la tienda y sus secciones (facet `facetSection`).
- La API no deja pasar de `start` 2400, asi que se recorre por secciones (la mayor tiene
  ~1.600 productos).

Uso academico y sin animo de lucro: una pasada nocturna, peticiones de una en una con pausa
entre ellas y reintentos con espera creciente.
"""
import os
import time

import requests

BASE = "https://api.empathy.co/search/v1/query/condis/browse"
TIMEOUT = 30
RETRIES = 3
MAX_START = 2400  # limite de la API para `start`
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; academic-price-research)")


class Client:
    def __init__(self, store: str, delay: float, rows: int = 500):
        self.store, self.delay, self.rows = store, delay, rows
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Origin": "https://compraonline.condis.es",
            "Referer": "https://compraonline.condis.es/",
        })
        self._last = 0.0

    def browse(self, field: str, value: str, start: int = 0, rows: int | None = None) -> dict:
        """Una pagina de `browse`. Lanza si no hay manera: el scraper tiene que fallar de
        forma visible, no devolver 0 productos."""
        params = {"browseField": field, "browseValue": value, "store": self.store, "lang": "es",
                  "rows": self.rows if rows is None else rows, "start": start}
        last: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.session.get(BASE, params=params, timeout=TIMEOUT)
                r.raise_for_status()
                catalog = r.json().get("catalog")
                if not isinstance(catalog, dict):
                    raise ValueError(f"respuesta sin catalog: {r.text[:200]}")
                return catalog
            except (requests.RequestException, ValueError) as e:
                last = e
                print(f"   {field}={value} start={start} intento {attempt}/{RETRIES}: {e}", flush=True)
                if attempt < RETRIES:
                    time.sleep(10 * attempt)
        raise RuntimeError(f"no he podido leer {field}={value} start={start}: {last}")

    def sections(self) -> tuple[int, dict[str, int]]:
        """(total de la tienda, {seccion: productos})."""
        c = self.browse("store", self.store, rows=0)
        facet = next((f for f in c.get("facets", []) if f.get("facet") == "facetSection"), {})
        return c.get("numFound", 0), {v["id"]: v["count"] for v in facet.get("values", [])}

    def section(self, name: str) -> list[dict]:
        """Todos los productos de una seccion, pagina a pagina."""
        out, start = [], 0
        while True:
            c = self.browse("section", name, start)
            content = c.get("content") or []
            out.extend(content)
            start += self.rows
            if not content or start >= c.get("numFound", 0):
                return out
            if start >= MAX_START:
                raise RuntimeError(f"la seccion {name} pasa de {MAX_START} productos: hay que partirla")
