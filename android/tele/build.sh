#!/usr/bin/env bash
# Compila la app de la tele en docker: el APK firmado de release, o los tests de :core.
# Uso: android/tele/build.sh [destino.apk]   ·   android/tele/build.sh test
# Entorno: TELE_KEYS_DIR, carpeta de la clave (default ~/.config/domotica/android);
#          TELE_HOUSE, URL base de la casa (default la de app/build.gradle.kts).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
image="domotica-tele-build"
volume="domotica-tele-gradle-cache"
keys="${TELE_KEYS_DIR:-$HOME/.config/domotica/android}"

# Genera el wrapper si falta; versión y hash salen de la tarea `wrapper` de build.gradle.kts.
wrapper='[ -x ./gradlew ] && [ -f gradle/wrapper/gradle-wrapper.jar ] || gradle wrapper --no-daemon -q'

run() {
    docker build -q -t "$image" "$here" > /dev/null
    docker volume create "$volume" > /dev/null
    docker run --rm \
        -u "$(id -u):$(id -g)" \
        -e HOME=/tmp \
        -v "$volume:/gradle-cache" \
        -v "$here:/src" \
        "$@"
}

if [ "${1:-}" = "test" ]; then
    run "$image" bash -c "$wrapper && ./gradlew --no-daemon :core:test"
    exit 0
fi

if [ ! -f "$keys/tele-release.jks" ] || [ ! -f "$keys/keystore.properties" ]; then
    cat >&2 <<EOF
Falta la clave de firma en $keys (tele-release.jks y keystore.properties).
Vive fuera del repo y se crea una sola vez: perderla obliga a desinstalar la app de cada tele.

    mkdir -p "$keys" && chmod 700 "$keys"
    keytool -genkeypair -v -storetype PKCS12 -keystore "$keys/tele-release.jks" \\
        -alias tele -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=Domotica tele"
    cat > "$keys/keystore.properties" <<'PROPS'
storePassword=<la contraseña que elegiste>
keyAlias=tele
keyPassword=<la misma contraseña: PKCS12 usa una sola>
PROPS
    chmod 600 "$keys/tele-release.jks" "$keys/keystore.properties"

O apuntá TELE_KEYS_DIR a otra carpeta que tenga los dos archivos.
EOF
    exit 1
fi

dest="${1:-}"
house=()
if [ -n "${TELE_HOUSE:-}" ]; then
    house=("-Phouse=$TELE_HOUSE")
fi
apk="app/build/outputs/apk/release/app-release.apk"

run -v "$keys:/keys:ro" "$image" bash -c \
    "$wrapper && ./gradlew --no-daemon -PkeysDir=/keys ${house[*]} :app:assembleRelease && apksigner verify --print-certs $apk"

ls -l "$here/$apk"
if [ -n "$dest" ]; then
    cp "$here/$apk" "$dest"
    echo "APK copiado a $dest"
fi
