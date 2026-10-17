#!/usr/bin/env bash
#
# Despliegue del normalizer con Pydantic (tarea 3, sin la parte de BD).
# Hay que ejecutarlo EN LA VM del cluster: necesita docker, minikube, kubectl y el
# CLI `fission`. Todo vive en el namespace `default` (el del kubeconfig actual).
#
#   bash deploy.sh              # todo: entorno + funcion + trigger + consumer + humo
#   bash deploy.sh env          # solo la imagen/entorno de Fission con pydantic
#   bash deploy.sh fn           # solo el codigo de la funcion (+ trigger HTTP)
#   bash deploy.sh consumer     # solo el consumer (imagen nueva + rollout)
#   bash deploy.sh smoke        # solo la prueba de humo contra el router
#
# Variables (valores por defecto entre parentesis):
#   ENV_IMAGE (normalizer-env:v1)      imagen del entorno Fission con pydantic
#   FISSION_PY_ENV ()                  base del build; por defecto, la imagen que ya
#                                      usa el entorno `python` (ghcr.io/fission/python-env)
#   CONSUMER_IMAGE (normalizer-consumer:v2)
#   ENV_NAME (python)  FN_NAME (normalizer)  ENTRYPOINT (normalizer.main)
#   NS_FN (default)    NS_ROUTER (fission)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_IMAGE="${ENV_IMAGE:-normalizer-env:v1}"
CONSUMER_IMAGE="${CONSUMER_IMAGE:-normalizer-consumer:v2}"
ENV_NAME="${ENV_NAME:-python}"
FN_NAME="${FN_NAME:-normalizer}"
ENTRYPOINT="${ENTRYPOINT:-normalizer.main}"
NS_FN="${NS_FN:-default}"
NS_ROUTER="${NS_ROUTER:-fission}"
CONSUMER_DEPLOY="${CONSUMER_DEPLOY:-normalizer-consumer}"
CONSUMER_CONTAINER="${CONSUMER_CONTAINER:-consumer}"

