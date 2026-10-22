#!/usr/bin/env bash
# Montaje del prototipo de RAG (flujo-ia) en una maquina limpia.
#
#   bash setup.sh              # venv + dependencias + dataset + indice
#   bash setup.sh --with-ollama   # ademas baja el LLM local de Ollama
#   bash setup.sh --verify        # solo comprueba el estado
#
# Es idempotente: se puede volver a ejecutar sin romper nada.
#
# Variables de entorno que honra:
#   HF_HOME          cache de HuggingFace (por defecto ~/.cache/huggingface)
#   RAG_EMBED_MODEL  modelo de embeddings (bge-m3 | e5-small | id de HF)
#   RAG_OLLAMA_MODEL modelo de Ollama (por defecto qwen3:4b)
#   RAG_LLM          backend de LLM (ollama | gemini | none)
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

VENV="$RAIZ/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"
CACHE="$RAIZ/.cache"

EMBED_MODEL="${RAG_EMBED_MODEL:-e5-small}"
OLLAMA_MODEL="${RAG_OLLAMA_MODEL:-qwen3:4b}"

export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export RAG_CACHE_DIR="${RAG_CACHE_DIR:-$CACHE}"
# pip descarga a /tmp, que en algunas maquinas esta en la particion del
# sistema (sin espacio). Se lleva el temporal a la cache del proyecto.
export TMPDIR="${TMPDIR:-$CACHE/tmp}"
mkdir -p "$HF_HOME" "$TMPDIR" "$CACHE"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

if [[ "${1:-}" == "--verify" ]]; then
  log "Estado"
  [[ -x "$PY" ]] && echo "venv: ok ($("$PY" --version 2>&1))" || echo "venv: FALTA"
  [[ -d "$CACHE/index/$EMBED_MODEL" ]] && echo "indice: ok ($EMBED_MODEL)" || echo "indice: FALTA (python -m rag.cli index)"
  command -v ollama >/dev/null && echo "ollama: $(ollama list 2>/dev/null | tail -n +2 | wc -l) modelo(s)" || echo "ollama: no instalado"
  command -v curl >/dev/null && echo "curl: ok" || echo "curl: FALTA"
  exit 0
fi

# ---------------------------------------------------------------------------
# 1. Python y entorno virtual
# ---------------------------------------------------------------------------
log "1/5 Entorno virtual"
if [[ ! -x "$PY" ]]; then
  python3 -c 'import sys; assert sys.version_info >= (3, 10), "se necesita Python 3.10+"'
  if python3 -m venv "$VENV" 2>/dev/null; then
    :
  else
    # Distributions de Debian sin python3-venv: ensurepip no esta.
    echo "ensurepip no disponible; se instala pip a mano"
    python3 -m venv --without-pip "$VENV"
    curl -sSf https://bootstrap.pypa.io/get-pip.py -o "$TMPDIR/get-pip.py"
    "$PY" "$TMPDIR/get-pip.py" -q
  fi
fi
"$PIP" install -q -U pip
echo "venv: $("$PY" --version 2>&1)"

# ---------------------------------------------------------------------------
# 2. Dependencias (torch en version CPU)
# ---------------------------------------------------------------------------
log "2/5 Dependencias"
if ! "$PY" -c "import torch, sentence_transformers" 2>/dev/null; then
  "$PIP" install -q --resume-retries 30 --timeout 180 \
    --index-url https://download.pytorch.org/whl/cpu torch
  "$PIP" install -q --resume-retries 30 --timeout 180 -r requirements.txt
fi
"$PY" - <<'PY'
import torch, sentence_transformers, numpy
print(f"torch {torch.__version__} | sentence-transformers {sentence_transformers.__version__} | numpy {numpy.__version__}")
PY

# ---------------------------------------------------------------------------
# 3. Dataset de prueba
# ---------------------------------------------------------------------------
log "3/5 Dataset de prueba"
if [[ ! -f data/raw/mercadona_clean.txt ]]; then
  "$PY" data/generate_dataset.py
else
  echo "data/raw/ ya existe (no se regenera)"
fi

# ---------------------------------------------------------------------------
# 4. Indice de embeddings
# ---------------------------------------------------------------------------
log "4/5 Indice de embeddings ($EMBED_MODEL)"
if [[ ! -f ".cache/index/$EMBED_MODEL/meta.json" ]]; then
  "$PY" -m rag.cli --embed "$EMBED_MODEL" index
else
  echo "el indice de $EMBED_MODEL ya existe (reindexar con: python -m rag.cli --embed $EMBED_MODEL index)"
fi

# ---------------------------------------------------------------------------
# 5. LLM local (opcional)
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--with-ollama" ]]; then
  log "5/5 LLM local con Ollama ($OLLAMA_MODEL)"
  if ! command -v ollama >/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  # Si el servicio ya corre, se reutiliza.
  if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "arrancando 'ollama serve' (Ctrl+C para parar)"
    OLLAMA_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}" nohup ollama serve >/tmp/ollama.log 2>&1 &
    sleep 3
  fi
  ollama pull "$OLLAMA_MODEL"
else
  log "5/5 LLM local (omitido: usa --with-ollama)"
fi

cat <<'EOF'

Listo. Prueba rapida:

  python -m rag.cli search "aceite de oliva virgen extra"
  python -m rag.cli ask "¿cual es el aceite mas barato por litro?" --llm ollama
  python -m rag.cli eval --llm none          # metricas de retrieval (sin API)
  python -m rag.cli compare                 # bge-m3 vs e5-small

Documentacion: docs/01-decision-modelos.md
EOF
