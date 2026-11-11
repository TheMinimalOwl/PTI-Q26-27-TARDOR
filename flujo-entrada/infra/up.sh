#!/usr/bin/env bash
#
# Levanta la ingesta completa desde cero con un solo comando:
#
#   bash flujo-entrada/infra/up.sh
#
# 1. bootstrap.sh: en una VM Ubuntu/Debian recien instalada pone docker (con sudo),
#    kubectl, minikube, helm y terraform (en ~/.local/bin) y sube el limite de inotify.
# 2. Arranca un perfil de minikube propio (por defecto `ingesta`) si no existe.
# 3. terraform apply: imagenes, namespaces, NATS + JetStream (NACK), Fission, normalizer,
#    consumer y CronJob del scraper.
# 4. Prueba de humo contra el router de Fission y estado de NATS.
# 5. Con E2E=1, ademas, e2e.sh: una pasada real del scraper hasta scraper.mercadona.clean.
#
# Es idempotente: repetirlo solo reconstruye/actualiza lo que haya cambiado.
#
# Variables (valores por defecto entre parentesis):
#   MINIKUBE_PROFILE (ingesta)  MINIKUBE_CPUS (2)  MINIKUBE_MEMORY (4g)
#   MINIKUBE_DRIVER (docker)    K8S_VERSION (v1.37.0)  SKIP_SMOKE (0)  E2E (0)
#   y las de bootstrap.sh (KUBECTL_VERSION, MINIKUBE_VERSION, HELM_VERSION, TF_VERSION).
#
# Requisito unico: Ubuntu/Debian con sudo (solo para instalar docker la primera vez).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$HERE/terraform"

PROFILE="${MINIKUBE_PROFILE:-ingesta}"
CPUS="${MINIKUBE_CPUS:-2}"
MEMORY="${MINIKUBE_MEMORY:-4g}"
DRIVER="${MINIKUBE_DRIVER:-docker}"
K8S_VERSION="${K8S_VERSION:-v1.37.0}"
SKIP_SMOKE="${SKIP_SMOKE:-0}"
E2E="${E2E:-0}"

say()  { printf '\n== %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "falta '$1' en el PATH"; }

export PATH="$HOME/.local/bin:$PATH"

step_tools() {
  local rc=0
  bash "$HERE/bootstrap.sh" || rc=$?
  if [ "$rc" = 10 ]; then
    # Docker recien instalado: el grupo `docker` no vale hasta la proxima sesion, asi
    # que me relanzo dentro del grupo (solo una vez).
    [ -z "${UP_SH_SG:-}" ] || die "sigo sin acceso a docker tras 'sg docker'"
    echo "   relanzando up.sh dentro del grupo docker"
    exec sg docker -c "UP_SH_SG=1 bash $(printf '%q' "$HERE/up.sh") $(printf '%q ' "$@")"
  fi
  [ "$rc" = 0 ] || die "bootstrap.sh ha fallado"
  docker info >/dev/null 2>&1 || die "docker no responde (revisa permisos del usuario)"
}

# Con dos clusters de minikube a la vez, el limite por defecto de inotify (128 instancias)
# se agota y kube-proxy del segundo cae en CrashLoop ("too many open files"): el nodo se
# queda NotReady y nada se programa. Aviso antes de arrancar.
check_inotify() {
  local limit others
  limit="$(sysctl -n fs.inotify.max_user_instances 2>/dev/null || echo 0)"
  others="$(minikube profile list -o json 2>/dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(" ".join(p["Name"] for p in d.get("valid", []) if p["Name"] != sys.argv[1] and p.get("Status") == "OK"))
' "$PROFILE" 2>/dev/null || true)"
  if [ -n "$others" ] && [ "$limit" -lt 512 ]; then
    printf 'AVISO: hay otro perfil de minikube en marcha (%s) y fs.inotify.max_user_instances=%s.\n' "$others" "$limit" >&2
    printf '  El nodo de %s probablemente se quedara NotReady. Soluciones:\n' "$PROFILE" >&2
    printf '    sudo sysctl -w fs.inotify.max_user_instances=512   (o)   minikube stop -p %s\n' "${others%% *}" >&2
    [ "${FORCE:-0}" = 1 ] || die "abortado (FORCE=1 para seguir igualmente)"
  fi
}

step_cluster() {
  say "minikube, perfil '$PROFILE'"
  if minikube -p "$PROFILE" status >/dev/null 2>&1; then
    echo "   ya esta en marcha"
  else
    check_inotify
    # Perfil nuevo o parado. Si el perfil no existia, el estado de terraform (si lo hay)
    # describe un cluster que ya no existe: se descarta para empezar limpio.
    if ! minikube profile list -o json 2>/dev/null | grep -q "\"Name\":\"$PROFILE\""; then
      rm -f "$TF_DIR"/terraform.tfstate "$TF_DIR"/terraform.tfstate.backup
    fi
    minikube start -p "$PROFILE" --driver="$DRIVER" --cpus="$CPUS" --memory="$MEMORY" \
      --kubernetes-version="$K8S_VERSION" \
      --addons=storage-provisioner,default-storageclass
  fi
  # minikube start ya cambia el contexto; lo fijo tambien si el perfil ya existia.
  kubectl config use-context "$PROFILE" >/dev/null
  echo "   contexto de kubectl: $(kubectl config current-context)"
}

step_apply() {
  say "terraform apply"
  local args=(-input=false -no-color
    -var "minikube_profile=$PROFILE" -var "kubeconfig=${KUBECONFIG:-$HOME/.kube/config}")
  # Reintentos: providers, charts y CRDs se bajan de internet (GitHub a veces da 500,
  # el DNS de la red de la UPC a veces falla).
  # El plan completo (con los CRDs de Fission son ~40.000 lineas) va a un fichero; en
  # pantalla solo el resumen de que se crea/cambia/borra y el progreso del apply.
  local i plan_txt="$TF_DIR/last-plan.txt"
  for i in 1 2 3; do
    terraform -chdir="$TF_DIR" init -input=false -upgrade=false >/dev/null \
      && terraform -chdir="$TF_DIR" plan "${args[@]}" -out=tfplan >"$plan_txt" \
      && { grep -E '^  # .* (will be|must be)|^Plan:|^No changes' "$plan_txt" | sed 's/^  //' || true; } \
      && echo "   (plan completo en $plan_txt)" \
      && terraform -chdir="$TF_DIR" apply -input=false tfplan && return 0
    [ "$i" = 3 ] && die "terraform apply ha fallado 3 veces"
    echo "   apply fallido (intento $i/3); reintento en 30 s"
    sleep 30
  done
}

step_smoke() {
  [ "$SKIP_SMOKE" = 1 ] && return
  say "estado de JetStream (NACK)"
  kubectl -n messaging get streams.jetstream.nats.io,consumers.jetstream.nats.io

  # Misma prueba que deploy.sh: una linea de Mercadona -> precio unitario de la fuente.
  bash "$HERE/../fission/normalizer/deploy.sh" smoke

  say "listo"
  terraform -chdir="$TF_DIR" output -raw prueba_manual
}

step_e2e() {
  [ "$E2E" = 1 ] || return 0
  MINIKUBE_PROFILE="$PROFILE" \
    FN_NAMESPACE="$(terraform -chdir="$TF_DIR" output -raw functions_namespace)" \
    bash "$HERE/e2e.sh"
}

step_tools "$@"
step_cluster
step_apply
step_smoke
step_e2e
