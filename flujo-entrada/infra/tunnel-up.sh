#!/usr/bin/env bash
#
# Publica la API (Service api/api) en internet con el Cloudflare Tunnel del equipo:
#
#   bash flujo-entrada/infra/tunnel-up.sh          # despliega (idempotente) y comprueba
#   TUNNEL_TOKEN=<token> bash flujo-entrada/infra/tunnel-up.sh   # la 1a vez: guarda el token
#   bash flujo-entrada/infra/tunnel-up.sh --url    # dice la URL publica
#   bash flujo-entrada/infra/tunnel-up.sh --down   # lo quita
#
# El token va en el Secret api/cloudflared-token (lo crea este script si se le pasa
# TUNNEL_TOKEN; no va en el repo). El hostname, en tunnel/cloudflared.yaml.
# La URL es fija. Necesita api-up.sh antes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${MINIKUBE_PROFILE:-ingesta}"
MANIFEST="$HERE/tunnel/cloudflared.yaml"

export PATH="$HOME/.local/bin:$PATH"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
k()   { kubectl --context "$PROFILE" "$@"; }

# Hostname: anotacion superahorro/hostname del manifiesto.
host="$(sed -n 's/^ *superahorro\/hostname: *"\{0,1\}\([^"]*\)"\{0,1\} *$/\1/p' "$MANIFEST")"
host="${host#https://}"; host="${host%/}"
case "$host" in ""|PON_AQUI*) die "pon el hostname del tunel en $MANIFEST (superahorro/hostname)" ;; esac
PUBLIC_URL="https://$host"

case "${1:-}" in
  --url)  echo "$PUBLIC_URL"; exit 0 ;;
  --down) k delete -f "$MANIFEST" --ignore-not-found; exit 0 ;;
  "") ;;
  *) die "uso: $0 [--url|--down]" ;;
esac

k -n api get svc api >/dev/null 2>&1 || die "no hay Service api en el namespace api: lanza antes api-up.sh"

# Token del tunel (panel de Cloudflare > Zero Trust > Networks > Tunnels): en un Secret.
if [ -n "${TUNNEL_TOKEN:-}" ]; then
  k -n api create secret generic cloudflared-token --from-literal=TUNNEL_TOKEN="$TUNNEL_TOKEN" \
    --dry-run=client -o yaml | k apply -f - >/dev/null
  echo "token guardado en el Secret api/cloudflared-token"
fi
k -n api get secret cloudflared-token >/dev/null 2>&1 \
  || die "falta el token del tunel: TUNNEL_TOKEN=<token> bash $0"

k apply -f "$MANIFEST"
k -n api rollout status deploy/cloudflared --timeout=180s

# Cada pod registra sus conexiones con el edge en los logs.
conns=0
for _ in $(seq 30); do
  conns="$(k -n api logs -l app=cloudflared --tail=-1 2>/dev/null \
    | grep -c 'Registered tunnel connection' || true)"
  [ "$conns" -gt 0 ] && break; sleep 2
done
[ "$conns" -gt 0 ] || die "el tunel no conecta con Cloudflare (kubectl -n api logs -l app=cloudflared)"
echo "tunel conectado ($conns conexiones con el edge)"

code=000
for _ in $(seq 10); do
  code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$PUBLIC_URL/health" || true)"
  [ "$code" = 200 ] && break; sleep 3
done
echo "API publica: $PUBLIC_URL   (docs: $PUBLIC_URL/docs, /health -> $code)"
[ "$code" = 200 ] || echo "aviso: /health no responde 200; revisa que el hostname del panel de Cloudflare apunte a http://api.api.svc.cluster.local:80"
