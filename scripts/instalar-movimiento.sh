#!/usr/bin/env bash
# Kimodo, MotionBricks and Audio2Face-3D for the game characters (owner,
# 2 Nov 2026). Only on request («instala los movimientos») and only with an
# NVIDIA GPU: several GB. Each one in its own folder under $1
# (~/.openjarvis/movimiento). Never the research-only Kimodo SMPL-X model.
set -uo pipefail
DEST="${1:-$HOME/.openjarvis/movimiento}"
mkdir -p "$DEST"
cd "$DEST"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "Sin tarjeta NVIDIA (nvidia-smi): no instalo nada."
  exit 2
fi
need() { command -v "$1" >/dev/null 2>&1 || { echo "Falta $1"; return 1; }; }
need git || exit 3
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v git-lfs >/dev/null 2>&1 || sudo -n apt-get install -y git-lfs || echo "Instale git-lfs (sudo apt install git-lfs)."
git lfs install --skip-repo >/dev/null 2>&1 || true

fetch() { # repo folder
  if [ -d "$2/.git" ]; then git -C "$2" pull --ff-only; else git clone --depth 1 "$1" "$2"; fi
}

ok=0
echo "== Kimodo (texto a movimiento)"
if fetch https://github.com/nv-tlabs/kimodo kimodo && (cd kimodo && uv sync); then ok=$((ok+1)); else echo "Kimodo no quedó."; fi

echo "== MotionBricks (locomoción en tiempo real)"
if fetch https://github.com/NVlabs/motionbricks motionbricks && (cd motionbricks && git lfs pull && uv sync); then
  (cd motionbricks && uv run hf download nvidia/MotionBricks --local-dir checkpoints/MotionBricks) || echo "Faltan los checkpoints de MotionBricks."
  ok=$((ok+1))
else
  echo "MotionBricks no quedó."
fi

echo "== Audio2Face-3D (la cara desde la voz)"
mkdir -p audio2face
if fetch https://github.com/NVIDIA/Audio2Face-3D-SDK audio2face/sdk && fetch https://github.com/NVIDIA/Audio2Face-3D-Samples audio2face/samples; then
  ok=$((ok+1))
else
  echo "Audio2Face no quedó."
fi
echo "Listo: $ok de 3 motores."
[ "$ok" -gt 0 ]
