#!/usr/bin/env bash
# Sube el APK de la tele al CT, donde lo sirve /app/tele.apk. No compila ni reinicia.
# Uso: deploy/push-apk.sh <apk> [host-proxmox] [ctid]
set -euo pipefail

APK="${1:?uso: deploy/push-apk.sh <apk> [host-proxmox] [ctid]}"
PVE="${2:-192.168.68.60}"
CTID="${3:-300}"
REMOTE_TMP="/tmp/domotica-tele.apk"

if [[ ! -f "$APK" ]]; then
  echo "no existe el archivo: $APK" >&2
  exit 1
fi
if [[ ! -s "$APK" ]]; then
  echo "el archivo está vacío: $APK" >&2
  exit 1
fi

echo "==> sha256 local"
sha256sum "$APK" | cut -d' ' -f1

echo "==> copiando al proxmox"
scp -q "$APK" "root@${PVE}:${REMOTE_TMP}"

echo "==> instalando en el CT ${CTID}"
ssh "root@${PVE}" bash -s <<REMOTE
set -euo pipefail
trap 'rm -f ${REMOTE_TMP}' EXIT
pct push ${CTID} ${REMOTE_TMP} ${REMOTE_TMP}
pct exec ${CTID} -- bash -c '
  set -euo pipefail
  trap "rm -f ${REMOTE_TMP}" EXIT
  install -d -m 755 -o root -g root /var/lib/domotica/app
  install -m 644 -o root -g root ${REMOTE_TMP} /var/lib/domotica/app/tele.apk.tmp
  # Reemplaza el APK de forma atómica.
  mv -f /var/lib/domotica/app/tele.apk.tmp /var/lib/domotica/app/tele.apk
  echo "==> sha256 en el CT"
  sha256sum /var/lib/domotica/app/tele.apk | cut -d" " -f1
'
REMOTE