say()  { printf '\n== %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { printf "falta '%s' en el PATH\n" "$1" >&2; exit 1; }; }
env_exists() { kubectl -n "$NS_FN" get environment "$ENV_NAME" >/dev/null 2>&1; }
fn_exists()  { kubectl -n "$NS_FN" get function "$FN_NAME" >/dev/null 2>&1; }

# Nombre del primer pod del pool del entorno (para comprobar pydantic dentro).
# `grep -m1` + `|| true`: sin SIGPIPE y sin romper `set -e`/`pipefail`.
pool_pod() {
  kubectl -n "$NS_FN" get pods -o name 2>/dev/null | grep -m1 "poolmgr-$ENV_NAME-" || true
}

step_env() {
  need docker; need minikube; need kubectl
  say "entorno Fission '$ENV_NAME' -> $ENV_IMAGE (con pydantic)"

  # La base es la imagen que ya usa el entorno: asi no se cambia de version de
  # Fission. Si ya apunta a nuestra imagen, no la usamos como base (creceria en
  # cada ejecucion).
  local base="${FISSION_PY_ENV:-ghcr.io/fission/python-env}"
  if env_exists; then
    local current
    current="$(kubectl -n "$NS_FN" get environment "$ENV_NAME" -o jsonpath='{.spec.runtime.image}' || true)"
    if [ -n "$current" ] && [ "$current" != "$ENV_IMAGE" ]; then base="$current"; fi
  fi
  echo "   base: $base"

  if ! docker image inspect "$base" >/dev/null 2>&1; then
    echo "   (la base no esta en el docker local; se intentara bajar)"
    docker pull "$base" || {
      printf "no se pudo obtener la base '%s'.\n" "$base" >&2
      printf "alternativas: 'eval \$(minikube docker-env)' y repetir, o FISSION_PY_ENV=<imagen>\n" >&2
      exit 1
    }
  fi

  docker build --build-arg "FISSION_PY_ENV=$base" -t "$ENV_IMAGE" -f "$HERE/Dockerfile.env" "$HERE"
  minikube image load "$ENV_IMAGE"

  if env_exists; then
    # Solo se cambia la imagen: se conservan version (3), builder y poolsize.
    kubectl -n "$NS_FN" patch environment "$ENV_NAME" --type merge \
      -p "{\"spec\":{\"runtime\":{\"image\":\"$ENV_IMAGE\"}}}"
  else
    need fission
    fission env create --name "$ENV_NAME" --envNamespace "$NS_FN" --image "$ENV_IMAGE"
  fi

  # El pool precalentado puede seguir sirviendo pods con la imagen vieja.
  kubectl -n "$NS_FN" delete pod -l "environmentName=$ENV_NAME" --ignore-not-found

  # Comprobacion directa: un pod del pool tiene que poder importar pydantic.
  echo "   esperando pods del pool con la imagen nueva..."
  local pod
  for _ in $(seq 1 60); do
    pod="$(pool_pod)"
    if [ -n "$pod" ] && kubectl -n "$NS_FN" exec "$pod" -- python3 -c 'import pydantic' >/dev/null 2>&1; then
      printf "   OK: pydantic %s en %s\n" \
        "$(kubectl -n "$NS_FN" exec "$pod" -- python3 -c 'import pydantic; print(pydantic.VERSION)' 2>/dev/null)" \
        "$pod"
      return 0
    fi
    sleep 2
  done
  printf "AVISO: no he podido confirmar pydantic en el pool (%s). Revisa:\n" "$ENV_NAME" >&2
  printf "  kubectl -n %s get pods | grep poolmgr\n" "$NS_FN" >&2
  kubectl -n "$NS_FN" get pods -o name | grep "poolmgr-$ENV_NAME-" || true
  exit 1
}

step_fn() {
  need fission
  say "funcion '$FN_NAME' con el codigo nuevo ($ENTRYPOINT)"
  if fn_exists; then
    # Reutiliza el paquete existente (normalizer-<uuid>), creado con --code.
    fission fn update --name "$FN_NAME" \
      --code "$HERE/normalizer.py" --entrypoint "$ENTRYPOINT"
  else
    fission fn create --name "$FN_NAME" --env "$ENV_NAME" \
      --code "$HERE/normalizer.py" --entrypoint "$ENTRYPOINT"
  fi
  kubectl apply -f "$HERE/fission.yaml"
  kubectl -n "$NS_FN" get function "$FN_NAME"
  kubectl -n "$NS_FN" get packages
}

step_consumer() {
  need docker; need minikube; need kubectl
  say "consumer '$CONSUMER_DEPLOY' -> $CONSUMER_IMAGE"
  docker build -t "$CONSUMER_IMAGE" -f "$HERE/Dockerfile.consumer" "$HERE"
  minikube image load "$CONSUMER_IMAGE"
  kubectl -n "$NS_FN" set image "deployment/$CONSUMER_DEPLOY" "$CONSUMER_CONTAINER=$CONSUMER_IMAGE"
  kubectl -n "$NS_FN" rollout status "deployment/$CONSUMER_DEPLOY" --timeout=180s
}

step_smoke() {
  need kubectl; need curl
  say "prueba de humo contra el router"
  local port
  port="$(kubectl -n "$NS_ROUTER" get svc router -o jsonpath='{.spec.ports[0].port}')"
  kubectl -n "$NS_ROUTER" port-forward svc/router "8888:$port" >/dev/null 2>&1 &
  local pf=$!
  trap "kill $pf 2>/dev/null || true" EXIT
  for _ in $(seq 1 30); do
    curl -s -o /dev/null "http://127.0.0.1:8888/" && break
    sleep 1
  done

  local body txt json
  body='{"wh":"default","items":[{"id":4241,"display_name":"Aceite de oliva Hacendado","share_url":"https://tienda.mercadona.es/product/4241","categories":[{"name":"Aceite, especias y salsas"}],"price_instructions":{"unit_price":"17.25","unit_size":5.0,"size_format":"l","reference_price":"3.450","reference_format":"L"}}]}'
  txt="$(curl -sS -X POST "http://127.0.0.1:8888/normalize" -H 'Content-Type: application/json' -d "$body")"
  json="$(curl -sS -X POST "http://127.0.0.1:8888/normalize?format=json" -H 'Content-Type: application/json' -d "$body")"

  echo "-- text/plain (contrato actual):"
  printf '%s\n' "$txt"
  echo "-- application/json (CleanBatch):"
  printf '%s\n' "$json"

  # La linea esperada sale de normalizer.py: ref 3.450 EUR/L -> 3.45EUR/l src=fuente
  local esperada="4241 | Aceite de oliva Hacendado | 17.25EUR total | 3.45EUR/l | 5.0l | Aceite, especias y salsas | https://tienda.mercadona.es/product/4241 | ref=3.450EUR/L src=fuente"
  if [ "$txt" = "Items: 1
Unitarios: 1 (fuente 1, calculado 0) | Incompletos: 0
---
$esperada" ]; then
    echo "OK: la linea limpia coincide"
  else
    printf 'AVISO: la salida de texto no coincide con la esperada:\n  %s\n' "$esperada" >&2
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$json" | python3 -c 'import json, sys
d = json.load(sys.stdin)
i = d["items"][0]
assert d["source"] == "normalizer" and i["unit_price"] == "3.4500" and i["unit_src"] == "fuente" and i["unit"] == "l", i
print("OK: el JSON es valido y trae el precio unitario de la fuente")' \
      || printf 'AVISO: el JSON no trae lo esperado: %s\n' "$json" >&2
  else
    local ok=1
    for p in '"source": "normalizer"' '"unit_price": "3.4500"' '"unit_src": "fuente"'; do
      printf '%s' "$json" | grep -q -- "$p" || ok=0
    done
    if [ "$ok" = 1 ]; then
      echo "OK: el JSON trae el precio unitario de la fuente"
    else
      printf 'AVISO: el JSON no trae lo esperado: %s\n' "$json" >&2
    fi
  fi
}

case "${1:-all}" in
  all)      step_env; step_fn; step_consumer; step_smoke ;;
  env)      step_env ;;
  fn)       step_fn ;;
  consumer) step_consumer ;;
  smoke)    step_smoke ;;
  *) printf 'uso: %s [all|env|fn|consumer|smoke]\n' "$0" >&2; exit 2 ;;
esac
