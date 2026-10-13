#!/usr/bin/env bash
# Complete upstream applications in separate, pinned runtimes. Nothing is overwritten.
set -euo pipefail
for d in "$HOME"/.local/share/sergio-toolchain/node-*/bin; do
  [[ ! -d "$d" ]] || PATH="$d:$PATH"
done
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
mode="${1:-}"
install_root="$HOME/.local/share/sergio-integrations"

checkout() {
  local name="$1" origin="$2" revision="$3" folder="$install_root/$1"
  command -v git >/dev/null || { echo 'Falta Git.' >&2; exit 1; }
  mkdir -p "$install_root"
  if [[ -e "$folder" ]]; then
    [[ "$(git -C "$folder" remote get-url origin)" == "$origin" ]] || { echo 'Origen inesperado; no modifiqué la carpeta.' >&2; exit 1; }
    [[ -z "$(git -C "$folder" status --porcelain --untracked-files=no)" ]] || { echo 'Hay cambios en la integración. No los sobrescribí.' >&2; exit 1; }
  else
    git clone --filter=blob:none --no-checkout "$origin" "$folder"
  fi
  git -C "$folder" fetch --no-tags origin "$revision"
  git -C "$folder" checkout --detach "$revision"
  [[ "$(git -C "$folder" rev-parse HEAD)" == "$revision" ]]
}

case "$mode" in
  opendesign)
    command -v node >/dev/null && command -v npx >/dev/null || { echo 'Falta Node y npm.' >&2; exit 1; }
    checkout OpenDesign https://github.com/clawnify/OpenDesign.git a0ea785a3be38f61a944571c7a7f72c2ce7d2c2f
    npx --yes pnpm@10.18.3 --dir "$install_root/OpenDesign" install --frozen-lockfile
    npx --yes pnpm@10.18.3 --dir "$install_root/OpenDesign" test
    npx --yes pnpm@10.18.3 --dir "$install_root/OpenDesign" run build
    echo 'OpenDesign completo preparado. Inícielo con: bash scripts/preparar-integraciones.sh iniciar-opendesign'
    ;;
  iniciar-opendesign)
    cd -- "$install_root/OpenDesign"
    [[ "$(git rev-parse HEAD)" == a0ea785a3be38f61a944571c7a7f72c2ce7d2c2f ]] || { echo 'Prepare primero OpenDesign.' >&2; exit 1; }
    npx --yes pnpm@10.18.3 exec wrangler d1 execute open-design-db --local --file=schema.sql
    echo 'Editor: http://127.0.0.1:5178 · API: http://127.0.0.1:8787. Deje esta terminal abierta.'
    exec npx --yes pnpm@10.18.3 exec concurrently -n ui,api -c cyan,green \
      'vite --host 127.0.0.1 --port 5178 --strictPort' 'wrangler dev --ip 127.0.0.1 --port 8787'
    ;;
  kronos)
    command -v uv >/dev/null || { echo 'Falta uv.' >&2; exit 1; }
    checkout Kronos https://github.com/shiyu-coder/Kronos.git 67b630e67f6a18c9e9be918d9b4337c960db1e9a
    uv venv --allow-existing --python 3.12 "$install_root/Kronos/.venv"
    uv pip install --python "$install_root/Kronos/.venv/bin/python" -r "$install_root/Kronos/requirements.txt"
    mkdir -p "$install_root/Kronos/weights"
    echo 'Runtime Kronos preparado. Coloque Kronos-small en weights/model y Kronos-Tokenizer-base en weights/tokenizer.'
    echo 'No descargué los pesos. El cálculo de Sergio los carga solo desde el disco y nunca coloca órdenes.'
    ;;
  *) echo 'Uso: bash scripts/preparar-integraciones.sh opendesign|iniciar-opendesign|kronos' >&2; exit 2 ;;
esac
