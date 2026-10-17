#!/usr/bin/env bash
#
# Montaje del flujo de entrada en la VM del cluster. Idempotente: se puede repetir.
#
#   bash setup-vm.sh              # todo: base + namespaces + nats + fission + normalizer + scraper + verify
#   bash setup-vm.sh base         # comprobaciones, minikube en marcha y repos de Helm
#   bash setup-vm.sh namespaces   # scrappers, messaging y fission
#   bash setup-vm.sh nats         # NATS con JetStream + stream SCRAPERS + consumidor durable normalizer
#   bash setup-vm.sh fission      # Fission + entorno `python` (version 3, poolsize 3)
#   bash setup-vm.sh normalizer   # deploy.sh: entorno con pydantic + funcion + trigger + consumer + humo
#   bash setup-vm.sh scraper      # secretos + imagen + CronJob scrapper-mercadona (0 2 * * *)
#   bash setup-vm.sh verify       # estado real y como lanzar una pasada de prueba
#
# Requisitos en la VM: docker (usable por tu usuario), minikube, kubectl, helm y el CLI
# `fission` en la misma version que el servidor (v1.27.0). No hay registry: las imagenes se
# cargan en el cluster con `minikube image load` (lo hacen este script y deploy.sh). Si un pod
# se queda en ImagePullBackOff, es que falta ese paso.
#
# Sin BD: la tarea 3 (escritura en base de datos) sigue pendiente. El MessageQueueTrigger de
# Fission no se monta a proposito: da 401 contra el router de 1.27 y el puente es el
# Deployment `normalizer-consumer`.
#
# Variables (valores por defecto entre parentesis):
#   NS_SCRAPPERS (scrappers)  NS_MSG (messaging)  NS_FISSION (fission)  NS_FN (default)
#   NATS_RELEASE (nats)  FISSION_RELEASE (fission)  NATS_URL_INCLUSTER (nats://nats:4222)
#   STREAM (SCRAPERS)  DURABLE (normalizer)  SUBJECT_ALL (scraper.>)
#   SUBJECT_RAW (scraper.mercadona.raw)  DELIVER (deliver.normalizer)
#   STREAM_MAX_AGE (7d)  DUPE_WINDOW (2m)  MAX_ACK_PENDING (1000)  ACK_WAIT (30s)
#   ENV_NAME (python)  ENV_VERSION (3)  ENV_POOLSIZE (3)
#   ENV_BASE_IMAGE (ghcr.io/fission/python-env)  CONSUMER_DEPLOY (normalizer-consumer)
#   SCRAPER_IMAGE (scrapper-mercadona:v1)  SCRAPER_CRONJOB (scrapper-mercadona)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NS_SCRAPPERS="${NS_SCRAPPERS:-scrappers}"
NS_MSG="${NS_MSG:-messaging}"
NS_FISSION="${NS_FISSION:-fission}"
NS_FN="${NS_FN:-default}"

NATS_RELEASE="${NATS_RELEASE:-nats}"
FISSION_RELEASE="${FISSION_RELEASE:-fission}"
NATS_URL_INCLUSTER="${NATS_URL_INCLUSTER:-nats://nats:4222}"

STREAM="${STREAM:-SCRAPERS}"
DURABLE="${DURABLE:-normalizer}"
SUBJECT_ALL="${SUBJECT_ALL:-scraper.>}"
SUBJECT_RAW="${SUBJECT_RAW:-scraper.mercadona.raw}"
DELIVER="${DELIVER:-deliver.normalizer}"
STREAM_MAX_AGE="${STREAM_MAX_AGE:-7d}"
DUPE_WINDOW="${DUPE_WINDOW:-2m}"
MAX_ACK_PENDING="${MAX_ACK_PENDING:-1000}"
ACK_WAIT="${ACK_WAIT:-30s}"

