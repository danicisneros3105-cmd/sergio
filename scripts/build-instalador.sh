#!/usr/bin/env bash
# Builds installer/Sergio-Instalador.exe with NSIS (apt install nsis).
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
command -v makensis >/dev/null || { echo "Instale NSIS: sudo apt-get install -y nsis" >&2; exit 1; }

version="$(date +%Y.%m.%d)"
cd "$root/installer"
makensis -V2 -DVERSION="${version//./.}" sergio.nsi
echo "Listo: installer/Sergio-Instalador.exe"
