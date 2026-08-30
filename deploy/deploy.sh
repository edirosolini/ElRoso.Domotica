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
  rm -rf /opt/domotica/src
  tar -xzf /tmp/domotica.tar.gz -C /opt/domotica
  install -m 644 /opt/domotica/deploy/domotica.service /etc/systemd/system/domotica.service
  install -m 755 /opt/domotica/deploy/domotica-say /usr/local/bin/domotica-say
  systemctl daemon-reload
  systemctl enable domotica.service
  # restart, not "enable --now": --now does nothing if it is already running,
  # so the old process keeps serving the previous code.
  systemctl restart domotica.service
  rm -f /tmp/domotica.tar.gz
'
rm -f /tmp/domotica.tar.gz
REMOTE

echo "==> estado"
ssh "root@${PVE}" "pct exec ${CTID} -- systemctl is-active domotica.service"
