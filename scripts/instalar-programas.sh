#!/usr/bin/env bash
# Creator's programs that run inside Ubuntu (WSL) and show up in Sergio's web:
#   opendesign  OpenDesign (clawnify/OpenDesign, MIT): the Canva-like editor
#   vscodium    VSCodium for the browser (VSCodium/vscodium "reh-web", MIT)
#   kronos      Kronos (shiyu-coder/Kronos, MIT): stock forecasts, with torch
# Usage: bash scripts/instalar-programas.sh [opendesign|vscodium|kronos ...]
# With no names it installs or updates all three. Each one is independent:
# a failure is reported and the others go on.
set -uo pipefail
for d in "$HOME"/.local/share/sergio-toolchain/node-*/bin; do
  if [[ -d "$d" ]]; then PATH="$d:$PATH"; fi
done
export PATH="$PATH:$HOME/.local/bin:$HOME/.cargo/bin"
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
apps="${OPENJARVIS_HOME:-$HOME/.openjarvis}/apps"
mkdir -p "$apps"

opendesign() {
  local dir="$apps/opendesign"
  if [[ -d "$dir/.git" ]]; then
    # The Spanish texts (and the lock pnpm refreshes) change tracked files on
    # each build: undo them so the update is a clean fast-forward.
    git -C "$dir" checkout --quiet -- . || return 1
    git -C "$dir" pull --ff-only --quiet || return 1
  else
    git clone --depth 1 --quiet https://github.com/clawnify/OpenDesign "$dir" || return 1
  fi
  python3 "$root/scripts/opendesign_es.py" "$dir" || return 1
  (
    cd "$dir" || exit 1
    npx --yes pnpm@10.28.0 install --no-frozen-lockfile --silent || exit 1
    npx --yes pnpm@10.28.0 run build || exit 1
    WRANGLER_SEND_METRICS=false npx wrangler d1 execute open-design-db --local --file=schema.sql >/dev/null || exit 1
  )
}

# The editor shows Sergio's name for it («Código»), not its own.
codigo_name() {
  local product="$1/product.json"
  [[ -f "$product" ]] || return 0
  python3 - "$product" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
if data.get("nameShort") != "Código":
    data.update(nameShort="Código", nameLong="Código")
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY
}

vscodium() {
  local dir="$apps/vscodium-web" arch url tmp
  case "$(uname -m)" in
    x86_64) arch=x64 ;;
    aarch64) arch=arm64 ;;
    *) echo "VSCodium web: arquitectura no soportada" >&2; return 1 ;;
  esac
  url="$(curl -fsSL -H 'Accept: application/vnd.github+json' \
    https://api.github.com/repos/VSCodium/vscodium/releases/latest |
    grep -o "https://[^\"]*vscodium-reh-web-linux-${arch}-[^\"]*\.tar\.gz" | head -n1)"
  [[ -n "$url" ]] || { echo "VSCodium web: no encontré la descarga" >&2; return 1; }
  if [[ -f "$dir/.version" && "$(cat "$dir/.version")" == "$url" ]]; then
    codigo_name "$dir"
    return 0  # already the latest
  fi
  tmp="$(mktemp -d)"
  curl -fsSL "$url" -o "$tmp/reh.tar.gz" || { rm -rf "$tmp"; return 1; }
  rm -rf "$dir.new" && mkdir -p "$dir.new"
  tar -xzf "$tmp/reh.tar.gz" -C "$dir.new" || { rm -rf "$tmp" "$dir.new"; return 1; }
  rm -rf "$tmp" "$dir" && mv "$dir.new" "$dir"
  echo "$url" > "$dir/.version"
  codigo_name "$dir"
  [[ -x "$dir/bin/codium-server" ]]
}

kronos() {
  (cd "$root" && uv run --no-sync python -c 'from openjarvis.creator import kronos; kronos.install()')
}

names=("$@")
if [[ ${#names[@]} -eq 0 ]]; then names=(opendesign vscodium kronos); fi
status=0
for name in "${names[@]}"; do
  case "$name" in
    opendesign|vscodium|kronos)
      echo "Programas de Creator: $name…"
      if "$name"; then echo "  $name: listo."; else echo "  $name: no se pudo (se reintenta en la próxima actualización)." >&2; status=1; fi
      ;;
    *) echo "Programa desconocido: $name" >&2; status=2 ;;
  esac
done
exit "$status"
