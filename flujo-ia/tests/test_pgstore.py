"""Tests de PgStore (PostgreSQL + pgvector) con una conexion simulada.

No hay que tener una base de verdad: la fabrica de conexiones devuelve un
objeto falso que registra las consultas y devuelve las filas que se le
indican. Asi se comprueba el SQL que se genera (coseno, filtros,
parametros) y el mapeo fila -> documento, que es lo que hay que acertar
cuando entre la BD real.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from rag import config, pgstore
from rag.pgstore import PgError, PgStore, cargar_store, vector_texto
from rag.retriever import Filters, Retriever
from rag.store import VectorStore

CAMPOS = list(config.PG_COLUMNAS)  # id, name, chain, ... (orden del SELECT)


class CursorFalso:
    def __init__(self, resultados):
        self.resultados = list(resultados)
        self.ejecutados: list[tuple] = []
        self.lotes: list[tuple] = []  # de executemany
        self._actual: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.ejecutados.append((sql, list(params) if params is not None else []))
        if not self.resultados:
            self._actual = []
            return
        r = self.resultados.pop(0)
        if isinstance(r, Exception):
            raise r
        self._actual = r

    def executemany(self, sql, seq):
        self.lotes.append((sql, list(seq)))
        self.ejecutados.append((sql, "executemany"))

    def fetchall(self):
        return list(self._actual)

    def fetchone(self):
        return self._actual[0] if self._actual else None


class ConnFalsa:
    def __init__(self, resultados=()):
        self.cur = CursorFalso(resultados)
        self.cerrada = False
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def close(self):
        self.cerrada = True


def store_con(resultados, **kw) -> tuple[PgStore, ConnFalsa]:
    conn = ConnFalsa(resultados)
    store = PgStore(dsn="postgresql://prueba/prueba", conectar_fn=lambda dsn: conn, **kw)
    return store, conn


def fila(**kwargs) -> tuple:
    base = {
        "id": "10001",
        "name": "Aceite de oliva",
        "chain": "mercadona",
        "category": "aceites",
        "total": "3.50",
        "unit_price": "3.50",
        "unit": "l",
        "size": "1",
        "size_format": "l",
        "url": "http://x",
    }
    base.update(kwargs)
    return tuple(base[c] for c in CAMPOS)


def cols_info() -> list[tuple]:
    return [("public", config.PG_COLUMNAS[c]) for c in CAMPOS] + [
        ("public", config.PG_COL_VECTOR)
    ]


# -- search ---------------------------------------------------------------


def test_busqueda_usa_coseno_pgvector():
    conn_score = 0.91
    store, conn = store_con(
        [cols_info(), [(*fila(), conn_score), (*fila(id="10002", name="Otro"), 0.5)]]
    )
    hits = store.search(np.array([1.0, 0.0], dtype=np.float32), k=2)

    sql, params = conn.cur.ejecutados[1]  # [0] es la sonda de information_schema
    assert "<=>" in sql and "ORDER BY" in sql and "LIMIT %s" in sql
    assert "IS NOT NULL" in sql  # sin vector no hay score
    assert params == [vector_texto([1.0, 0.0])] * 2 + [2]
    assert [h.rank for h in hits] == [1, 2]
    assert hits[0].score == pytest.approx(0.91)
    assert hits[0].doc["name"] == "Aceite de oliva"
    assert "score" not in hits[0].doc  # el score no es parte del documento
    assert conn.cerrada  # conexion devuelta en cada operacion


def test_filtros_se_traducen_a_where_parametrizado():
    filtros = Filters(chain="mercadona", category="aceite", max_total=5)
    store, conn = store_con([cols_info(), []])
    store.search(np.array([1.0, 0.0]), k=3, filters=filtros)

    sql, params = conn.cur.ejecutados[1]
    assert "= %s" in sql
    assert "LIKE %s ESCAPE" in sql
    assert "::numeric <= %s" in sql
    assert "mercadona" in params and "%aceite%" in params and "5" in params


def test_exclude_ids_se_pasa_como_lista():
    store, conn = store_con([cols_info(), []])
    store.search(np.array([1.0, 0.0]), k=1, exclude_ids={"9", "8"})
    sql, params = conn.cur.ejecutados[1]
    assert "ANY(%s)" in sql
    assert ["9", "8"] in params or ["8", "9"] in params


def test_where_solo_sin_filters_da_error_claro():
    store, _ = store_con([])
    with pytest.raises(PgError, match="filters="):
        store.search(np.array([1.0, 0.0]), where=lambda d: True)


def test_columna_de_filtro_inexistente_da_error():
    # La tabla no tiene 'chain': filtrar por ella seria devolver sin filtrar.
    store, _ = store_con([[("public", "id"), ("public", "name"), ("public", "embedding")]])
    with pytest.raises(PgError, match="chain"):
        store.search(np.array([1.0, 0.0]), filters=Filters(chain="mercadona"))


# -- get / len / docs / filter -------------------------------------------


def test_get_devuelve_documento_o_none():
    store, conn = store_con([cols_info(), [fila()], []])
    doc = store.get("10001")
    assert doc is not None and doc["name"] == "Aceite de oliva"
    assert store.get("999") is None
    sql, params = conn.cur.ejecutados[1]
    assert "::text = %s" in sql and params == ["10001"]


def test_len_es_un_count():
    store, _ = store_con([[(7,)]])
    assert len(store) == 7


def test_docs_se_consulta_una_sola_vez():
    store, conn = store_con([cols_info(), [fila()], [fila(id="10002")]])
    assert len(store.docs) == 1
    assert len(store.docs) == 1  # cacheado
    assert len(conn.cur.ejecutados) == 2  # 1 info_schema + 1 select


def test_filter_usa_la_interfaz_de_siempre():
    store, _ = store_con([cols_info(), [fila(), fila(chain="lidl")]])
    assert [d["id"] for d in store.filter(lambda d: d["chain"] == "lidl")] == ["10001"]


def test_mapeo_de_valores_como_el_indice_local():
    fila_mala = (
        10001,  # id entero -> texto
        "Aceite",
        "mercadona",
        None,  # category nula
        Decimal("3.50"),  # numeric -> texto igual que Product.to_dict
        None,
        None,
        None,
        None,
        None,
    )
    store, _ = store_con([cols_info(), [fila_mala]])
    doc = store.get("1")
    assert doc["id"] == "10001"
    assert doc["total"] == "3.50"
    assert doc["category"] is None and doc["unit"] is None


# -- utilidades -----------------------------------------------------------


def test_filtrar_es_un_select_con_limite():
    store, conn = store_con([cols_info(), [fila()]])
    filas = store.filtrar(Filters(chain="mercadona"), limite=10)
    sql, params = conn.cur.ejecutados[1]
    assert sql.startswith("SELECT") and "LIMIT 10" in sql
    assert "<=>" not in sql  # sin similitud
    assert params == ["mercadona"]
    assert filas[0]["chain"] == "mercadona"


def test_similares_hace_self_join_por_coseno():
    store, conn = store_con([cols_info(), [(*fila(), 0.87)]])
    res = store.similares("10001", k=4)
    sql, params = conn.cur.ejecutados[1]
    assert "JOIN" in sql and sql.count("<=>") == 2
    assert params == ["10001", 4]
    assert res[0]["score"] == pytest.approx(0.87)
    assert res[0]["name"] == "Aceite de oliva"


def test_pendientes_y_guardar_embeddings():
    store, conn = store_con([cols_info(), [fila()]])
    pend = store.pendientes()
    assert pend and pend[0]["id"] == "10001"
    sql, _ = conn.cur.ejecutados[1]  # [0] es la sonda de information_schema
    assert "IS NULL" in sql

    n = store.guardar_embeddings([("10001", "[0.1,0.2]")])
    assert n == 1
    assert conn.committed
    assert conn.cur.lotes  # UPDATE en lote
    assert conn.cur.lotes[0][1] == [("[0.1,0.2]", "10001")]


def test_ping_informa_dimension():
    store, conn = store_con(
        [
            cols_info(),  # information_schema
            [(257,)],  # count
            [("[0.1,0.2,0.3]",)],  # un vector
        ]
    )
    info = store.ping()
    assert info["n"] == 257 and info["dim"] == 3
    assert "id" in info["columnas"]  # columnas del documento (el vector va aparte, en dim)


def test_ping_detecta_dimension_incompatible():
    store, _ = store_con([cols_info(), [(10,)], [("[0.1,0.2]",)]])
    with pytest.raises(PgError, match="dimension"):
        store.ping(dim_esperada=384)


def test_identificador_invalido_no_pasa_a_sql():
    with pytest.raises(PgError, match="no valido"):
        pgstore._id("productos; DROP TABLE x")
    store, conn = store_con([cols_info()], tabla="malo malo")
    with pytest.raises(PgError, match="no valido"):
        store.filtrar(Filters())  # FROM "tabla mala" -> rechazado


def test_tabla_inexistente_da_error_acotado():
    store, _ = store_con([[]])  # information_schema sin filas
    with pytest.raises(PgError, match="no existe la tabla"):
        store.ping()


def test_sin_dsn_da_instrucciones():
    with pytest.raises(PgError, match="RAG_PG_DSN"):
        pgstore.conectar("")


# -- backend local: el puente filters y el fallback -----------------------


def test_indice_local_acepta_solo_el_kwarg_filters():
    """Si al store local solo llega `filters`, se usa (mismo resultado)."""
    vs = VectorStore(dim=2)
    vs.add(
        np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        [{"id": "a", "chain": "mercadona"}, {"id": "b", "chain": "lidl"}],
    )
    hits = vs.search(np.array([1.0, 0.0]), k=2, filters=Filters(chain="lidl"))
    assert [h.id for h in hits] == ["b"]


class EmbedderFalso:
    class spec:
        key = "e5-small"
        dim = 384

    def encode_one(self, texto, is_query=True):
        return np.array([1.0, 0.0], dtype=np.float32)


def test_cargar_store_por_defecto_es_local(monkeypatch):
    monkeypatch.setattr(config, "STORE_BACKEND", "local")
    monkeypatch.setattr(pgstore, "load_index", lambda emb: "INDICE")
    store, origen, error = cargar_store(EmbedderFalso())
    assert (store, origen, error) == ("INDICE", "local", None)


def test_cargar_store_pg_con_fallback_si_falla(monkeypatch):
    """RAG_STORE=pg sin base disponible: vuelve al indice local (plan B)."""
    monkeypatch.setattr(config, "STORE_BACKEND", "pg")
    monkeypatch.setattr(config, "PG_DSN", "")  # sin conexion: ping falla
    monkeypatch.setattr(pgstore, "load_index", lambda emb: "INDICE")
    store, origen, error = cargar_store(EmbedderFalso())
    assert (store, origen) == ("INDICE", "local")
    assert error and "RAG_PG_DSN" in error


def test_cargar_store_pg_ok(monkeypatch):
    monkeypatch.setattr(config, "STORE_BACKEND", "pg")
    monkeypatch.setattr(config, "PG_DSN", "postgresql://x")

    class PgStub:
        def __init__(self, *a, **k):
            pass

        def ping(self, dim_esperada=None):
            return {"n": 5, "dim": dim_esperada}

    monkeypatch.setattr(pgstore, "PgStore", PgStub)
    store, origen, error = cargar_store(EmbedderFalso())
    assert origen == "pg" and error is None


def test_retriever_pasa_el_objeto_filters_al_store():
    class StoreCaptura:
        docs = []

        def search(self, qv, k=5, where=None, exclude_ids=None, filters=None):
            self.ultima = {"where": where, "filters": filters}
            return []

        def get(self, pid):
            return None

        def __len__(self):
            return 0

    captura = StoreCaptura()
    retr = Retriever(EmbedderFalso(), captura)
    filtros = Filters(chain="lidl")
    retr.search("aceite", k=3, filters=filtros)
    assert captura.ultima["filters"] is filtros
    assert captura.ultima["where"] == filtros.matches
