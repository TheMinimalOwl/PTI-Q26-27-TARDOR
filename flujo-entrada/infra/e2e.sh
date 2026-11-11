#!/usr/bin/env bash
#
# Prueba de extremo a extremo de la ingesta ya desplegada (con up.sh):
#
#   bash flujo-entrada/infra/e2e.sh                       # todos los scrapers
#   SCRAPERS=consum bash flujo-entrada/infra/e2e.sh       # solo uno
#
# SCRAPERS son los CronJobs (scrapper-<nombre>). Las cadenas publicadas se sacan del log de
# cada Job ("nats: N -> scraper.<cadena>.raw").
#
# 1. Lanza un Job desde cada CronJob (como el de las 02:00), a la vez, y espera a que acaben.
# 2. Comprueba en sus logs que cada uno ha publicado productos (> 0).
# 3. Espera a que el consumidor `normalizer` lo procese todo y a que aparezcan lotes nuevos
#    en scraper.<cadena>.clean de cada cadena publicada: la salida hacia API/BD.
#
# Sale con 0 solo si todo eso se cumple. Necesita internet (baja los catalogos).
#
# Variables: SCRAPERS ("mercadona consum caprabo condis")  MINIKUBE_PROFILE (ingesta)
#            FN_NAMESPACE (ingesta)  JOB_TIMEOUT (5400 s)  DRAIN_TIMEOUT (900 s)  KEEP_JOB (0)
set -euo pipefail

SCRAPERS="${SCRAPERS:-${CHAINS:-mercadona consum caprabo condis}}"
PROFILE="${MINIKUBE_PROFILE:-ingesta}"
FN_NS="${FN_NAMESPACE:-ingesta}"
JOB_TIMEOUT="${JOB_TIMEOUT:-5400}"
DRAIN_TIMEOUT="${DRAIN_TIMEOUT:-900}"
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
  local s
  for s in $SCRAPERS; do k -n scrappers delete job "$(job "$s")" --ignore-not-found >/dev/null 2>&1 || true; done
}
trap cleanup EXIT

say "estado inicial"
declare -A BEFORE PUBLISHED
while IFS='=' read -r subj n; do [ -n "$subj" ] && BEFORE[$subj]="$n"; done < <(counts)
for s in $SCRAPERS; do
  k -n scrappers get cronjob "scrapper-$s" >/dev/null 2>&1 || die "no existe el CronJob scrapper-$s"
done
for subj in $(printf '%s\n' "${!BEFORE[@]}" | sort); do echo "   $subj=${BEFORE[$subj]}"; done

say "scrapers: lanzando $(echo $SCRAPERS | wc -w) Jobs (timeout ${JOB_TIMEOUT}s)"
for s in $SCRAPERS; do
  k -n scrappers create job --from="cronjob/scrapper-$s" "$(job "$s")" >/dev/null
  echo "   $(job "$s")"
done

# Espera a que todos acaben (Complete o Failed).
deadline=$((SECONDS + JOB_TIMEOUT))
pending="$SCRAPERS"
while [ -n "$pending" ]; do
  still=""
  for s in $pending; do
    j="$(job "$s")"
    st="$(k -n scrappers get job "$j" -o jsonpath='{range .status.conditions[?(@.status=="True")]}{.type}{" "}{end}')"
    case "$st" in
      *Complete*) echo "   $s: terminado ($(( SECONDS / 60 )) min)" ;;
      *Failed*)   k -n scrappers logs "job/$j" --tail=30 || true; die "el Job de $s ha fallado" ;;
      *)          still="$still $s" ;;
    esac
  done
  pending="${still# }"
  [ -z "$pending" ] && break
  [ "$SECONDS" -lt "$deadline" ] || die "no han acabado en ${JOB_TIMEOUT}s: $pending"
  sleep 30
done

for s in $SCRAPERS; do
  log="$(k -n scrappers logs "job/$(job "$s")")"
  printf '%s\n' "$log" | grep -E '^(200|nats:|   [0-9]{5}:|   [a-z]+: (tienda|no reparte))' | sed "s/^ */   $s: /"
  # Una linea "nats: N -> scraper.<cadena>.raw" por tienda: se suman por cadena.
  found=0
  while read -r n chain; do
    PUBLISHED[$chain]=$(( ${PUBLISHED[$chain]:-0} + n )); found=$(( found + n ))
  done < <(printf '%s\n' "$log" | sed -n 's/^nats: \([0-9]*\) -> scraper\.\([a-z0-9-]*\)\.raw.*/\1 \2/p')
  [ "$found" -gt 0 ] || die "$s no ha publicado nada (fallo de red puntual: relanza e2e.sh)"
done
CHAINS_OUT="$(printf '%s\n' "${!PUBLISHED[@]}" | sort | tr '\n' ' ')"

say "normalizador: esperando a que procese todo (timeout ${DRAIN_TIMEOUT}s)"
deadline=$((SECONDS + DRAIN_TIMEOUT))
while :; do
  pend="$(consumer_field num_pending)"; acks="$(consumer_field num_ack_pending)"
  ok=1; line=""
  for c in $CHAINS_OUT; do
    new=$(( $(count "scraper.$c.clean") - ${BEFORE[scraper.$c.clean]:-0} ))
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

errores="$(k -n "$FN_NS" logs deploy/normalizer-consumer --since=2h 2>/dev/null | grep -c 'ERROR' || true)"
say "OK"
for c in $CHAINS_OUT; do
  new=$(( $(count "scraper.$c.clean") - ${BEFORE[scraper.$c.clean]:-0} ))
  echo "   $c: ${PUBLISHED[$c]} productos -> $new lotes nuevos en scraper.$c.clean (~$(( (PUBLISHED[$c] + 49) / 50 )) esperados con lotes de 50)"
done
echo "   lineas ERROR en el log del consumer (ultimas 2 h): $errores"
echo "   la salida queda en el stream $STREAM para el writer de API/BD (durable api-writer)"
