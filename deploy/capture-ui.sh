#!/usr/bin/env bash
# Captura las páginas de la casa en celular, tablet, PC y tele, en tema claro y oscuro. Solo hace GET.
# Uso: CAPTURE_BROWSER=<chrome o chromium> [CAPTURE_FLAGS=--no-sandbox] deploy/capture-ui.sh <url-base> [carpeta] [job-de-alarma]
set -euo pipefail

BASE="${1:?uso: deploy/capture-ui.sh <url-base> [carpeta] [job-de-alarma]}"
OUT="${2:-capturas}"
JOB="${3:-}"
BROWSER="${CAPTURE_BROWSER:-chromium}"
WAIT_MS="${CAPTURE_WAIT_MS:-6000}"
LIMIT_S="${CAPTURE_TIMEOUT_S:-60}"
# Banderas de más para el navegador, por ejemplo --no-sandbox donde no hay sandbox de usuario.
read -r -a EXTRA <<< "${CAPTURE_FLAGS:-}"
BASE="${BASE%/}"

if ! command -v "$BROWSER" >/dev/null 2>&1; then
  echo "no encuentro el navegador: $BROWSER (CAPTURE_BROWSER)" >&2
  exit 1
fi
mkdir -p "$OUT"

# Nombre del tamaño y ventana: celular, tablet apaisada, PC, tele 1080p y tele 720p.
SIZES=("cel 412,915" "tab 1024,768" "pc 1440,900" "tele 1920,1080" "tele720 1280,720")
# Las páginas largas también se sacan enteras, con una ventana alta.
LONG=("cel 412,2600" "pc 1440,1800")

PAGES=("control /control" "agenda /agenda" "pantalla /pantalla" "pantalla-tele /pantalla?ver=1")
if [[ -n "$JOB" ]]; then
  PAGES+=("alarma /alarma?job=$JOB")
fi

# Saca una captura con un perfil vacío, así no arrastra lo guardado en localStorage.
shoot() {
  local file="$1" size="$2" url="$3"
  shift 3
  local profile
  profile="$(mktemp -d)"
  timeout "$LIMIT_S" "$BROWSER" --headless --disable-gpu --hide-scrollbars --no-first-run \
    --force-device-scale-factor=1 --user-data-dir="$profile" \
    --virtual-time-budget="$WAIT_MS" --window-size="$size" \
    --screenshot="$file" ${EXTRA[@]+"${EXTRA[@]}"} "$@" "$url" >/dev/null 2>&1 || echo "falló: $file" >&2
  rm -rf "$profile"
  echo "$file"
}

for page in "${PAGES[@]}"; do
  name="${page%% *}"
  path="${page#* }"
  for entry in "${SIZES[@]}"; do
    shoot "$OUT/$name-${entry%% *}.png" "${entry#* }" "$BASE$path"
  done
  case "$name" in
    control|agenda)
      for entry in "${LONG[@]}"; do
        shoot "$OUT/$name-${entry%% *}-largo.png" "${entry#* }" "$BASE$path"
        shoot "$OUT/$name-${entry%% *}-largo-oscuro.png" "${entry#* }" "$BASE$path" \
          --blink-settings=preferredColorScheme=0
      done
      ;;
  esac
  shoot "$OUT/$name-cel-oscuro.png" "412,915" "$BASE$path" --blink-settings=preferredColorScheme=0
  shoot "$OUT/$name-pc-oscuro.png" "1440,900" "$BASE$path" --blink-settings=preferredColorScheme=0
done
