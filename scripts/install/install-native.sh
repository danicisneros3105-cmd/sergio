#!/usr/bin/env bash
# install-native.sh — put the native engine (openjarvis_rust) in the venv.
#
# 1. A pre-built wheel from the `rust-wheels` GitHub release (seconds, no Rust).
# 2. Otherwise compile it locally with maturin (minutes, needs Rust).
#
# Usage: scripts/install/install-native.sh [path/to/venv/python]
# Exit 0 when `import openjarvis_rust` works afterwards.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${1:-$ROOT/.venv/bin/python}"
REPO="${OPENJARVIS_WHEELS_REPO:-}"
if [[ -z "$REPO" ]]; then
    url="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
    REPO="$(printf '%s' "$url" | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"
fi
[[ "$REPO" == */* ]] || REPO="danicisneros3105-cmd/sergio"
WHEELS="https://github.com/$REPO/releases/expanded_assets/rust-wheels"

imports() { "$PY" -c "import openjarvis_rust" >/dev/null 2>&1; }

if imports; then
    echo "Motor nativo ya instalado."
    exit 0
fi

echo "Motor nativo: buscando una versión ya compilada…"
if uv pip install --python "$PY" --no-index --find-links "$WHEELS" openjarvis-rust >/dev/null 2>&1 && imports; then
    echo "Motor nativo instalado (ya compilado, sin Rust)."
    exit 0
fi

echo "No hay versión compilada para este equipo; compilándolo (tarda unos minutos)…"
if bash "$ROOT/scripts/install/install-rust.sh" \
   && PATH="$HOME/.cargo/bin:$PATH" uv run --python "$PY" --with "maturin>=1.12.6" \
        maturin develop --release -m "$ROOT/rust/crates/openjarvis-python/Cargo.toml" \
   && imports; then
    echo "Motor nativo instalado (compilado aquí)."
    exit 0
fi
echo "⚠ No se pudo instalar el motor nativo (memoria de documentos desactivada)." >&2
exit 1
