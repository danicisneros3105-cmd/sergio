# Run from an existing Sergio checkout in Windows; the app itself runs via WSL.
param(
    [string]$Distribucion = "Ubuntu",
    [string]$Repositorio = "~/sergio",
    [string]$Rama = "codex/professional-reliability-audit",
    [string]$Commit = ""
)
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$bootstrap = @'
set -euo pipefail
repo="$1"
branch="$2"
requested="${3:-}"
case "$repo" in '~/'*) repo="$HOME/${repo:2}" ;; esac
cd -- "$repo"
git check-ref-format --branch "$branch" >/dev/null
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "Guarda o confirma tus cambios locales antes de actualizar." >&2; exit 1
fi
origin="$(git remote get-url origin)"
case "$origin" in
  https://github.com/danicisneros3105-cmd/sergio|https://github.com/danicisneros3105-cmd/sergio.git|git@github.com:danicisneros3105-cmd/sergio.git) ;;
  *) echo "Origen inesperado; actualización cancelada." >&2; exit 1 ;;
esac
previous="$(git rev-parse HEAD)"
git fetch --no-tags origin "$branch"
target="$(git rev-parse FETCH_HEAD)"
if [[ -n "$requested" ]]; then
  [[ "$requested" =~ ^[0-9a-f]{40}$ ]]
  git cat-file -e "$requested^{commit}"
  git merge-base --is-ancestor "$requested" "$target"
  target="$requested"
fi
git merge-base --is-ancestor "$previous" "$target"
git update-ref "refs/sergio/updates/bootstrap-$(date +%s)-$$" "$previous"
git merge --ff-only "$target"
bash scripts/actualizar-sergio.sh "$branch" "$requested"
'@
$temporary = Join-Path ([IO.Path]::GetTempPath()) ("sergio-update-" + [guid]::NewGuid().ToString("N") + ".sh")
try {
    [IO.File]::WriteAllText($temporary, $bootstrap.Replace("`r", "") + "`n", [Text.UTF8Encoding]::new($false))
    $linuxPath = (& wsl.exe -d $Distribucion --exec wslpath -u $temporary).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $linuxPath) { throw "No pude convertir la ruta temporal para WSL." }
    & wsl.exe -d $Distribucion --exec bash $linuxPath $Repositorio $Rama $Commit
    $updateExit = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue
}
if ($updateExit -ne 0) {
    throw "Actualización detenida. Revisa el error anterior; no se borraron tus cambios ni tu perfil."
}
