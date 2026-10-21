"""Configuracion del prototipo de RAG: modelos, rutas y parametros.

Decisiones tomadas (justificadas en `docs/01-decision-modelos.md`):

- **Embeddings**: multilingue de HuggingFace via `sentence-transformers`, porque los
  datos son de supermercado espanol y todos los candidatos open-weight de 2026
  compiten en el mismo rango. Por defecto `BAAI/bge-m3` (1024 dim, ~100 idiomas);
  alternativa ligera `intfloat/multilingual-e5-small` (384 dim) para maquinas
  modestas. Se elige con `--embed` o `RAG_EMBED_MODEL`.
- **LLM**: hibrido. `ollama` (local, sin claves, por defecto) o `gemini` (API, con
  `GEMINI_API_KEY`). Se elige con `--llm` o `RAG_LLM`. `none` deja el pipeline en
  modo solo-recuperacion, que es lo que se usa para medir la calidad del
  retrieval sin depender de ninguna API.

Todos los valores se pueden sobreescribir por entorno para no tocar codigo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
RAW_DIR = DATA_DIR / "raw"
GOLD_DIR = DATA_DIR / "gold"
CACHE_DIR = Path(os.environ.get("RAG_CACHE_DIR") or (RAIZ / ".cache"))
INDEX_DIR = CACHE_DIR / "index"
HF_CACHE_DIR = Path(os.environ.get("HF_HOME") or (CACHE_DIR / "huggingface"))

# `HF_HOME` se fija **antes** de que se importe transformers: si no, la
# libreria decide el directorio de cache al importarse y el modelo se baja a
# `~/.cache/huggingface` (o, en maquinas sin espacio, revienta).
os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR))


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddingSpec:
    """Ficha de un modelo de embeddings.

    `query_prefix` / `passage_prefix` importan: la familia E5 se entrenó con
    prefijos asimetricos ("query: " / "passage: ") y sin ellos el recall se
    hunde. BGE-M3 no los usa.
    """

    key: str
    hf_id: str
    dim: int
    query_prefix: str = ""
    passage_prefix: str = ""
    max_seq_length: int = 512
    note: str = ""


EMBEDDINGS: dict[str, EmbeddingSpec] = {
    "e5-small": EmbeddingSpec(
        key="e5-small",
        hf_id="intfloat/multilingual-e5-small",
        dim=384,
        query_prefix="query: ",
        passage_prefix="passage: ",
        note="12 capas, 384 dim, ~470 MB: el que entra en un portatil modesto",
    ),
    "bge-m3": EmbeddingSpec(
        key="bge-m3",
        hf_id="BAAI/bge-m3",
        dim=1024,
        note="XLM-RoBERTa-large, 100+ idiomas, denso+esparso+ColBERT, sin prefijos",
    ),
    "nomic-embed": EmbeddingSpec(
        key="nomic-embed",
        hf_id="nomic-ai/nomic-embed-text-v1.5",
        dim=768,
        query_prefix="search_query: ",
        passage_prefix="search_document: ",
        note="Contexto 8192 tokens, pensado para documentos largos",
    ),
    "qwen3-embed-0.6b": EmbeddingSpec(
        key="qwen3-embed-0.6b",
        hf_id="Qwen/Qwen3-Embedding-0.6B",
        dim=1024,
        note="Lider multilingue de 2026 (119 idiomas), 595M params, Apache-2.0",
    ),
}

# Por defecto `e5-small`: en la medicion propia iguala o supera a bge-m3 en el
# catalogo (recall@1 0.837 vs 0.584) y pesa 5 veces menos (471 MB vs 2.3 GB),
# que es justo lo que manda en una VM con RAM limitada. `bge-m3` sigue
# configurado: es el que gana (por poco) en equivalencia y el que se prueba
# con los datos reales. Ver docs/01-decision-modelos.md.
DEFAULT_EMBEDDING = os.environ.get("RAG_EMBED_MODEL", "e5-small")


def embedding_spec(model: str | None = None) -> EmbeddingSpec:
    """Resuelve una clave (`bge-m3`) o un id de HuggingFace directo."""
    key = model or DEFAULT_EMBEDDING
    if key in EMBEDDINGS:
        return EMBEDDINGS[key]
    # Id arbitrario de HF: se asume sin prefijos y con 384 dim por defecto.
    return EmbeddingSpec(key=key, hf_id=key, dim=384, note="modelo de HF arbitrario")


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

LLM_PROVIDERS = ("ollama", "gemini", "none")
DEFAULT_LLM = os.environ.get("RAG_LLM", "ollama")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("RAG_OLLAMA_MODEL", "qwen3:4b")
OLLAMA_TIMEOUT = float(os.environ.get("RAG_OLLAMA_TIMEOUT", "120"))

GEMINI_MODEL = os.environ.get("RAG_GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_BASE = os.environ.get(
    "RAG_GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
)
GEMINI_TIMEOUT = float(os.environ.get("RAG_GEMINI_TIMEOUT", "60"))


def gemini_api_key() -> str | None:
    """Clave de la API de Gemini.

    Se lee de `GEMINI_API_KEY` o `GOOGLE_API_KEY`. En las cuentas de la
    universidad la clave se saca de AI Studio (aistudio.google.com/apikey); la
    cuenta de pago da mas cuota que el tier gratuito.
    """
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


# ---------------------------------------------------------------------------
# Recuperacion
# ---------------------------------------------------------------------------

TOP_K = int(os.environ.get("RAG_TOP_K", "5"))
TOP_K_EQUIV = int(os.environ.get("RAG_TOP_K_EQUIV", "8"))
TEMPERATURE = float(os.environ.get("RAG_TEMPERATURE", "0"))

# Cuota que se manda al LLM como contexto. Es un LLM pequeno en local: pasarle
# 20 productos cuesta tiempo sin aportar (el recall@k ya se mide aparte).
MAX_CONTEXT_ITEMS = int(os.environ.get("RAG_MAX_CONTEXT_ITEMS", "6"))
