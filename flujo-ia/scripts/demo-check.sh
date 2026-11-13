#!/usr/bin/env bash
# Verifica las 4 preguntas de demo (docs/05-demo.md) contra el servicio.
#
#   bash scripts/demo-check.sh                    # servicio local (:8080)
#   bash scripts/demo-check.sh --url http://vm:8080
#
# Compara cada respuesta con lo esperado en 05-demo.md:
#   1. AOVE 1 l mas barato en total  -> 11.70 y carrefour
#   2. AOVE 1 l por unidad           -> 12.50 y empate de las tres cadenas
#   3. Agua mineral en Mercadona     -> 0.45 y mercadona/hacendado
#   4. Arroz (fuera de catalogo)     -> abstencion o respuesta sin precios
#
# Sale con codigo 0 si las 4 pasan, 1 si algo falla.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

URL="http://127.0.0.1:8080"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
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
  else
    FALLO=$((FALLO + 1))
    RESULTADOS+=("$(rojo ' FALLO') $nombre")
    echo "$salida" | head -8 | sed 's/^/        /'
  fi
}

# demo <nombre> <pregunta> <expresion python sobre d y ans>
demo() {
  local nombre="$1" pregunta="$2" expr="$3"
  local payload
  payload="$(.venv/bin/python -c 'import json,sys;print(json.dumps({"question": sys.argv[1]}))' "$pregunta")"
  check "$nombre" bash -c "
    salida=\$(curl -sf -m 300 '$URL/ask' -H 'Content-Type: application/json' -d '$payload') || {
      echo 'sin respuesta del servicio ($URL/ask)'; exit 1; }
    echo \"\$salida\" | .venv/bin/python -c \"
import json, sys, re
d = json.load(sys.stdin)
ans = (d.get('answer') or '')
ok = bool($expr)
if not ok:
    print('respuesta: ' + ans[:300])
    print('abstained: %s  guardrails: %s' % (d.get('abstained'), d.get('guardrails')))
sys.exit(0 if ok else 1)
\""
}

echo "== Demo: 4 preguntas ($URL) =="
check "el servicio tiene LLM configurado" bash -c "
  curl -sf -m 15 '$URL/health' | .venv/bin/python -c \"
import json, sys
h = json.load(sys.stdin)
prov = (h.get('llm') or {}).get('provider')
assert prov and prov != 'none', 'sin LLM real (provider=%r, error=%r): RAG_LLM=none?' % (prov, h.get('llm_error'))
\""

demo "1 · precio en total (11.70 + carrefour)" \
  "¿Cuál es el aceite de oliva virgen extra de 1 l más barato en total?" \
  "re.search(r'11[.,]70', ans) and 'carrefour' in ans.lower()"

demo "2 · empate por unidad (12.50 + 3 cadenas)" \
  "¿Cuál es el aceite de oliva virgen extra de 1 l más barato por unidad?" \
  "re.search(r'12[.,]50', ans) and ('empate' in ans.lower() or (all(c in ans.lower() for c in ('carrefour', 'alcampo')) and ('mercadona' in ans.lower() or 'hacendado' in ans.lower())))"

demo "3 · lookup Mercadona (0.45 + mercadona)" \
  "¿Cuánto cuesta el agua mineral de 1.5 l en Mercadona?" \
  "re.search(r'0[.,]45', ans) and ('mercadona' in ans.lower() or 'hacendado' in ans.lower())"

demo "4 · fuera de catalogo (abstencion, no inventa)" \
  "¿Cuánto cuesta el arroz de 1 kg?" \
  "bool(d.get('abstained')) or not re.search(r'[0-9]+[.,][0-9]+\s*EUR', ans, re.I)"

echo
echo "== Resultado =="
for r in "${RESULTADOS[@]}"; do echo "$r"; done
echo
echo "  $OK correctos, $FALLO fallos"
[[ $FALLO -eq 0 ]] && echo "  LAS 4 DEMO LISTAS" || echo "  HAY FALLOS: revisar docs/05-demo.md"
exit $(( FALLO > 0 ? 1 : 0 ))
