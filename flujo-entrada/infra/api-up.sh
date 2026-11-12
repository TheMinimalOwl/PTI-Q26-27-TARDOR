#!/usr/bin/env bash
#
# Despliega la parte de API y BD del equipo de API/BD (carpeta api/) en el MISMO cluster
# de la ingesta, como un despliegue aparte (namespace `api`):
#
#   bash flujo-entrada/infra/api-up.sh          # despues de up.sh
#   API=1 bash flujo-entrada/infra/up.sh        # o todo de una vez
#
# No toca nada de api/: construye su imagen y aplica sus manifiestos (api/k8s/) tal cual.
# - PostgreSQL + pgvector (StatefulSet con volumen), Redis, la API (2 replicas) y el writer.
# - El writer lee `scraper.*.clean` del NATS de `messaging` (durable `api-writer`) y
#   escribe en PostgreSQL: con esto, lo que publica la ingesta acaba en la BD.
#
# Tiene que ser el mismo cluster porque el writer llega a NATS por el DNS interno
# (nats.messaging.svc.cluster.local).
#
# Despues comprueba /health y cuenta filas en la BD. Es idempotente.
#
# Variables: MINIKUBE_PROFILE (ingesta)  API_DIR (<repo>/api)  WAIT_DATA (120 s)
# Quitarlo:  kubectl --context ingesta delete -k api/k8s/   (borra tambien el volumen de la BD)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
API_DIR="${API_DIR:-$REPO/api}"
PROFILE="${MINIKUBE_PROFILE:-ingesta}"
WAIT_DATA="${WAIT_DATA:-120}"
IMAGE="pti/api:dev"   # el nombre que usan api/k8s/api.yaml y writer.yaml

export PATH="$HOME/.local/bin:$PATH"
say() { printf '\n== %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
k()   { kubectl --context "$PROFILE" "$@"; }
sql() { k -n api exec statefulset/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$1"' _ "$1"; }

[ -f "$API_DIR/k8s/kustomization.yaml" ] || die "no encuentro $API_DIR/k8s (API_DIR)"
minikube -p "$PROFILE" status >/dev/null 2>&1 || die "el cluster '$PROFILE' no esta en marcha: lanza antes up.sh"
k -n messaging get svc nats >/dev/null 2>&1 || die "no hay NATS en 'messaging': lanza antes up.sh"

say "imagen $IMAGE (docker build + minikube image load)"
docker build -q -t "$IMAGE" "$API_DIR" >/dev/null
minikube -p "$PROFILE" image load --overwrite=true "$IMAGE"
minikube -p "$PROFILE" image ls | grep -q "${IMAGE}" || die "la imagen no ha llegado al nodo"

say "manifiestos de api/k8s (namespace api)"
k apply -k "$API_DIR/k8s/"
# Misma etiqueta `dev`: se reinician para que cojan la imagen recien cargada.
k -n api rollout restart deploy/api deploy/writer >/dev/null

say "esperando a PostgreSQL, Redis, API y writer"
k -n api rollout status statefulset/postgres --timeout=300s
for d in redis api writer; do k -n api rollout status "deploy/$d" --timeout=300s; done

say "comprobaciones"
health="$(k -n api exec deploy/api -- python -c 'import urllib.request;print(urllib.request.urlopen("http://localhost:8000/health",timeout=10).read().decode())')"
echo "   /health: $health"

# El writer carga lo que ya haya en scraper.*.clean (el stream guarda 7 dias).
deadline=$((SECONDS + WAIT_DATA))
until n="$(sql 'select count(*) from prices' 2>/dev/null)" && [ "${n:-0}" -gt 0 ]; do
  [ "$SECONDS" -lt "$deadline" ] || { echo "   (sin precios todavia: normal si aun no ha corrido ningun scraper)"; break; }
  sleep 5
done
echo "   filas en la BD por cadena:"
sql "select c.slug, count(distinct p.id) productos, count(pr.id) precios
     from chains c left join products p on p.chain_id=c.id left join prices pr on pr.product_id=p.id
     group by c.slug order by c.slug" | sed 's/^/     /'
pend="$(k -n messaging exec deploy/nats-box -- nats -s nats://nats:4222 consumer info SCRAPERS api-writer --json 2>/dev/null \
        | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["num_pending"]+d["num_ack_pending"])' 2>/dev/null || echo '?')"
echo "   mensajes clean pendientes para el writer: $pend"

say "listo"
cat <<EOF
# API en http://localhost:8000/docs:
kubectl --context $PROFILE -n api port-forward svc/api 8000:80
# logs del writer (lotes que va cargando):
kubectl --context $PROFILE -n api logs deploy/writer -f
EOF
