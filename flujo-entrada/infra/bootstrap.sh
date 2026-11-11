#!/usr/bin/env bash
#
# Deja una VM Ubuntu/Debian recien instalada lista para `up.sh`. Lo llama up.sh, pero se
# puede ejecutar solo. Es idempotente: lo que ya esta instalado no se toca.
#
#   bash flujo-entrada/infra/bootstrap.sh
#
# Con sudo (lo pide una vez si hace falta):
#   - paquetes base: ca-certificates, curl, python3, unzip
#   - Docker Engine desde el repo oficial de Docker + el usuario en el grupo `docker`
#   - fs.inotify.max_user_instances=512 (si no, dos minikube a la vez dejan el nodo NotReady)
#
# Sin sudo, en ~/.local/bin, con version fija y checksum:
#   - kubectl, minikube, helm y terraform
#
# Si ya hay una version distinta en el PATH, se respeta y solo se avisa.
#
# Variables: KUBECTL_VERSION MINIKUBE_VERSION HELM_VERSION TF_VERSION (ver abajo).
set -euo pipefail

KUBECTL_VERSION="${KUBECTL_VERSION:-v1.37.1}"
MINIKUBE_VERSION="${MINIKUBE_VERSION:-v1.39.0}"
HELM_VERSION="${HELM_VERSION:-v3.16.3}"
TF_VERSION="${TF_VERSION:-1.17.1}"
INOTIFY_INSTANCES=512

BIN="$HOME/.local/bin"
ME="$(id -un)"
export PATH="$BIN:$PATH"

say()  { printf '\n== %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

case "$(uname -m)" in
  x86_64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "arquitectura no soportada: $(uname -m)" ;;
esac

# sudo solo cuando hace falta; como root no se usa.
SUDO=""
as_root() {
  if [ "$(id -u)" = 0 ]; then "$@"; return; fi
  if [ -z "$SUDO" ]; then
    have sudo || die "hace falta root para '$*' y no hay sudo. Instalalo como root o pidelo al administrador."
    SUDO=sudo
  fi
  $SUDO "$@"
}

# --- paquetes del sistema --------------------------------------------------------------

step_os() {
  say "sistema"
  [ -r /etc/os-release ] || die "no encuentro /etc/os-release"
  . /etc/os-release
  echo "   $PRETTY_NAME ($ARCH)"
  case "${ID:-}:${ID_LIKE:-}" in
    ubuntu:*|debian:*|*:*debian*|*:*ubuntu*) ;;
    *) die "solo se soporta Ubuntu/Debian (apt); este sistema es '$ID'" ;;
  esac

  local missing=() p
  for p in curl python3 unzip; do have "$p" || missing+=("$p"); done
  [ -r /etc/ssl/certs/ca-certificates.crt ] || missing+=(ca-certificates)
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "   instalando: ${missing[*]}"
    as_root apt-get update -qq
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates "${missing[@]}"
  else
    echo "   curl, python3, unzip y ca-certificates ya estan"
  fi
}

# --- docker ----------------------------------------------------------------------------

step_docker() {
  say "docker"
  if ! have docker; then
    . /etc/os-release
    local distro="$ID"
    case "$distro" in ubuntu|debian) ;; *) distro="${ID_LIKE%% *}" ;; esac
    echo "   instalando Docker Engine (repo oficial de Docker, $distro $VERSION_CODENAME)"
    as_root install -m 0755 -d /etc/apt/keyrings
    as_root curl -fsSL "https://download.docker.com/linux/$distro/gpg" -o /etc/apt/keyrings/docker.asc
    as_root chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$distro $VERSION_CODENAME stable" \
      | as_root tee /etc/apt/sources.list.d/docker.list >/dev/null
    as_root apt-get update -qq
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      docker-ce docker-ce-cli containerd.io docker-buildx-plugin
  fi
  echo "   $(docker --version)"

  # El servicio: con systemd se habilita; sin systemd (p. ej. un contenedor) no se puede.
  # Primero sin sudo: si el usuario ya puede usar docker, no hay nada que hacer aqui.
  if docker info >/dev/null 2>&1; then
    echo "   demonio en marcha y accesible para $ME"
    return
  fi
  if ! as_root docker info >/dev/null 2>&1; then
    if have systemctl && [ -d /run/systemd/system ]; then
      as_root systemctl enable --now docker
    else
      die "el demonio de docker no esta en marcha y no hay systemd para arrancarlo"
    fi
  fi

  # Usuario en el grupo docker (minikube con driver docker no funciona como root).
  if [ "$(id -u)" != 0 ] && ! id -nG "$ME" | tr ' ' '\n' | grep -qx docker; then
    echo "   anadiendo '$ME' al grupo docker"
    as_root usermod -aG docker "$ME"
  fi
  if ! docker info >/dev/null 2>&1; then
    # El grupo nuevo no vale en esta sesion: up.sh se relanza con `sg docker`.
    echo "   (el grupo docker se aplica en la proxima sesion; up.sh se relanza con 'sg docker')"
    DOCKER_NEEDS_SG=1
  fi
}

