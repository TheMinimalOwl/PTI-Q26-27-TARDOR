"""Embeddings multilingues de HuggingFace (sentence-transformers).

Por que `sentence-transformers` y no la API de embeddings: el prototipo tiene
que funcionar sin claves y sin coste, y el corpus es pequeno. Ademas, dejando
los embeddings en local, el indice se puede regenerar entero cuando cambie el
modelo sin depender de nadie.

Los dos modelos que se comparan en `docs/01-decision-modelos.md`:
- `bge-m3` (por defecto): 1024 dim, ~100 idiomas, sin prefijos.
- `e5-small`: 384 dim, ~470 MB, **exige** prefijos asimetricos ("query: " /
  "passage: "); sin ellos el recall se hunde.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import config


class Embedder:
    """Envoltorio sobre `SentenceTransformer` con las reglas de la casa.

    - Normaliza a norma 1 (el store hace coseno con producto escalar).
    - Aplica el prefijo correcto segun sea consulta o documento.
    - Carga perezosa: importar este modulo no descarga 2 GB.
    """

    def __init__(self, model: str | None = None, device: str = "cpu", batch_size: int = 32):
        self.spec = config.embedding_spec(model)
        self.device = device
        self.batch_size = batch_size
        self._model = None

    # -- carga perezosa ---------------------------------------------------
    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            config.HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._model = SentenceTransformer(
                self.spec.hf_id, device=self.device, cache_folder=str(config.HF_CACHE_DIR)
            )
            self._model.max_seq_length = min(self._model.max_seq_length, self.spec.max_seq_length)
        return self._model

    # -- codificacion -----------------------------------------------------
    def encode(
        self,
        texts: list[str],
        is_query: bool = False,
        normalize: bool = True,
    ) -> np.ndarray:
        """Codifica una lista de textos a vectores."""
        if not texts:
            return np.zeros((0, self.spec.dim), dtype=np.float32)
        prefix = self.spec.query_prefix if is_query else self.spec.passage_prefix
        payload = [f"{prefix}{t}" for t in texts]
        vecs = self.model.encode(
            payload,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    def encode_one(self, text: str, is_query: bool = True) -> np.ndarray:
        return self.encode([text], is_query=is_query)[0]

    def describe(self) -> dict:
        return {
            "key": self.spec.key,
            "hf_id": self.spec.hf_id,
            "dim": self.spec.dim,
            "query_prefix": self.spec.query_prefix,
            "passage_prefix": self.spec.passage_prefix,
            "note": self.spec.note,
        }
