#!/usr/bin/env bash
#
# Prueba de extremo a extremo de la ingesta ya desplegada (con up.sh):
#
#   bash flujo-entrada/infra/e2e.sh
#
# 1. Lanza un Job desde el CronJob del scraper (como el de las 02:00) y espera a que acabe.
# 2. Comprueba en su log que ha publicado productos en scraper.mercadona.raw (> 0).
# 3. Espera a que el consumidor `normalizer` lo procese todo y a que aparezcan lotes nuevos
#    en scraper.mercadona.clean, que es la salida hacia API/BD.
#
# Sale con 0 solo si todo eso se cumple. Necesita internet (baja el catalogo de Mercadona).
#
# Variables: MINIKUBE_PROFILE (ingesta)  FN_NAMESPACE (ingesta)
#            JOB_TIMEOUT (900 s)  DRAIN_TIMEOUT (600 s)  KEEP_JOB (0)
set -euo pipefail

PROFILE="${MINIKUBE_PROFILE:-ingesta}"
FN_NS="${FN_NAMESPACE:-ingesta}"
JOB_TIMEOUT="${JOB_TIMEOUT:-900}"
DRAIN_TIMEOUT="${DRAIN_TIMEOUT:-600}"
STREAM="SCRAPERS"
RAW="scraper.mercadona.raw"
CLEAN="scraper.mercadona.clean"
JOB="e2e-$(date +%Y%m%d%H%M%S)"

export PATH="$HOME/.local/bin:$PATH"
k()    { kubectl --context "$PROFILE" "$@"; }
nats() { k -n messaging exec deploy/nats-box -- nats -s nats://nats:4222 "$@"; }
say()  { printf '\n== %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Mensajes de un subject dentro del stream (0 si aun no hay ninguno).
count() {
  nats stream subjects "$STREAM" --json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], 0))' "$1"
}
# Campo numerico del consumidor durable `normalizer`.
consumer_field() {
  nats consumer info "$STREAM" normalizer --json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

cleanup() {
  [ "${KEEP_JOB:-0}" = 1 ] || k -n scrappers delete job "$JOB" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup EXIT

say "estado inicial"
raw0="$(count "$RAW")"; clean0="$(count "$CLEAN")"
echo "   $RAW=$raw0  $CLEAN=$clean0"

say "scraper: Job $JOB (timeout ${JOB_TIMEOUT}s)"
k -n scrappers create job --from=cronjob/scrapper-mercadona "$JOB" >/dev/null
# Espera a Complete o Failed, lo que llegue antes.
deadline=$((SECONDS + JOB_TIMEOUT))
while :; do
  st="$(k -n scrappers get job "$JOB" -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type}{" "}{end}')"
  case "$st" in
    *Complete*) break ;;
    *Failed*)   k -n scrappers logs "job/$JOB" --tail=30 || true; die "el Job del scraper ha fallado" ;;
  esac
  [ "$SECONDS" -lt "$deadline" ] || { k -n scrappers logs "job/$JOB" --tail=30 || true; die "el Job no ha acabado en ${JOB_TIMEOUT}s"; }
  sleep 10
done
log="$(k -n scrappers logs "job/$JOB")"
printf '%s\n' "$log" | tail -3 | sed 's/^/   /'

# El scraper acaba con 0 aunque no haya bajado nada (fallo silencioso conocido): se mira el log.
published="$(printf '%s\n' "$log" | sed -n "s/^nats: \([0-9]*\) -> $RAW.*/\1/p" | tail -1)"
[ -n "$published" ] && [ "$published" -gt 0 ] \
  || die "el scraper no ha publicado nada (fallo de red puntual: relanza e2e.sh)"
echo "   publicados: $published"

say "normalizador: esperando a que procese todo (timeout ${DRAIN_TIMEOUT}s)"
deadline=$((SECONDS + DRAIN_TIMEOUT))
while :; do
  pending="$(consumer_field num_pending)"; acks="$(consumer_field num_ack_pending)"
  clean1="$(count "$CLEAN")"
  echo "   pendientes=$pending sin_ack=$acks lotes_nuevos=$((clean1 - clean0))"
  [ "$pending" = 0 ] && [ "$acks" = 0 ] && [ "$clean1" -gt "$clean0" ] && break
  [ "$SECONDS" -lt "$deadline" ] || {
    k -n "$FN_NS" logs deploy/normalizer-consumer --tail=30 || true
    die "el normalizador no ha vaciado la cola en ${DRAIN_TIMEOUT}s"
  }
  sleep 10
done

errores="$(k -n "$FN_NS" logs deploy/normalizer-consumer --since=1h 2>/dev/null | grep -c 'ERROR' || true)"
expected=$(( (published + 49) / 50 ))
say "OK"
echo "   $published productos -> $((clean1 - clean0)) lotes nuevos en $CLEAN (~$expected esperados con lotes de 50)"
echo "   lineas ERROR en el log del consumer (ultima hora): $errores"
echo "   la salida queda en el stream $STREAM para el writer de API/BD (durable api-writer)"
