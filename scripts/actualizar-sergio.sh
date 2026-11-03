#!/usr/bin/env bash
# Update an existing private checkout in WSL, preserving user data and extras.
set -euo pipefail
# Desde PowerShell (bash -lc) el Node del instalador no está en PATH: añádalo.
for d in "$HOME"/.local/share/sergio-toolchain/node-*/bin; do
  if [[ -d "$d" ]]; then PATH="$d:$PATH"; fi
done
# Tools installed for the user come after what is already on PATH (mise shims
# included), so the PATH the caller chose still wins.
export PATH="$PATH:$HOME/.local/share/mise/shims:$HOME/.local/bin:$HOME/.cargo/bin"
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
# Clean any generated/local build artifacts so the update never blocks.
static=src/openjarvis/server/static
if [[ -d "$static" ]]; then
  git checkout -- "$static" 2>/dev/null || true
  git clean -fdq -- "$static" 2>/dev/null || true
fi
# Only the generated web build is cleaned above. Anything else changed here is
# the owner's own work: never wipe it (no reset --hard, no clean), stop and say so.
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
uv sync --locked --inexact --extra server --extra desktop --extra browser
# Sergio's own browser (works in the background, without a window): Chromium
# for Playwright. A failed download only turns that one tool off.
uv run --no-sync playwright install chromium || echo "Aviso: no pude instalar el navegador de Sergio; «en segundo plano» queda apagado hasta la próxima actualización." >&2
uv run --no-sync python -c 'from google import genai; from google.genai import types; assert genai.Client and types.LiveConnectConfig; print("SDK Gemini Live: listo")'
# The prompt library (public system and persona prompts, downloaded whole to
# ~/.openjarvis/prompt_library); a failed download keeps the previous copy.
uv run --no-sync sergio prompts sincronizar || echo "Aviso: no pude actualizar la biblioteca de prompts; se reintenta en la próxima actualización." >&2
# The fly core: the measured connectome (FlyWire, SHA-256 checked) and the
# on-device meaning model; without them the stand-in and words keep working.
uv run --no-sync sergio cerebro descargar || echo "Aviso: no pude descargar el cerebro real; se reintenta en la próxima actualización." >&2
# Skills de guion y motion graphics de GitHub: se bajan aquí, nunca al repositorio.
uv run --no-sync python -c "from openjarvis.video_essay import skillbook as s; print(s.sync())" || echo "Aviso: no pude bajar las skills de video; se reintenta en la próxima actualización." >&2
# La voz propia de Sergio (transcripción y voz en este equipo): se bajan ahora
# para que la primera conversación no espere la descarga.
uv run --no-sync python -c "from openjarvis.speech import voz_propia as v; v.warm()" || echo "Aviso: no pude preparar la voz propia; se usará la voz de Gemini hasta la próxima actualización." >&2
# The full list of throwaway mail domains (CC0) for sign-up.
uv run --no-sync sergio cuentas listas || echo "Aviso: no pude actualizar la lista de correos temporales." >&2
(
  cd frontend
  npm ci --no-audit --no-fund
  # Into a folder git ignores: a build never leaves tracked files changed, so
  # the next update never stops on «local changes».
  SERGIO_WEB_OUT=../src/openjarvis/server/static_local npm run build
)
git checkout -- src/openjarvis/server/static 2>/dev/null || true
# Creator's programs inside Ubuntu (OpenDesign, VSCodium web, Kronos): never
# blocks the update; whatever fails is retried next time.
bash scripts/instalar-programas.sh || echo "Aviso: algún programa de Creator no se instaló; se reintenta en la próxima actualización." >&2
uv run --no-sync sergio escritorio instalar
# The background service must run this checkout (older updates used other folders).
uv run --no-sync sergio servicio instalar </dev/null || echo "Aviso: no pude reinstalar el servicio; ejecuta «sergio servicio instalar»." >&2
echo "Sergio actualizado a $(git rev-parse --short HEAD)."
echo "Si hubo un fallo, el respaldo conserva el código; revisa las dependencias antes de restaurarlo."