# --- inotify ---------------------------------------------------------------------------

step_inotify() {
  say "inotify"
  local cur
  cur="$(sysctl -n fs.inotify.max_user_instances 2>/dev/null || echo 0)"
  if [ "$cur" -ge "$INOTIFY_INSTANCES" ]; then
    echo "   max_user_instances=$cur"
    return
  fi
  echo "   max_user_instances=$cur -> $INOTIFY_INSTANCES (persistente en /etc/sysctl.d)"
  echo "fs.inotify.max_user_instances=$INOTIFY_INSTANCES" \
    | as_root tee /etc/sysctl.d/99-ingesta-inotify.conf >/dev/null
  as_root sysctl -q -w "fs.inotify.max_user_instances=$INOTIFY_INSTANCES" \
    || echo "   AVISO: no he podido aplicarlo ahora (¿contenedor?); se aplicara al reiniciar" >&2
}

# --- binarios en ~/.local/bin ----------------------------------------------------------

# instala <nombre> <version_esperada> <comando_version> <funcion_descarga>
ensure_bin() {
  local name="$1" want="$2" vcmd="$3" fetch="$4"
  if have "$name"; then
    local got
    got="$(eval "$vcmd" 2>/dev/null | head -1 || true)"
    if printf '%s' "$got" | grep -qF "${want#v}"; then
      echo "   $name $want"
    else
      echo "   $name ya esta ($got); se esperaba $want: lo respeto" >&2
    fi
    return
  fi
  echo "   instalando $name $want en $BIN"
  mkdir -p "$BIN"
  local tmp
  tmp="$(mktemp -d)"
  ( cd "$tmp" && "$fetch" ) || { rm -rf "$tmp"; die "no he podido instalar $name"; }
  install -m 0755 "$tmp/$name" "$BIN/$name"
  rm -rf "$tmp"
}

# Descarga $1 a $2 y comprueba que su sha256 es $3.
get_checked() {
  curl -fsSL --retry 3 -o "$2" "$1"
  echo "$3  $2" | sha256sum -c --quiet - || die "checksum incorrecto: $1"
}

fetch_kubectl() {
  local u="https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/$ARCH/kubectl"
  get_checked "$u" kubectl "$(curl -fsSL --retry 3 "$u.sha256")"
}

fetch_minikube() {
  local u="https://github.com/kubernetes/minikube/releases/download/$MINIKUBE_VERSION/minikube-linux-$ARCH"
  get_checked "$u" minikube "$(curl -fsSL --retry 3 "$u.sha256" | awk '{print $1}')"
}

fetch_helm() {
  local f="helm-$HELM_VERSION-linux-$ARCH.tar.gz"
  get_checked "https://get.helm.sh/$f" "$f" "$(curl -fsSL --retry 3 "https://get.helm.sh/$f.sha256sum" | awk '{print $1}')"
  tar -xzf "$f" && mv "linux-$ARCH/helm" helm
}

fetch_terraform() {
  local f="terraform_${TF_VERSION}_linux_${ARCH}.zip" base="https://releases.hashicorp.com/terraform/$TF_VERSION"
  get_checked "$base/$f" "$f" "$(curl -fsSL --retry 3 "$base/terraform_${TF_VERSION}_SHA256SUMS" | awk -v f="$f" '$2==f {print $1}')"
  unzip -q -o "$f" terraform
}

step_bins() {
  say "kubectl, minikube, helm y terraform"
  ensure_bin kubectl   "$KUBECTL_VERSION"  "kubectl version --client"  fetch_kubectl
  ensure_bin minikube  "$MINIKUBE_VERSION" "minikube version --short" fetch_minikube
  ensure_bin helm      "$HELM_VERSION"     "helm version --short"     fetch_helm
  ensure_bin terraform "$TF_VERSION"       "terraform version"        fetch_terraform

  if ! grep -qs '\.local/bin' "$HOME/.profile" "$HOME/.bashrc" 2>/dev/null; then
    echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$HOME/.bashrc"
    echo "   ~/.local/bin anadido al PATH en ~/.bashrc"
  fi
}

DOCKER_NEEDS_SG=0
step_os
step_docker
step_inotify
step_bins

if [ "$DOCKER_NEEDS_SG" = 1 ]; then
  # Codigo de salida especial para que up.sh se relance dentro del grupo docker.
  exit 10
fi
say "bootstrap listo"
