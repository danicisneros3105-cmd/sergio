#!/usr/bin/env bash
# Update an existing private checkout in WSL, preserving user data and extras.
set -euo pipefail
# Desde PowerShell (bash -lc) el Node del instalador no está en PATH: añádalo.
for d in "$HOME"/.local/share/sergio-toolchain/node-*/bin; do
  if [[ -d "$d" ]]; then PATH="$d:$PATH"; fi
done
export PATH="$PATH:$HOME/.local/bin:$HOME/.cargo/bin"
branch="${1:-main}"
requested="${2:-}"
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$root"
git check-ref-format --branch "$branch" >/dev/null
origin="$(git remote get-url origin)"
case "$origin" in
  https://github.com/danicisneros3105-cmd/sergio|https://github.com/danicisneros3105-cmd/sergio.git|git@github.com:danicisneros3105-cmd/sergio.git) ;;
  *) echo "Origen inesperado. Comprueba el repositorio privado de Sergio." >&2; exit 1 ;;
esac
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "Guarda o confirma tus cambios locales antes de actualizar." >&2
  exit 1
fi
command -v uv >/dev/null || { echo "Instala uv antes de actualizar." >&2; exit 1; }
command -v node >/dev/null || { echo "Instala Node 22.22+ antes de actualizar." >&2; exit 1; }
command -v npm >/dev/null || { echo "Instala npm 11.19+ (menor que 12)." >&2; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22||(a===22&&b<22))process.exit(1)'
npm_version="$(npm --version)"
node -e 'const [a,b]=process.argv[1].split(".").map(Number); if(a!==11||b<19)process.exit(1)' "$npm_version"
previous="$(git rev-parse HEAD)"
git fetch --no-tags origin "$branch"
target="$(git rev-parse FETCH_HEAD)"
if [[ -n "$requested" ]]; then
  [[ "$requested" =~ ^[0-9a-f]{40}$ ]] || { echo "Commit inválido." >&2; exit 1; }
  git cat-file -e "$requested^{commit}"
  git merge-base --is-ancestor "$requested" "$target"
  target="$requested"
fi
git merge-base --is-ancestor "$previous" "$target" || {
  echo "La actualización no es fast-forward; conserva tus commits y resuelve la divergencia." >&2
  exit 1
}
rollback_ref="refs/sergio/updates/$(date +%s)-$$"
git update-ref "$rollback_ref" "$previous"
git merge --ff-only "$target"
echo "Respaldo del código: $rollback_ref ($previous)."
# Use exact locked versions, retaining manually installed optional dependencies.
uv sync --locked --inexact --extra server --extra desktop
uv run --no-sync python -c 'from google import genai; from google.genai import types; assert genai.Client and types.LiveConnectConfig; print("SDK Gemini Live: listo")'
(
  cd frontend
  npm ci --no-audit --no-fund
  npm run build
)
# Creator's programs inside Ubuntu (OpenDesign, VSCodium web, Kronos): never
# blocks the update; whatever fails is retried next time.
bash scripts/instalar-programas.sh || echo "Aviso: algún programa de Creator no se instaló; se reintenta en la próxima actualización." >&2
uv run --no-sync sergio escritorio instalar
# The background service must run this checkout (older updates used other folders).
uv run --no-sync sergio servicio instalar </dev/null || echo "Aviso: no pude reinstalar el servicio; ejecuta «sergio servicio instalar»." >&2
echo "Sergio actualizado a $(git rev-parse --short HEAD)."
echo "Si hubo un fallo, el respaldo conserva el código; revisa las dependencias antes de restaurarlo."
