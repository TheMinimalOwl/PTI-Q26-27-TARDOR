#!/usr/bin/env bash
#
# Publica la API (Service api/api) en internet con un Cloudflare quick tunnel:
#
#   bash flujo-entrada/infra/tunnel-up.sh          # despliega (idempotente) y da la URL
#   bash flujo-entrada/infra/tunnel-up.sh --url    # solo dice la URL actual
#   bash flujo-entrada/infra/tunnel-up.sh --down   # lo quita
#
# La URL (https://<aleatorio>.trycloudflare.com) cambia cada vez que el pod se reinicia,
# p. ej. tras reiniciar la VM: vuelve a mirarla con --url. Necesita api-up.sh antes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${MINIKUBE_PROFILE:-ingesta}"
MANIFEST="$HERE/tunnel/cloudflared.yaml"

export PATH="$HOME/.local/bin:$PATH"
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
k()   { kubectl --context "$PROFILE" "$@"; }

# El pod registra la URL en sus logs al abrir el tunel.
url() {
  k -n api logs deploy/cloudflared 2>/dev/null \
    | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1
}

case "${1:-}" in
  --url)
    u="$(url)"; [ -n "$u" ] || die "no hay tunel en marcha (lanza tunnel-up.sh)"
    echo "$u"; exit 0 ;;
  --down)
    k delete -f "$MANIFEST" --ignore-not-found; exit 0 ;;
  "") ;;
  *) die "uso: $0 [--url|--down]" ;;
esac

k -n api get svc api >/dev/null 2>&1 || die "no hay Service api en el namespace api: lanza antes api-up.sh"

k apply -f "$MANIFEST"
k -n api rollout status deploy/cloudflared --timeout=180s

u=""
for _ in $(seq 30); do u="$(url)"; [ -n "$u" ] && break; sleep 2; done
[ -n "$u" ] || die "el tunel no ha dado URL (kubectl -n api logs deploy/cloudflared)"

# El DNS de trycloudflare tarda unos segundos en propagarse.
code=000
for _ in $(seq 30); do
  code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$u/health" || true)"
  [ "$code" = 200 ] && break; sleep 3
done
echo "API publica: $u   (docs: $u/docs, /health -> $code)"
[ "$code" = 200 ] || echo "aviso: /health aun no responde 200; prueba de nuevo en un minuto"
