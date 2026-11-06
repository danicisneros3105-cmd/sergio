#!/usr/bin/env bash
# Builds a Windows release candidate with NSIS (apt install nsis).
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
command -v makensis >/dev/null || { echo "Instale NSIS: sudo apt-get install -y nsis" >&2; exit 1; }

version="${1:-$(date +%Y.%m.%d)}"
if [[ ! "$version" =~ ^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$ ]]; then
  echo "Versión inválida. Usa tres números, por ejemplo 1.0.2." >&2
  exit 2
fi
output="$root/dist/sergio-windows"
mkdir -p -- "$output"
cd "$root/installer"
makensis -V2 "-DVERSION=$version" "-DOUTFILE=$output/Sergio-Instalador.exe" sergio.nsi
cd "$output"
test -s Sergio-Instalador.exe
sha256sum Sergio-Instalador.exe > SHA256SUMS.txt
echo "Candidato sin firmar: $output/Sergio-Instalador.exe"
