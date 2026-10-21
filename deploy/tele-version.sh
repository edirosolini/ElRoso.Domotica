#!/usr/bin/env bash
# Imprime el tele.json de un APK: versión, sha256 y tamaño. No sube nada.
# Uso: deploy/tele-version.sh <apk>
set -euo pipefail

APK="${1:?uso: deploy/tele-version.sh <apk>}"
IMAGE="domotica-tele-build"

if [[ ! -s "$APK" ]]; then
  echo "no existe o está vacío: $APK" >&2
  exit 1
fi
if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  echo "falta la imagen $IMAGE: corré antes android/tele/build.sh" >&2
  exit 1
fi

apk_path="$(cd "$(dirname "$APK")" && pwd)/$(basename "$APK")"
badging="$(docker run --rm --network none -u "$(id -u):$(id -g)" \
  -v "$apk_path:/in/tele.apk:ro" "$IMAGE" aapt2 dump badging /in/tele.apk)" || {
  echo "aapt2 no pudo leer el APK: $APK" >&2
  exit 1
}
badging="${badging%%$'\n'*}"

code="$(sed -n "s/.* versionCode='\([^']*\)'.*/\1/p" <<< "$badging")"
name="$(sed -n "s/.* versionName='\([^']*\)'.*/\1/p" <<< "$badging")"

# Solo lo que entra en el JSON sin escapar y en el tope de `hello`.
if [[ ! "$code" =~ ^(0|[1-9][0-9]{0,9})$ ]]; then
  echo "no pude leer el versionCode del APK" >&2
  exit 1
fi
if [[ ! "$name" =~ ^[A-Za-z0-9._+-]{1,40}$ ]]; then
  echo "versionName inválido en el APK: '$name'" >&2
  exit 1
fi

sha="$(sha256sum "$APK" | cut -d' ' -f1)"
size="$(stat -c %s "$APK")"

printf '{"version_code": %s, "version_name": "%s", "sha256": "%s", "size": %s}\n' \
  "$code" "$name" "$sha" "$size"
