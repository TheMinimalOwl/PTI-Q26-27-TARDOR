#!/usr/bin/env bash
#
# Despliegue del normalizer con Pydantic (tarea 3, sin la parte de BD).
# Hay que ejecutarlo EN LA VM del cluster: necesita docker, minikube, kubectl
# y el CLI `fission` (para crear/actualizar la funcion y, si hace falta, el entorno).
#
#   ./deploy.sh                 # todo: entorno + funcion + trigger + consumer + humo
#   ./deploy.sh env             # solo la imagen/entorno de Fission con pydantic
#   ./deploy.sh fn              # solo el codigo de la funcion (+ trigger HTTP)
#   ./deploy.sh consumer        # solo el consumer (imagen nueva + rollout)
#   ./deploy.sh smoke           # solo la prueba de humo contra el router
#
# Variables (valores por defecto entre parentesis):
#   ENV_IMAGE (normalizer-env:v1)      imagen del entorno Fission con pydantic
#   CONSUMER_IMAGE (normalizer-consumer:v2)
#   ENV_NAME (python)  FN_NAME (normalizer)  ENTRYPOINT (normalizer.main)
#   NS_ENV (default)   NS_FN (default)       NS_ROUTER (fission)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_IMAGE="${ENV_IMAGE:-normalizer-env:v1}"
CONSUMER_IMAGE="${CONSUMER_IMAGE:-normalizer-consumer:v2}"
ENV_NAME="${ENV_NAME:-python}"
FN_NAME="${FN_NAME:-normalizer}"
ENTRYPOINT="${ENTRYPOINT:-normalizer.main}"
NS_ENV="${NS_ENV:-default}"
NS_FN="${NS_FN:-default}"
NS_ROUTER="${NS_ROUTER:-fission}"
CONSUMER_DEPLOY="${CONSUMER_DEPLOY:-normalizer-consumer}"
CONSUMER_CONTAINER="${CONSUMER_CONTAINER:-consumer}"

say()  { printf '\n== %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { printf "falta '%s' en el PATH\n" "$1" >&2; exit 1; }; }
env_exists() { kubectl -n "$NS_ENV" get environment "$ENV_NAME" >/dev/null 2>&1; }

step_env() {
  need docker; need minikube; need kubectl
  say "entorno Fission '$ENV_NAME' -> $ENV_IMAGE (con pydantic)"

  # Heredamos de la imagen que ya usa el entorno, para no cambiar de version de
  # Fission. Si ya apunta a nuestra imagen, no la usamos como base (creceria en
  # cada ejecucion).
  local base="fission/python-env:latest"
  if env_exists; then
    local current
    current="$(kubectl -n "$NS_ENV" get environment "$ENV_NAME" -o jsonpath='{.spec.runtime.image}' || true)"
    if [ -n "$current" ] && [ "$current" != "$ENV_IMAGE" ]; then base="$current"; fi
    echo "   base: $base"
  fi

  docker build --build-arg "FISSION_PY_ENV=$base" -t "$ENV_IMAGE" -f "$HERE/Dockerfile.env" "$HERE"
  minikube image load "$ENV_IMAGE"

  if env_exists; then
    # Solo se cambia la imagen: se conservan version, builder y poolsize.
    kubectl -n "$NS_ENV" patch environment "$ENV_NAME" --type merge \
      -p "{\"spec\":{\"runtime\":{\"image\":\"$ENV_IMAGE\"}}}"
  else
    need fission
    fission env create --name "$ENV_NAME" --envns "$NS_ENV" --image "$ENV_IMAGE"
  fi

  # El pool precalentado puede seguir sirviendo pods con la imagen vieja.
  kubectl -n "$NS_ENV" delete pod -l "environmentName=$ENV_NAME" --ignore-not-found
}

step_fn() {
  need fission
  say "funcion '$FN_NAME' con el codigo nuevo ($ENTRYPOINT)"
  if fission fn get --name "$FN_NAME" --fnns "$NS_FN" >/dev/null 2>&1; then
    fission fn update --name "$FN_NAME" --fnns "$NS_FN" \
      --code "$HERE/normalizer.py" --entrypoint "$ENTRYPOINT"
  else
    fission fn create --name "$FN_NAME" --fnns "$NS_FN" \
      --env "$ENV_NAME" --envns "$NS_ENV" \
      --code "$HERE/normalizer.py" --entrypoint "$ENTRYPOINT"
  fi
  kubectl apply -f "$HERE/fission.yaml"
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

  local body
  body='{"wh":"default","items":[{"id":4241,"display_name":"Aceite de oliva Hacendado","share_url":"https://tienda.mercadona.es/product/4241","categories":[{"name":"Aceite, especias y salsas"}],"price_instructions":{"unit_price":"17.25","unit_size":5.0,"size_format":"l","reference_price":"3.450","reference_format":"L"}}]}'

  echo "-- text/plain (contrato actual):"
  curl -sS -X POST "http://127.0.0.1:8888/normalize" \
    -H 'Content-Type: application/json' -d "$body"
  echo "-- application/json (CleanBatch):"
  curl -sS -X POST "http://127.0.0.1:8888/normalize?format=json" \
    -H 'Content-Type: application/json' -d "$body"
  echo
}

case "${1:-all}" in
  all)      step_env; step_fn; step_consumer; step_smoke ;;
  env)      step_env ;;
  fn)       step_fn ;;
  consumer) step_consumer ;;
  smoke)    step_smoke ;;
  *) printf 'uso: %s [all|env|fn|consumer|smoke]\n' "$0" >&2; exit 2 ;;
esac
