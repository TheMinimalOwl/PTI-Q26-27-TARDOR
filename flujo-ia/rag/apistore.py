"""Almacen sobre la API del equipo de API/BD (VM 1, por el Cloudflare tunnel).

Con `RAG_STORE=api` el RAG no lee el indice local ni se conecta a
PostgreSQL: recupera los productos (con su **ultimo precio**) de la API
publica de la VM 1 (`RAG_BD_API_URL`, la URL del quick tunnel).

Dos caminos de recuperacion, en este orden:

1. `POST /products/search-vector` con el embedding de la consulta
   (pgvector en la BD). Es el camino previsto en el contrato de la API.
   Si la API desplegada aun no lo tiene (404/405), se recuerda y se pasa
   al segundo camino sin volver a probarlo en cada pregunta.
2. `GET /products/search?q=` con las palabras clave de la pregunta (la
   API exige que aparezcan **todas** en el nombre: si no sale nada se van
   quitando palabras), y despues **re-ranking semantico** aqui: se
   embeben los candidatos con el mismo modelo del RAG y se ordenan por
   coseno contra la consulta. Los vectores se cachean por id.

`ApiStore` expone la interfaz que usan el Retriever y la cadena QA
(`search_query`, `search`, `get`, `docs`, `__len__`).
"""

from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

from . import config
from .ingest import Product
from .store import Hit, l2_normalize

_TIMEOUT = 90  # una busqueda sin cache en la BD tarda ~35 s (con Redis, <1 s)
_CANDIDATOS = 100  # maximo de /products/search
_UNIDADES = ("l", "kg", "ud")
_BONUS_CABEZA = 0.03  # las unidades con productos comparables

# Palabras que no ayudan a buscar por nombre de producto (la API hace AND
# de todas las palabras de `q`, asi que una sola de estas lo vacia todo).
_STOP = set(
    """
    a al algo algun alguna alguno algunos ante con contra cual cuales cuanto
    cuanta cuantos cuantas cuesta cuestan cuestas de del desde donde el ella
    en entre es esta estan este esto hay la las le lo los mas me mi mucho muy
    ni no o para pero por porque precio precios que quien se si sin sobre su
    sus tambien te tiene tienen tu un una uno unos unas vale valen y ya
    barato barata baratos baratas caro cara caros caras mejor peor
    comprar compro compra producto productos supermercado supermercados
    litro litros kilo kilos euro euros eur dame dime quiero busco buscar
    encontrar tienda tiendas cadena cadenas oferta ofertas hoy actual
    """.split()
)


class ApiError(RuntimeError):
    """La API de la BD no responde o devuelve un error."""


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def palabras_clave(texto: str) -> list[str]:
    """Palabras de la pregunta utiles para buscar por nombre."""
    limpio = _sin_acentos(texto.lower())
    palabras = re.findall(r"[a-z0-9ñ]+", limpio)
    return [p for p in palabras if len(p) >= 3 and p not in _STOP]


def _doc(item: dict) -> dict:
    """Producto de la API -> el dict de producto que usa el RAG."""
    precio = item.get("price") or {}
    cadena = item.get("chain") or {}
    total = precio.get("total")
    up = precio.get("unit_price")
    return {
        "id": str(item.get("id")),
        "name": item.get("name", ""),
        "chain": cadena.get("slug", "") if isinstance(cadena, dict) else str(cadena),
        "category": item.get("category", "") or "",
        "unit": item.get("unit"),
        "url": item.get("url", "") or "",
        "total": str(total) if total is not None else None,
        "unit_price": str(up) if up is not None else None,
        "unit_src": precio.get("unit_src", "-") or "-",
        "size": item.get("size", "-") or "-",
        "size_format": item.get("size_format", "") or "",
        "wh": precio.get("store", "default") or "default",
        "ts": str(precio.get("observed_on", "")),
        "similarity": item.get("similarity"),
    }


