#!/usr/bin/env bash
#
# Arranque automatico del cluster tras reiniciar la VM.
#
# El contenedor de minikube tiene politica de reinicio `no`: si la VM se reinicia, no hay
# scrapers, NATS, API ni writer hasta que alguien lance `minikube start -p ingesta`. Este
# script lo deja programado:
#
#   bash flujo-entrada/infra/autostart.sh            # instala (idempotente)
#   bash flujo-entrada/infra/autostart.sh --remove   # lo quita
#   bash flujo-entrada/infra/autostart.sh --run      # lo que se ejecuta al arrancar
#
# - Con sudo: una unidad systemd `minikube-ingesta.service` (despues de docker.service).
# - Sin sudo: una linea `@reboot` en el crontab del usuario (cron arranca con la VM).
#
# Al arrancar espera a docker y hace `minikube start -p <perfil>`. Los datos sobreviven:
# minikube guarda en su volumen los PV (BD de PostgreSQL, stream de NATS, volcados) y las
# imagenes cargadas. Los CronJobs tienen startingDeadlineSeconds de 6 h, asi que si la VM
# vuelve antes de las 08:00 la pasada de las 02:00 se lanza igualmente.
#
# Log: ~/.minikube-ingesta-autostart.log
set -euo pipefail

PROFILE="${MINIKUBE_PROFILE:-ingesta}"
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
LOG="$HOME/.minikube-ingesta-autostart.log"
UNIT="minikube-$PROFILE.service"
TAG="# autostart minikube $PROFILE (flujo-entrada/infra/autostart.sh)"

run() {
  export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
  echo "== $(date -Is) arranque de minikube -p $PROFILE"
  for _ in $(seq 60); do docker info >/dev/null 2>&1 && break; sleep 5; done
  docker info >/dev/null 2>&1 || { echo "docker no responde tras 5 min"; exit 1; }
  minikube -p "$PROFILE" status >/dev/null 2>&1 && { echo "ya estaba en marcha"; exit 0; }
  minikube start -p "$PROFILE"
  echo "== $(date -Is) listo"
}

install_systemd() {
  sudo tee "/etc/systemd/system/$UNIT" >/dev/null <<EOF
[Unit]
Description=minikube perfil $PROFILE (ingesta + API/BD)
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=$USER
Environment=HOME=$HOME
ExecStart=/usr/bin/env bash $SELF --run
StandardOutput=append:$LOG
StandardError=append:$LOG
TimeoutStartSec=900

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable "$UNIT"
  echo "instalado: systemd $UNIT (systemctl status $UNIT)"
}

install_cron() {
  local line="@reboot HOME=$HOME /usr/bin/env bash $SELF --run >> $LOG 2>&1 $TAG"
  { crontab -l 2>/dev/null | grep -vF "$TAG" || true; echo "$line"; } | crontab -
  echo "instalado: crontab @reboot (crontab -l)"
}

remove() {
  { crontab -l 2>/dev/null | grep -vF "$TAG" || true; } | crontab -
  if [ -f "/etc/systemd/system/$UNIT" ] && sudo -n true 2>/dev/null; then
    sudo systemctl disable "$UNIT" && sudo rm -f "/etc/systemd/system/$UNIT" && sudo systemctl daemon-reload
  fi
  echo "quitado"
}

case "${1:-}" in
  --run)    run ;;
  --remove) remove ;;
  "")
    if sudo -n true 2>/dev/null; then install_systemd; else install_cron; fi ;;
  *) echo "uso: $0 [--run|--remove]" >&2; exit 2 ;;
esac
