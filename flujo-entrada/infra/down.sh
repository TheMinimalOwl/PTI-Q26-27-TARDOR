#!/usr/bin/env bash
#
# Desmonta la ingesta.
#
#   bash flujo-entrada/infra/down.sh            # borra el perfil de minikube entero (rapido)
#   bash flujo-entrada/infra/down.sh --keep     # terraform destroy, el cluster sigue vivo
#
# Variables: MINIKUBE_PROFILE (ingesta)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$HERE/terraform"
PROFILE="${MINIKUBE_PROFILE:-ingesta}"
export PATH="$HOME/.local/bin:$PATH"

case "${1:-}" in
  --keep)
    terraform -chdir="$TF_DIR" destroy -input=false -auto-approve \
      -var "minikube_profile=$PROFILE" -var "kubeconfig=${KUBECONFIG:-$HOME/.kube/config}"
    ;;
  "")
    minikube delete -p "$PROFILE"
    rm -f "$TF_DIR"/terraform.tfstate "$TF_DIR"/terraform.tfstate.backup
    ;;
  *) printf 'uso: %s [--keep]\n' "$0" >&2; exit 2 ;;
esac