class ApiStore:
    """Recuperacion contra la API de la BD, con re-ranking local."""

    def __init__(self, embedder, base_url: str | None = None):
        self.embedder = embedder
        self.base_url = (base_url or config.BD_API_URL).rstrip("/")
        if not self.base_url:
            raise ApiError(
                "falta la URL de la API de la BD: define RAG_BD_API_URL "
                "(infra/tunnel-up.sh --url en la VM 1)"
            )
        self.dim = embedder.spec.dim
        self._vectores: dict[str, np.ndarray] = {}
        self._vistos: dict[str, dict] = {}
        self._cadenas: list[dict] | None = None
        self._search_vector: bool | None = None  # None = sin probar

    # -- HTTP ---------------------------------------------------------------
    def _get(self, ruta: str, params: dict | None = None):
        try:
            resp = requests.get(self.base_url + ruta, params=params, timeout=_TIMEOUT)
        except requests.RequestException as e:
            raise ApiError(f"no responde la API de la BD ({e.__class__.__name__})") from e
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise ApiError(f"GET {ruta}: HTTP {resp.status_code}")
        return resp.json()

    def ping(self) -> dict:
        datos = self._get("/health")
        if not datos or datos.get("status") != "ok" or not datos.get("db"):
            raise ApiError(f"la API de la BD no esta sana: {datos}")
        return datos

    # -- recuperacion ---------------------------------------------------------
    def _por_vector(self, qv: np.ndarray, top_k: int, filters) -> list[dict] | None:
        """`POST /products/search-vector`; None si la API no lo tiene."""
        if self._search_vector is False:
            return None
        body: dict = {"embedding": [float(x) for x in np.asarray(qv).reshape(-1)], "top_k": top_k}
        if filters is not None:
            cadenas = filters.chains or ([filters.chain] if filters.chain else None)
            if cadenas:
                body["chains"] = cadenas
            if filters.max_total is not None:
                body["max_price"] = float(filters.max_total)
            if filters.max_unit_price is not None:
                body["max_unit_price"] = float(filters.max_unit_price)
        try:
            resp = requests.post(
                self.base_url + "/products/search-vector", json=body, timeout=_TIMEOUT
            )
        except requests.RequestException as e:
            # Corte puntual (tunel, pod reiniciando): esta vez por texto.
            print(f"aviso: search-vector no responde ({e.__class__.__name__}); se busca por texto")
            return None
        if resp.status_code in (404, 405):
            self._search_vector = False  # la API desplegada no lo tiene
            return None
        if resp.status_code >= 500:
            # 5xx / 530 de Cloudflare (origen caido un momento): por texto.
            print(f"aviso: search-vector HTTP {resp.status_code}; se busca por texto")
            return None
        if resp.status_code >= 400:
            raise ApiError(f"POST /products/search-vector: HTTP {resp.status_code}")
        self._search_vector = True
        return [_doc(it) for it in resp.json().get("items", [])]

    def _por_texto(self, texto: str, filters) -> list[dict]:
        """`GET /products/search` con las palabras clave (AND), relajando."""
        palabras = palabras_clave(texto)
        cadena = filters.chain if filters is not None else None
        # Un nombre de cadena en la pregunta es un filtro, no una palabra del
        # nombre del producto ("leche entera mercadona").
        slugs = {d["chain"] for d in self.docs}
        nombradas = [p for p in palabras if p in slugs]
        palabras = [p for p in palabras if p not in slugs]
        if not cadena and len(nombradas) == 1:
            cadena = nombradas[0]
        if not palabras:
            return []
        while palabras:
            # La API ordena por precio unitario dentro de la unidad mas
            # frecuente: con "aceite oliva" esa es kg (snacks con aceite) y el
            # aceite (l) no entraria en los 100. Se pide cada unidad en paralelo.
            def pedir(unit: str) -> list[dict]:
                params = {"q": " ".join(palabras), "limit": _CANDIDATOS, "unit": unit}
                if cadena:
                    params["chain"] = cadena
                datos = self._get("/products/search", params) or {}
                return datos.get("items") or []

            with ThreadPoolExecutor(max_workers=len(_UNIDADES)) as pool:
                listas = list(pool.map(pedir, _UNIDADES))
            vistos: set = set()
            docs = []
            for items in listas:
                for it in items:
                    if it.get("id") not in vistos:
                        vistos.add(it.get("id"))
                        docs.append(_doc(it))
            if docs:
                return docs
            palabras = palabras[:-1]
        return []

    def _vectores_de(self, docs: list[dict]) -> np.ndarray:
        faltan = [d for d in docs if d["id"] not in self._vectores]
        if faltan:
            textos = [Product.from_dict(d).embed_text for d in faltan]
            vecs = self.embedder.encode(textos, is_query=False)
            for d, v in zip(faltan, vecs):
                self._vectores[d["id"]] = np.asarray(v, dtype=np.float32)
        return np.vstack([self._vectores[d["id"]] for d in docs])

    def search_query(
        self,
        texto: str,
        qv: np.ndarray,
        k: int = 5,
        where=None,
        exclude_ids: set[str] | None = None,
        filters=None,
    ) -> list[Hit]:
        """Top-k para una consulta de texto (con su vector ya calculado)."""
        if where is None and filters is not None:
            where = filters.matches
        docs = self._por_vector(qv, max(k * 4, 20), filters)
        if docs is None:
            docs = self._por_texto(texto, filters)
        if exclude_ids:
            docs = [d for d in docs if d["id"] not in exclude_ids]
        if where is not None:
            docs = [d for d in docs if where(d)]
        if not docs:
            return []
        for d in docs:
            self._vistos[d["id"]] = d
        q = l2_normalize(np.asarray(qv, dtype=np.float32))[0]
        if all(d.get("similarity") is not None for d in docs):
            # search-vector: la BD ya da el coseno (mismo modelo y vectores).
            scores = np.array([float(d["similarity"]) for d in docs], dtype=np.float32)
        else:
            scores = l2_normalize(self._vectores_de(docs)) @ q
        # Las similitudes de e5 son muy planas (0,85-0,86 entre "aceite de
        # oliva" y "grissini al aceite de oliva"): si el nombre empieza por la
        # primera palabra clave (el sustantivo de la consulta), es ese producto
        # y no uno que solo lo lleva de ingrediente.
        clave = palabras_clave(texto)
        if clave:
            cabeza = clave[0]
            bonus = np.array(
                [_BONUS_CABEZA if _sin_acentos(d["name"].lower()).startswith(cabeza) else 0.0 for d in docs],
                dtype=np.float32,
            )
            scores = scores + bonus
        orden = np.argsort(-scores)[:k]
        return [Hit(doc=docs[i], score=float(scores[i]), rank=r + 1) for r, i in enumerate(orden)]

    def search(self, query, k: int = 5, where=None, exclude_ids=None, filters=None) -> list[Hit]:
        """Solo con vector (sin texto): requiere `search-vector` en la API."""
        docs = self._por_vector(query, max(k * 4, 20), filters)
        if docs is None:
            raise ApiError(
                "la API de la BD no tiene POST /products/search-vector: "
                "sin el texto de la consulta no se puede recuperar"
            )
        return self.search_query("", query, k=k, where=where, exclude_ids=exclude_ids, filters=filters)

    # -- lectura --------------------------------------------------------------
    def get(self, product_id: str) -> dict | None:
        if not str(product_id).isdigit():
            return self._vistos.get(str(product_id))
        datos = self._get(f"/products/{product_id}")
        if not datos:
            return None
        doc = _doc(datos)
        self._vistos[doc["id"]] = doc
        return doc

    @property
    def docs(self) -> list[dict]:
        """Una fila por cadena (lo que usan `_cadenas` de la QA y equivalencia)."""
        if self._cadenas is None:
            try:
                cadenas = self._get("/chains") or []
            except ApiError:
                cadenas = []
            self._cadenas = [{"chain": c.get("slug")} for c in cadenas if c.get("slug")]
        return self._cadenas

    def filter(self, where) -> list[dict]:
        return [d for d in self._vistos.values() if where(d)]

    def __len__(self) -> int:
        return len(self._vistos)
