#!/usr/bin/env bash
# Sube el APK de la tele y su tele.json al CT, donde los sirve /app/. No compila ni reinicia.
# Uso: deploy/push-apk.sh <apk> [host-proxmox] [ctid]
set -euo pipefail

APK="${1:?uso: deploy/push-apk.sh <apk> [host-proxmox] [ctid]}"
PVE="${2:-192.168.68.60}"
CTID="${3:-300}"
REMOTE_TMP="/tmp/domotica-tele.apk"
REMOTE_JSON="/tmp/domotica-tele.json"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ ! -f "$APK" ]]; then
  echo "no existe el archivo: $APK" >&2
  exit 1
fi
if [[ ! -s "$APK" ]]; then
  echo "el archivo está vacío: $APK" >&2
  exit 1
fi

echo "==> versión del APK"
local_json="$(mktemp)"
trap 'rm -f "$local_json"' EXIT
"$HERE/tele-version.sh" "$APK" > "$local_json"
cat "$local_json"

echo "==> copiando al proxmox"
scp -q "$APK" "root@${PVE}:${REMOTE_TMP}"
scp -q "$local_json" "root@${PVE}:${REMOTE_JSON}"

echo "==> instalando en el CT ${CTID}"
ssh "root@${PVE}" bash -s <<REMOTE
set -euo pipefail
trap 'rm -f ${REMOTE_TMP} ${REMOTE_JSON}' EXIT
pct push ${CTID} ${REMOTE_TMP} ${REMOTE_TMP}
pct push ${CTID} ${REMOTE_JSON} ${REMOTE_JSON}
pct exec ${CTID} -- bash -c '
  set -euo pipefail
  trap "rm -f ${REMOTE_TMP} ${REMOTE_JSON}" EXIT
  install -d -m 755 -o root -g root /var/lib/domotica/app
  install -m 644 -o root -g root ${REMOTE_TMP} /var/lib/domotica/app/tele.apk.tmp
  install -m 644 -o root -g root ${REMOTE_JSON} /var/lib/domotica/app/tele.json.tmp
  # Primero el APK y después la versión: tele.json nunca apunta a un APK viejo.
  mv -f /var/lib/domotica/app/tele.apk.tmp /var/lib/domotica/app/tele.apk
  mv -f /var/lib/domotica/app/tele.json.tmp /var/lib/domotica/app/tele.json
  echo "==> sha256 en el CT"
  sha256sum /var/lib/domotica/app/tele.apk | cut -d" " -f1
  echo "==> versión publicada"
  cat /var/lib/domotica/app/tele.json
'
REMOTE
