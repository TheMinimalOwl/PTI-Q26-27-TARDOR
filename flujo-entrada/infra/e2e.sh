#!/usr/bin/env bash
#
# Prueba de extremo a extremo de la ingesta ya desplegada (con up.sh):
#
#   bash flujo-entrada/infra/e2e.sh                  # todas las cadenas (mercadona consum)
#   CHAINS=consum bash flujo-entrada/infra/e2e.sh    # solo una
#
# Para cada cadena, a la vez:
# 1. Lanza un Job desde su CronJob (como el de las 02:00) y espera a que acabe.
# 2. Comprueba en su log que ha publicado productos en scraper.<cadena>.raw (> 0).
# Despues:
# 3. Espera a que el consumidor `normalizer` lo procese todo y a que aparezcan lotes nuevos
#    en scraper.<cadena>.clean de cada cadena, que es la salida hacia API/BD.
#
# Sale con 0 solo si todo eso se cumple. Necesita internet (baja los catalogos).
#
# Variables: CHAINS ("mercadona consum")  MINIKUBE_PROFILE (ingesta)  FN_NAMESPACE (ingesta)
#            JOB_TIMEOUT (1200 s)  DRAIN_TIMEOUT (600 s)  KEEP_JOB (0)
set -euo pipefail

CHAINS="${CHAINS:-mercadona consum}"
PROFILE="${MINIKUBE_PROFILE:-ingesta}"
FN_NS="${FN_NAMESPACE:-ingesta}"
JOB_TIMEOUT="${JOB_TIMEOUT:-1200}"
DRAIN_TIMEOUT="${DRAIN_TIMEOUT:-600}"
STREAM="SCRAPERS"
STAMP="$(date +%Y%m%d%H%M%S)"

export PATH="$HOME/.local/bin:$PATH"
k()    { kubectl --context "$PROFILE" "$@"; }
nats() { k -n messaging exec deploy/nats-box -- nats -s nats://nats:4222 "$@"; }
say()  { printf '\n== %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
job()  { echo "e2e-$1-$STAMP"; }

# Mensajes por subject dentro del stream, como "subject=n" (una linea por subject).
counts() {
  nats stream subjects "$STREAM" --json 2>/dev/null \
    | python3 -c 'import json,sys; [print(f"{k}={v}") for k,v in json.load(sys.stdin).items()]'
}
count() { counts | sed -n "s/^$1=//p" | grep . || echo 0; }
# Campo numerico del consumidor durable `normalizer`.
consumer_field() {
  nats consumer info "$STREAM" normalizer --json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

cleanup() {
  [ "${KEEP_JOB:-0}" = 1 ] && return
  local c
  for c in $CHAINS; do k -n scrappers delete job "$(job "$c")" --ignore-not-found >/dev/null 2>&1 || true; done
}
trap cleanup EXIT

declare -A CLEAN0 PUBLISHED
say "estado inicial"
for c in $CHAINS; do
  k -n scrappers get cronjob "scrapper-$c" >/dev/null 2>&1 || die "no existe el CronJob scrapper-$c"
  CLEAN0[$c]="$(count "scraper.$c.clean")"
  echo "   $c: raw=$(count "scraper.$c.raw") clean=${CLEAN0[$c]}"
done

say "scrapers: lanzando $(echo $CHAINS | wc -w) Jobs (timeout ${JOB_TIMEOUT}s)"
for c in $CHAINS; do
  k -n scrappers create job --from="cronjob/scrapper-$c" "$(job "$c")" >/dev/null
  echo "   $(job "$c")"
done

# Espera a que todos acaben (Complete o Failed).
deadline=$((SECONDS + JOB_TIMEOUT))
pending="$CHAINS"
while [ -n "$pending" ]; do
  still=""
  for c in $pending; do
    j="$(job "$c")"
    st="$(k -n scrappers get job "$j" -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type}{" "}{end}')"
    case "$st" in
      *Complete*) echo "   $c: terminado" ;;
      *Failed*)   k -n scrappers logs "job/$j" --tail=30 || true; die "el Job de $c ha fallado" ;;
      *)          still="$still $c" ;;
    esac
  done
  pending="${still# }"
  [ -z "$pending" ] && break
  [ "$SECONDS" -lt "$deadline" ] || die "no han acabado en ${JOB_TIMEOUT}s: $pending"
  sleep 15
done

for c in $CHAINS; do
  log="$(k -n scrappers logs "job/$(job "$c")")"
  printf '%s\n' "$log" | grep -E '^(200|nats:|   [0-9]{5}:)' | sed "s/^ */   $c: /"
  # Mercadona acaba con 0 aunque no haya bajado nada (fallo silencioso conocido): se mira el log.
  # Una linea "nats: N -> ..." por tienda (codigo postal): se suman.
  n="$(printf '%s\n' "$log" | sed -n "s/^nats: \([0-9]*\) -> scraper\.$c\.raw.*/\1/p" | awk '{s+=$1} END {print s+0}')"
  [ -n "$n" ] && [ "$n" -gt 0 ] || die "$c no ha publicado nada (fallo de red puntual: relanza e2e.sh)"
  PUBLISHED[$c]="$n"
done

say "normalizador: esperando a que procese todo (timeout ${DRAIN_TIMEOUT}s)"
deadline=$((SECONDS + DRAIN_TIMEOUT))
while :; do
  pend="$(consumer_field num_pending)"; acks="$(consumer_field num_ack_pending)"
  ok=1; line=""
  for c in $CHAINS; do
    new=$(( $(count "scraper.$c.clean") - CLEAN0[$c] ))
    line="$line $c=+$new"
    [ "$new" -gt 0 ] || ok=0
  done
  echo "   pendientes=$pend sin_ack=$acks lotes nuevos:$line"
  [ "$pend" = 0 ] && [ "$acks" = 0 ] && [ "$ok" = 1 ] && break
  [ "$SECONDS" -lt "$deadline" ] || {
    k -n "$FN_NS" logs deploy/normalizer-consumer --tail=30 || true
    die "el normalizador no ha vaciado la cola en ${DRAIN_TIMEOUT}s"
  }
  sleep 10
done

errores="$(k -n "$FN_NS" logs deploy/normalizer-consumer --since=1h 2>/dev/null | grep -c 'ERROR' || true)"
say "OK"
for c in $CHAINS; do
  new=$(( $(count "scraper.$c.clean") - CLEAN0[$c] ))
  echo "   $c: ${PUBLISHED[$c]} productos -> $new lotes nuevos en scraper.$c.clean (~$(( (PUBLISHED[$c] + 49) / 50 )) esperados con lotes de 50)"
done
echo "   lineas ERROR en el log del consumer (ultima hora): $errores"
echo "   la salida queda en el stream $STREAM para el writer de API/BD (durable api-writer)"
