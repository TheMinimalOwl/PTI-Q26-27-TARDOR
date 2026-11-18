"""Almacen en PostgreSQL + pgvector (y utilidades de consulta).

`PgStore` implementa la misma interfaz que `VectorStore` (`search`, `get`,
`filter`, `docs`, `__len__`), asi que el Retriever y la cadena QA no notan
el cambio: con `RAG_STORE=pg` la busqueda es una consulta SQL con el
operador de distancia de coseno de pgvector (`<=>`); con `RAG_STORE=local`
(defecto) sigue siendo el indice numpy de siempre.

Decisiones de diseno (ver docs/04-despliegue.md):

- **Conexion por operacion**: corta y segura con Flask en modo hilo (una
  conexion compartida entre hilos no lo es). A la escala del prototipo
  (miles de filas) el coste es irrelevante.
- **Filtros como objeto**: `Filters.matches` es un callable de Python y no
  se puede mandar a SQL; el Retriever pasa `filters=` y aqui se traduce a
  `WHERE` con parametros (nada de formatos de cadena: sin inyeccion).
- **Esquema configurable**: tabla, columnas y vector se ajustan por
  entorno (`RAG_PG_TABLE`, `RAG_PG_COL_<CAMPO>`). Al usarlo se comprueba
  contra `information_schema` que existen: integrar la base del equipo es
  fijar variables, no reescribir codigo.
- **Fallback**: si la base no responde, `cargar_store` vuelve al indice
  local y el servicio sigue en pie (la demo nunca depende de la BD).
- **score** = `1 - distancia_coseno`, la misma semantica que el indice
  local (producto escalar de vectores normalizados).
"""

from __future__ import annotations

import re
from decimal import Decimal

import numpy as np

from . import config
from .indexer import load_index
from .retriever import Filters
from .store import Hit, VectorStore


class PgError(RuntimeError):
    """Problema conectando o consultando PostgreSQL."""


def conectar(dsn: str):
    """Abre una conexion a PostgreSQL.

    `psycopg` es dependencia opcional: si no esta instalado, el error
    explica como hacerlo (el servicio no lo necesita en modo local).
    """
    try:
        import psycopg
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise PgError(
            "falta psycopg: instala las dependencias con "
            "'pip install -r requirements.txt'"
        ) from e
    if not dsn:
        raise PgError(
            "falta la conexion: define RAG_PG_DSN "
            "(postgresql://usuario:clave@127.0.0.1:5432/base)"
        )
    try:
        return psycopg.connect(dsn)
    except Exception as e:
        raise PgError(f"no se pudo conectar a PostgreSQL: {e}") from e


