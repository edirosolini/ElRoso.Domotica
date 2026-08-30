#!/usr/bin/env bash
# Copia el código al contenedor y reinicia el servicio.
# Uso: deploy/deploy.sh [host-proxmox] [ctid]
set -euo pipefail

PVE="${1:-192.168.68.60}"
CTID="${2:-300}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> empaquetando"
TAR=$(mktemp /tmp/domotica-XXXX.tar.gz)
tar -czf "$TAR" -C "$ROOT" src deploy

echo "==> copiando al proxmox"
scp -q "$TAR" "root@${PVE}:/tmp/domotica.tar.gz"
rm -f "$TAR"

echo "==> instalando en el CT ${CTID}"
ssh "root@${PVE}" bash -s <<REMOTE
set -euo pipefail
pct push ${CTID} /tmp/domotica.tar.gz /tmp/domotica.tar.gz
pct exec ${CTID} -- bash -lc '
  rm -rf /opt/nestbot/src
  tar -xzf /tmp/domotica.tar.gz -C /opt/nestbot
  install -m 644 /opt/nestbot/deploy/nestbot.service /etc/systemd/system/nestbot.service
  systemctl daemon-reload
  systemctl enable nestbot.service
  # restart, not "enable --now": --now does nothing if it is already running,
  # so the old process keeps serving the previous code.
  systemctl restart nestbot.service
  rm -f /tmp/domotica.tar.gz
'
rm -f /tmp/domotica.tar.gz
REMOTE

echo "==> estado"
ssh "root@${PVE}" "pct exec ${CTID} -- systemctl is-active nestbot.service"
