#!/usr/bin/env bash
# Verificacion de humo del prototipo de RAG.
#
#   bash scripts/verificar.sh                  # contra el servicio local (:8080)
#   bash scripts/verificar.sh --url http://vm:8080
#   bash scripts/verificar.sh --saltar-tests    # no ejecuta la suite de tests
#
# Comprueba, en orden:
#   1. el entorno (venv, indice, modelos)
#   2. la suite de tests
#   3. los servicios (Ollama y el servicio RAG)
#   4. la API: /health, /search, /ask, /ask/stream, /equiv
#   5. la CLI: search, ask, equiv, eval
#
# Sale con codigo 0 si todo pasa, 1 si algo falla.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

URL="http://127.0.0.1:8080"
OLLAMA_URL="${OLLAMA_HOST:-http://127.0.0.1:11434}"
SALTAR_TESTS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --saltar-tests) SALTAR_TESTS=1; shift ;;
    *) echo "opcion desconocida: $1"; exit 2 ;;
  esac
done

OK=0
FALLO=0
declare -a RESULTADOS=()

verde() { printf '\033[0;32m%s\033[0m' "$1"; }
rojo() { printf '\033[0;31m%s\033[0m' "$1"; }

check() {
  local nombre="$1"; shift
  local salida
  if salida="$("$@" 2>&1)"; then
    OK=$((OK + 1))
    RESULTADOS+=("$(verde '  OK  ') $nombre")
    [[ -n "${VERBOSO:-}" ]] && echo "$salida"
  else
    FALLO=$((FALLO + 1))
    RESULTADOS+=("$(rojo ' FALLO') $nombre")
    echo "$salida" | head -5 | sed 's/^/        /'
  fi
}

echo "== 1. Entorno =="
check "venv con las dependencias" bash -c 'test -x .venv/bin/python && .venv/bin/python -c "import flask, langchain_core, jsonschema, sentence_transformers"'
check "indice de embeddings" bash -c 'test -f .cache/index/e5-small/meta.json'
check "dataset de prueba" bash -c 'test -f data/raw/mercadona_clean.txt && test -f data/gold/qa.json'

if [[ $SALTAR_TESTS -eq 0 ]]; then
  echo "== 2. Tests =="
  check "suite de tests" bash -c '.venv/bin/python -m pytest tests/ -q 2>&1 | tail -1 | grep -q "passed"'
else
  echo "== 2. Tests (omitidos) =="
fi

echo "== 3. Servicios =="
check "Ollama responde" bash -c "curl -sf -m 10 $OLLAMA_URL/api/tags >/dev/null"
check "el servicio RAG responde" bash -c "curl -sf -m 15 $URL/health >/dev/null"

echo "== 4. API =="
check "GET /health" bash -c "curl -sf -m 15 $URL/health | grep -q '\"ok\": *true'"
check "POST /search devuelve productos" bash -c "
  curl -sf -m 60 $URL/search -H 'Content-Type: application/json' \
    -d '{\"query\":\"aceite de oliva\",\"k\":3}' | .venv/bin/python -c '
import json,sys
d=json.load(sys.stdin)
assert d[\"resultados\"], \"sin resultados\"
assert all(\"id\" in r and \"score\" in r for r in d[\"resultados\"])'"
check "POST /ask devuelve el JSON del esquema" bash -c "
  curl -sf -m 240 $URL/ask -H 'Content-Type: application/json' \
    -d '{\"question\":\"¿cual es el aceite de oliva virgen extra de 1 l mas barato por litro?\"}' \
    | .venv/bin/python -c '
import json,sys
sys.path.insert(0,\".\")
from rag.guardrails import validar
d=json.load(sys.stdin)
errores=validar(d)
assert not errores, \"el JSON no cumple el esquema: %s\" % errores
assert d[\"answer\"], \"respuesta vacia\"
assert d[\"guardrails\"][\"citations_valid\"], \"cita invalida\"
assert d[\"sources\"], \"sin fuentes\"'"
check "POST /ask/stream emite tokens" bash -c "
  curl -sN -m 240 $URL/ask/stream -H 'Content-Type: application/json' \
    -d '{\"question\":\"¿cual es el aceite mas barato por litro?\"}' \
    | .venv/bin/python -c '
import json,sys
evento=None; tokens=0; fin=False
for linea in sys.stdin:
    linea=linea.rstrip()
    if linea.startswith(\"event: \"): evento=linea[7:]
    elif linea.startswith(\"data: \"):
        if evento==\"token\": tokens+=1
        elif evento==\"fin\": fin=True
assert tokens>0, \"no llego ningun token\"
assert fin, \"no llego el evento fin\"'"
check "POST /equiv devuelve candidatos" bash -c "
  curl -sf -m 60 $URL/equiv -H 'Content-Type: application/json' \
    -d '{\"nombre\":\"aceite de oliva\",\"chain\":\"carrefour\"}' | .venv/bin/python -c '
import json,sys
d=json.load(sys.stdin)
assert d[\"origen\"][\"id\"], \"sin origen\"
assert isinstance(d[\"candidatos\"], list)'"

echo "== 5. CLI =="
check "cli search" bash -c ".venv/bin/python -m rag.cli search 'aceite de oliva' -k 3 2>/dev/null | grep -q 'Recuperados'"
check "cli eval (solo retrieval)" bash -c ".venv/bin/python -m rag.cli eval --llm none 2>/dev/null | grep -q 'CATALOGO'"

echo
echo "== Resultado =="
for r in "${RESULTADOS[@]}"; do echo "$r"; done
echo
echo "  ${OK} correctos, ${FALLO} fallos"
[[ $FALLO -eq 0 ]] && echo "  TODO CORRECTO" || echo "  HAY FALLOS"
exit $(( FALLO > 0 ? 1 : 0 ))