def _id(nombre: str) -> str:
    """Valida un identificador de SQL (tabla/columna) y lo entrecomilla."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nombre or ""):
        raise PgError(f"nombre de tabla/columna no valido: {nombre!r}")
    return f'"{nombre}"'


def vector_texto(v) -> str:
    """Vector de numpy como literal pgvector (`[0.1,0.2,...]`)."""
    arr = np.asarray(v, dtype=np.float32).reshape(-1)
    return "[" + ",".join(repr(float(x)) for x in arr) + "]"


def _dim_de(v) -> int:
    """Dimension de un vector devuelto por la BD (texto u objeto)."""
    if isinstance(v, (str, bytes)):
        s = str(v).strip()
        if s.startswith("["):
            s = s[1:-1]
        return len(s.split(",")) if s.strip() else 0
    try:
        return len(v)
    except TypeError:
        return 0


def _a_texto(v):
    """Valor de fila -> valor de documento.

    Los documentos del indice local serializan los importes y el `id`
    como texto (`Product.to_dict`): para que una fila de la BD y una del
    indice local se vean igual en la API, los numericos pasan a `str`.
    """
    if v is None:
        return None
    if isinstance(v, (Decimal, float, int)) and not isinstance(v, bool):
        return str(v)
    return v


def _filtros_sql(f: Filters, cols: dict[str, str]) -> tuple[list[str], list]:
    """Traduce `Filters` a clausulas WHERE con parametros.

    `cols` es el mapa campo -> columna **existentes** en la tabla: si el
    esquema del equipo no tiene un campo por el que se filtra, se avisa en
    vez de devolver resultados sin filtrar (que seria peor).
    """
    clausulas: list[str] = []
    params: list = []

    def col(campo: str) -> str:
        if campo not in cols:
            raise PgError(
                f"no se puede filtrar por '{campo}': falta la columna "
                f"'{config.PG_COLUMNAS.get(campo, campo)}' en la tabla "
                f"(configurala con RAG_PG_COL_{campo.upper()})"
            )
        return _id(cols[campo])

    if f.chain:
        clausulas.append(f"{col('chain')} = %s")
        params.append(f.chain)
    if f.chains:
        clausulas.append(f"{col('chain')} = ANY(%s)")
        params.append(list(f.chains))
    if f.category:
        patron = (
            "%"
            + f.category.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "%"
        )
        clausulas.append(f"LOWER({col('category')}) LIKE %s ESCAPE '\\'")
        params.append(patron)
    for campo, op, valor in (
        ("total", ">=", f.min_total),
        ("total", "<=", f.max_total),
        ("unit_price", ">=", f.min_unit_price),
        ("unit_price", "<=", f.max_unit_price),
    ):
        if valor is not None:
            clausulas.append(f"{col(campo)}::numeric {op} %s")
            params.append(str(valor))
    return clausulas, params


class PgStore:
    """Store que consulta PostgreSQL en cada operacion (misma interfaz que
    `VectorStore` para el Retriever)."""

    def __init__(
        self,
        dsn: str | None = None,
        tabla: str | None = None,
        columnas: dict[str, str] | None = None,
        col_vector: str | None = None,
        conectar_fn=None,
    ):
        self.dsn = config.PG_DSN if dsn is None else dsn
        self.tabla = config.PG_TABLE if tabla is None else tabla
        self.columnas = dict(config.PG_COLUMNAS if columnas is None else columnas)
        self.col_vector = config.PG_COL_VECTOR if col_vector is None else col_vector
        self._conectar = conectar_fn or conectar
        self._existentes: set[str] | None = None  # columnas de la tabla
        self._cols: dict[str, str] | None = None  # campo -> columna
        self._docs_cache: list[dict] | None = None

    # -- infraestructura -------------------------------------------------
    def _consultar(self, sql: str, params: tuple | list = ()) -> list[tuple]:
        conn = self._conectar(self.dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
        except PgError:
            raise
        except Exception as e:
            raise PgError(f"error consultando PostgreSQL: {e}") from e
        finally:
            conn.close()

    def _columnas_reales(self) -> dict[str, str]:
        """Comprueba la tabla y devuelve campo -> columna existentes."""
        if self._cols is not None:
            return self._cols
        filas = self._consultar(
            "SELECT table_schema, column_name FROM information_schema.columns "
            "WHERE table_name = %s "
            "AND table_schema NOT IN ('pg_catalog', 'information_schema')",
            (self.tabla,),
        )
        if not filas:
            raise PgError(
                f"no existe la tabla '{self.tabla}' (RAG_PG_TABLE). "
                "¿Esta instalada la extension pgvector y creada la tabla?"
            )
        existentes = {nombre for _, nombre in filas}
        self._existentes = existentes
        cols = {campo: col for campo, col in self.columnas.items() if col in existentes}
        if not cols:
            raise PgError(
                f"ninguna columna configurada existe en '{self.tabla}'. "
                f"configuradas: {sorted(self.columnas.values())}; "
                f"en la tabla: {sorted(existentes)}. Ajusta RAG_PG_COL_*"
            )
        self._cols = cols
        return cols

    def _validar_vector(self) -> None:
        self._columnas_reales()
        assert self._existentes is not None
        if self.col_vector not in self._existentes:
            raise PgError(
                f"la tabla '{self.tabla}' no tiene la columna vector "
                f"'{self.col_vector}' (RAG_PG_COL_VECTOR)"
            )

    def _sel(self) -> str:
        cols = self._columnas_reales()
        return ", ".join(f'{_id(col)} AS "{campo}"' for campo, col in cols.items())

    @staticmethod
    def _doc(fila: tuple, campos: list[str]) -> dict:
        return {campo: _a_texto(valor) for campo, valor in zip(campos, fila)}

    # -- interfaz de store ----------------------------------------------
    def search(
        self,
        query: np.ndarray,
        k: int = 5,
        where=None,
        exclude_ids: set[str] | None = None,
        filters: Filters | None = None,
    ) -> list[Hit]:
        """Top-k por distancia de coseno en pgvector (`<=>`).

        El filtro viaja como objeto `Filters` (el `where` callable no se
        puede ejecutar en SQL): `Retriever` pasa los dos y aqui se usa
        `filters`.
        """
        if where is not None and filters is None:
            raise PgError(
                "PgStore no puede ejecutar un filtro en Python sobre SQL: "
                "pasa filters=Filters(...) (el Retriever ya lo hace)"
            )
        cols = self._columnas_reales()
        self._validar_vector()
        campos = list(cols)
        clausulas, params_f = (
            _filtros_sql(filters, cols) if filters is not None else ([], [])
        )
        v = _id(self.col_vector)
        t = _id(self.tabla)
        sql = (
            f"SELECT {self._sel()}, 1 - ({v} <=> %s) AS score FROM {t} "
            f"WHERE {v} IS NOT NULL"
        )
        params: list = [vector_texto(query)]
        if clausulas:
            sql += " AND " + " AND ".join(clausulas)
            params.extend(params_f)
        if exclude_ids:
            if "id" not in cols:
                raise PgError("exclude_ids necesita la columna id (RAG_PG_COL_ID)")
            sql += f" AND NOT ({_id(cols['id'])}::text = ANY(%s))"
            params.append([str(x) for x in exclude_ids])
        sql += f" ORDER BY {v} <=> %s LIMIT %s"
        params.extend([vector_texto(query), int(k)])

        filas = self._consultar(sql, params)
        hits: list[Hit] = []
        for i, fila in enumerate(filas):
            doc = self._doc(fila[: len(campos)], campos)
            score = float(fila[len(campos)])
            hits.append(Hit(doc=doc, score=score, rank=i + 1))
        return hits

    def get(self, product_id: str) -> dict | None:
        cols = self._columnas_reales()
        sql = (
            f"SELECT {self._sel()} FROM {_id(self.tabla)} "
            f"WHERE {_id(cols['id'])}::text = %s LIMIT 1"
        )
        filas = self._consultar(sql, (str(product_id),))
        return self._doc(filas[0], list(cols)) if filas else None

    def filter(self, where) -> list[dict]:
        return [d for d in self.docs if where(d)]

    @property
    def docs(self) -> list[dict]:
        """Todos los productos (sin vector), cacheados tras la 1a consulta."""
        if self._docs_cache is None:
            cols = self._columnas_reales()
            filas = self._consultar(f"SELECT {self._sel()} FROM {_id(self.tabla)}")
            self._docs_cache = [self._doc(f, list(cols)) for f in filas]
        return self._docs_cache

    def __len__(self) -> int:
        filas = self._consultar(f"SELECT COUNT(*) FROM {_id(self.tabla)}")
        return int(filas[0][0]) if filas else 0

    # -- utilidades para el server MCP y el CLI --------------------------
    def filtrar(self, filters: Filters | None = None, limite: int = 50) -> list[dict]:
        """SELECT con filtros de metadatos (sin similitud)."""
        cols = self._columnas_reales()
        clausulas, params = _filtros_sql(filters or Filters(), cols)
        sql = f"SELECT {self._sel()} FROM {_id(self.tabla)}"
        if clausulas:
            sql += " WHERE " + " AND ".join(clausulas)
        sql += f" LIMIT {max(1, min(int(limite), 500))}"
        return [self._doc(f, list(cols)) for f in self._consultar(sql, params)]

    def pendientes(self, limite: int = 10000) -> list[dict]:
        """Productos sin embedding (para `pg-sync`)."""
        cols = self._columnas_reales()
        self._validar_vector()
        v = _id(self.col_vector)
        sql = (
            f"SELECT {self._sel()} FROM {_id(self.tabla)} "
            f"WHERE {v} IS NULL LIMIT {max(1, int(limite))}"
        )
        return [self._doc(f, list(cols)) for f in self._consultar(sql)]

    def guardar_embeddings(self, pares: list[tuple[str, str]]) -> int:
        """Guarda pares (id, vector literal pgvector). Devuelve cuantos."""
        cols = self._columnas_reales()
        self._validar_vector()
        if not pares:
            return 0
        sql = (
            f"UPDATE {_id(self.tabla)} SET {_id(self.col_vector)} = %s "
            f"WHERE {_id(cols['id'])}::text = %s"
        )
        conn = self._conectar(self.dsn)
        try:
            with conn.cursor() as cur:
                cur.executemany(sql, [(vec, str(pid)) for pid, vec in pares])
            conn.commit()
        except Exception as e:
            raise PgError(f"no se pudieron guardar los embeddings: {e}") from e
        finally:
            conn.close()
        self._docs_cache = None
        return len(pares)

    def similares(self, product_id: str, k: int = 5) -> list[dict]:
        """Top-k parecidos a un producto: coseno sobre los vectores de la
        BD (no hace falta modelo de embeddings, solo pgvector)."""
        cols = self._columnas_reales()
        self._validar_vector()
        t = _id(self.tabla)
        v = _id(self.col_vector)
        idc = _id(cols["id"])
        sql = (
            f"SELECT {self._sel()}, 1 - (a.{v} <=> b.{v}) AS score "
            f"FROM {t} a JOIN {t} b ON b.{idc}::text = %s "
            f"WHERE a.{v} IS NOT NULL AND a.{idc}::text <> b.{idc}::text "
            f"ORDER BY a.{v} <=> b.{v} LIMIT %s"
        )
        filas = self._consultar(sql, (str(product_id), int(k)))
        campos = list(cols)
        return [
            {**self._doc(f[: len(campos)], campos), "score": float(f[len(campos)])}
            for f in filas
        ]

    def ping(self, dim_esperada: int | None = None) -> dict:
        """Diagnostico: tabla, columnas, filas y dimension de los vectores."""
        cols = self._columnas_reales()
        n = len(self)
        dim: int | None = None
        try:
            self._validar_vector()
            filas = self._consultar(
                f"SELECT {_id(self.col_vector)} FROM {_id(self.tabla)} "
                f"WHERE {_id(self.col_vector)} IS NOT NULL LIMIT 1"
            )
            if filas:
                dim = _dim_de(filas[0][0])
        except PgError:
            pass  # sin columna vector todavia: se informa con dim=None
        if dim_esperada is not None and dim is not None and dim != dim_esperada:
            raise PgError(
                f"los vectores de la BD tienen dimension {dim} y el modelo "
                f"usa {dim_esperada}: no son compatibles (¿modelo distinto?)"
            )
        return {"tabla": self.tabla, "columnas": sorted(cols.values()), "n": n, "dim": dim}


def cargar_store(embedder) -> tuple[VectorStore | PgStore, str, str | None]:
    """Elige el backend segun `RAG_STORE` y nunca tumba el servicio.

    Devuelve `(store, origen, error)`: `origen` es `"pg"` o `"local"`;
    con `RAG_STORE=pg` si algo falla se vuelve al indice local y el
    motivo queda en `error` (se publica en `/health`).
    """
    if config.STORE_BACKEND != "pg":
        return load_index(embedder), "local", None
    try:
        store = PgStore()
        store.ping(dim_esperada=embedder.spec.dim)
        return store, "pg", None
    except Exception as e:  # noqa: BLE001 - cualquier fallo: plan B local
        print(f"aviso: RAG_STORE=pg no disponible ({e}); se usa el indice local")
        return load_index(embedder), "local", str(e)