ENV_NAME="${ENV_NAME:-python}"
ENV_VERSION="${ENV_VERSION:-3}"
ENV_POOLSIZE="${ENV_POOLSIZE:-3}"
ENV_BASE_IMAGE="${ENV_BASE_IMAGE:-ghcr.io/fission/python-env}"
CONSUMER_DEPLOY="${CONSUMER_DEPLOY:-normalizer-consumer}"

SCRAPER_IMAGE="${SCRAPER_IMAGE:-scrapper-mercadona:v1}"
SCRAPER_CRONJOB="${SCRAPER_CRONJOB:-scrapper-mercadona}"

# La API de JetStream pide las duraciones en nanosegundos (la CLI las acepta como "7d").
STREAM_MAX_AGE_NS=604800000000000   # 7d
DUPE_WINDOW_NS=120000000000         # 2m
ACK_WAIT_NS=30000000000             # 30s

say()  { printf '\n== %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { printf "falta '%s' en el PATH\n" "$1" >&2; exit 1; }; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

ns_exists()       { kubectl get namespace "$1" >/dev/null 2>&1; }
ensure_ns()       { ns_exists "$1" || kubectl create namespace "$1" >/dev/null; }
release_exists()  { helm status "$1" -n "$2" >/dev/null 2>&1; }
nats_cli()        { kubectl -n "$NS_MSG" exec deploy/nats-box -- nats -s "$NATS_URL_INCLUSTER" "$@"; }
stream_exists()   { nats_cli stream info "$STREAM" >/dev/null 2>&1; }
consumer_exists() { nats_cli consumer info "$STREAM" "$DURABLE" >/dev/null 2>&1; }

# Peticion a la API de JetStream: imprime la respuesta y falla si no trae "success":true.
js_request() {
  local out
  out="$(nats_cli request "$1" "$2" 2>&1)" || { printf '%s\n' "$out"; return 1; }
  printf '%s\n' "$out"
  printf '%s' "$out" | grep -q '"success":true'
}

add_repo() {
  local name="$1" url="$2"
  if helm repo list 2>/dev/null | awk '{print $1}' | grep -qx "$name"; then
    helm repo add "$name" "$url" --force-update >/dev/null 2>&1 || true
  else
    helm repo add "$name" "$url" >/dev/null
  fi
}

step_base() {
  say "herramientas, minikube y repos de Helm"
  local c
  for c in docker minikube kubectl helm; do need "$c"; done
  docker info >/dev/null 2>&1 || die "docker no responde (revisa permisos del usuario)"

  if ! minikube status >/dev/null 2>&1; then
    echo "   minikube no esta en marcha: lo arranco"
    minikube start
  fi
  echo "   minikube: $(minikube status 2>/dev/null | head -1)"
  echo "   contexto de kubectl: $(kubectl config current-context)"

  add_repo nats https://nats-io.github.io/k8s/helm-charts/
  add_repo fission-charts https://fission.github.io/fission-charts/
  helm repo update >/dev/null
  echo "   repos: $(helm repo list 2>/dev/null | awk 'NR>1 {printf "%s ", $1}')"
}

step_namespaces() {
  need kubectl
  say "namespaces"
  kubectl apply -k "$HERE/cluster/"
  kubectl get namespaces "$NS_SCRAPPERS" "$NS_MSG" "$NS_FISSION" --no-headers | sed 's/^/   /'
}

step_nats() {
  need kubectl; need helm
  ensure_ns "$NS_MSG"

  say "NATS con JetStream (release '$NATS_RELEASE' en $NS_MSG)"
  if release_exists "$NATS_RELEASE" "$NS_MSG"; then
    echo "   ya esta instalado"
  else
    helm install "$NATS_RELEASE" nats/nats -n "$NS_MSG" -f "$HERE/messaging/nats-values.yaml"
  fi
  # El chart de NATS levanta un StatefulSet (necesita volumen para JetStream); con otros
  # valores del chart puede ser un Deployment, asi que miro cual de los dos existe.
  if kubectl -n "$NS_MSG" get statefulset "$NATS_RELEASE" >/dev/null 2>&1; then
    kubectl -n "$NS_MSG" rollout status statefulset/"$NATS_RELEASE" --timeout=180s
  elif kubectl -n "$NS_MSG" get deployment "$NATS_RELEASE" >/dev/null 2>&1; then
    kubectl -n "$NS_MSG" rollout status deployment/"$NATS_RELEASE" --timeout=180s
  else
    echo "   (no encuentro el StatefulSet ni el Deployment de NATS; sigo)"
  fi
  # nats-box es la caja de herramientas con la CLI: la usan los pasos de abajo.
  kubectl -n "$NS_MSG" rollout status deploy/nats-box --timeout=180s \
    || echo "   (nats-box no llega a Ready; el CLI de NATS va dentro de ese pod)"

  say "stream '$STREAM' (subjects '$SUBJECT_ALL', Max Age $STREAM_MAX_AGE, Discard Old)"
  if stream_exists; then
    echo "   ya existe"
  else
    # El scraper tambien lo crea de forma defensiva al publicar, pero solo con el subject
    # crudo y sin retencion; aqui se deja el estado bueno de una vez.
    # Equivalente con el CLI:
    #   nats stream add SCRAPERS --subjects 'scraper.>' --storage file \
    #     --max-age 7d --discard old --dupe-window 2m
    local payload resp
    payload="$(printf '{"name":"%s","subjects":["%s"],"retention":"limits","discard":"old","storage":"file","max_age":%s,"duplicate_window":%s}' \
      "$STREAM" "$SUBJECT_ALL" "$STREAM_MAX_AGE_NS" "$DUPE_WINDOW_NS")"
    if ! resp="$(js_request "\$JS.API.STREAM.CREATE.$STREAM" "$payload")"; then
      printf '%s\n' "$resp" >&2
      die "no he podido crear el stream '$STREAM'"
    fi
    echo "   creado"
  fi

  say "consumidor durable '$DURABLE' (push, filtro '$SUBJECT_RAW' -> '$DELIVER')"
  if consumer_exists; then
    echo "   ya existe"
  else
    # Esta es la cola a la que se suscribe consumer.py. Sin el, el consumer no recibe nada.
    # Equivalente con el CLI:
    #   nats consumer add SCRAPERS normalizer --deliver deliver.normalizer \
    #     --filter scraper.mercadona.raw --ack explicit --max-pending 1000
    local payload resp
    payload="$(printf '{"stream_name":"%s","config":{"durable_name":"%s","deliver_subject":"%s","filter_subject":"%s","ack_policy":"explicit","ack_wait":%s,"max_ack_pending":%s,"deliver_policy":"all","replay_policy":"instant"}}' \
      "$STREAM" "$DURABLE" "$DELIVER" "$SUBJECT_RAW" "$ACK_WAIT_NS" "$MAX_ACK_PENDING")"
    if ! resp="$(js_request "\$JS.API.CONSUMER.DURABLE.CREATE.$STREAM.$DURABLE" "$payload")"; then
      printf '%s\n' "$resp" >&2
      die "no he podido crear el consumidor '$DURABLE'"
    fi
    echo "   creado"
  fi

  nats_cli stream info "$STREAM" | sed -n '1,12p'
}

step_fission() {
  need kubectl; need helm; need fission
  ensure_ns "$NS_FISSION"

  say "Fission v1.27 (release '$FISSION_RELEASE' en $NS_FISSION)"
  if release_exists "$FISSION_RELEASE" "$NS_FISSION"; then
    echo "   ya esta instalado"
  else
    helm install "$FISSION_RELEASE" fission-charts/fission-all -n "$NS_FISSION"
  fi
  kubectl -n "$NS_FISSION" rollout status deploy/router --timeout=300s \
    || echo "   (el router no llega a Ready; deploy.sh fallara en la prueba de humo)"

  say "entorno '$ENV_NAME' de Fission (version $ENV_VERSION, poolsize $ENV_POOLSIZE)"
  if kubectl -n "$NS_FN" get environment "$ENV_NAME" >/dev/null 2>&1; then
    echo "   ya existe (deploy.sh solo le cambia la imagen)"
    kubectl -n "$NS_FN" get environment "$ENV_NAME" \
      -o jsonpath='   runtime.image={.spec.runtime.image}{"\n"}'
  else
    # version y poolsize no los fija deploy.sh: se crean aqui para reproducir el cluster.
    fission env create --name "$ENV_NAME" --envNamespace "$NS_FN" \
      --version "$ENV_VERSION" --poolsize "$ENV_POOLSIZE" --image "$ENV_BASE_IMAGE"
  fi
}

step_normalizer() {
  say "normalizer + consumer (deploy.sh, idempotente)"
  bash "$HERE/fission/normalizer/deploy.sh"
}

step_scraper() {
  need docker; need minikube; need kubectl
  ensure_ns "$NS_SCRAPPERS"

  say "secretos de los scrapers (USER_AGENT)"
  kubectl apply -k "$HERE/scrappers/k8s/"

  say "imagen '$SCRAPER_IMAGE' + CronJob '$SCRAPER_CRONJOB' (0 2 * * *)"
  docker build -t "$SCRAPER_IMAGE" "$HERE/scrappers/scrapper_mercadona/"
  minikube image load "$SCRAPER_IMAGE"
  kubectl apply -k "$HERE/scrappers/scrapper_mercadona/"
  kubectl -n "$NS_SCRAPPERS" get cronjob "$SCRAPER_CRONJOB"
}

step_verify() {
  need kubectl
  say "namespaces"
  kubectl get namespaces | grep -E "NAME|$NS_SCRAPPERS|$NS_MSG|$NS_FISSION|$NS_FN" || true

  say "fission (ns $NS_FN)"
  kubectl -n "$NS_FN" get environment,function,httptrigger 2>/dev/null || true
  kubectl -n "$NS_FN" get deploy "$CONSUMER_DEPLOY" \
    -o jsonpath='   consumer image={.spec.template.spec.containers[0].image} ready={.status.readyReplicas}/{.status.replicas}{"\n"}' 2>/dev/null || true

  say "pods en fases raras (todo el cluster)"
  kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded || true

  say "nats"
  nats_cli stream info "$STREAM" 2>/dev/null | grep -Ei "subjects|messages|maximum age|deleted" || true
  nats_cli consumer info "$STREAM" "$DURABLE" 2>/dev/null \
    | grep -Ei "filter subject|deliver subject|max ack pending|unprocessed" || true

  say "scraper"
  kubectl -n "$NS_SCRAPPERS" get cronjob "$SCRAPER_CRONJOB" 2>/dev/null || true

  cat <<'TXT'

Para probar sin esperar a las 02:00 (y borrar el job al terminar: el CronJob solo
limpia los suyos, los creados a mano se quedan):

  kubectl create job --from=cronjob/scrapper-mercadona prueba-manual -n scrappers
  kubectl -n default logs deploy/normalizer-consumer --since=10m | tail
  #   esperado: ~4592 productos -> 92 lotes (91x50 + 42) y 0 errores
  kubectl -n scrappers delete job prueba-manual

TXT
}

case "${1:-all}" in
  all)        step_base; step_namespaces; step_nats; step_fission; step_normalizer; step_scraper; step_verify ;;
  base)       step_base ;;
  namespaces) step_namespaces ;;
  nats)       step_nats ;;
  fission)    step_fission ;;
  normalizer) step_normalizer ;;
  scraper)    step_scraper ;;
  verify)     step_verify ;;
  *) printf 'uso: %s [all|base|namespaces|nats|fission|normalizer|scraper|verify]\n' "$0" >&2; exit 2 ;;
esac
