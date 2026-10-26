#!/usr/bin/env bash
# Instala Sergio (núcleo OpenJarvis) con sus extensiones integradas (OpenClacky + globo 3D)
# en Linux (Ubuntu/Debian) o dentro de WSL2 en Windows 11.
#
#   ./scripts/install-todo-en-uno.sh               # todo
#   ./scripts/install-todo-en-uno.sh --sin-globo   # sin el globo 3D
#   ./scripts/install-todo-en-uno.sh --modelo qwen3:4b
#   ./scripts/install-todo-en-uno.sh --ahorro-tokens  # + LLMLingua (descarga ~2 GB)
#   ./scripts/install-todo-en-uno.sh --permanente     # dejarlo siempre encendido
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_GLOBE=false  # God's Eye View is hidden: only its data is used
TOKEN_SAVER=false
PERMANENT=false
MODEL="qwen3:8b"
while [[ $# -gt 0 ]]; do
  case $1 in
    --sin-globo) WITH_GLOBE=false ;;
    --con-globo) WITH_GLOBE=true ;;  # the visible 3D globe server, as before
    --ahorro-tokens) TOKEN_SAVER=true ;;
    --permanente) PERMANENT=true ;;
    --modelo) MODEL=$2; shift ;;
    *) echo "Opción desconocida: $1" >&2; exit 2 ;;
  esac
  shift
done
say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

say "1/6 Paquetes del sistema"
if command -v apt-get >/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y git curl build-essential libssl-dev libyaml-dev \
    zlib1g-dev libffi-dev pkg-config unzip ca-certificates
else
  echo "Distribución no Debian: instala git, curl y herramientas de compilación a mano."
fi

# En WSL, systemd hace falta para el modo permanente (`sergio servicio`).
NEEDS_WSL_RESTART=false
if grep -qi microsoft /proc/version 2>/dev/null \
   && ! grep -qs '^systemd=true' /etc/wsl.conf; then
  if grep -qs '^\[boot\]' /etc/wsl.conf; then
    sudo sed -i '/^\[boot\]/a systemd=true' /etc/wsl.conf
  else
    printf '\n[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf >/dev/null
  fi
  NEEDS_WSL_RESTART=true
fi

say "2/6 Ruby 3.3 y Node 24 (con mise)"
if ! command -v mise >/dev/null; then
  curl -fsSL https://mise.run | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
grep -q 'mise activate' ~/.bashrc 2>/dev/null \
  || echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
eval "$(mise activate bash)"
mise use -g ruby@3.3 node@24
eval "$(mise activate bash)"

say "3/6 uv y Ollama"
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
if grep -qi microsoft /proc/version 2>/dev/null \
   && curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama de Windows detectado desde WSL (usa tu GPU)."
else
  command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh \
    || echo "⚠ No se pudo instalar Ollama (solo hace falta para el modelo local; Gemini funciona sin él)."
  # Encenderlo y esperar a que conteste (hasta 60 s) para que la descarga
  # del modelo no falle por llegar antes que Ollama.
  if command -v ollama >/dev/null && ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    systemctl --user start ollama 2>/dev/null || sudo systemctl start ollama 2>/dev/null \
      || (nohup ollama serve >/tmp/ollama.log 2>&1 &)
    for _ in $(seq 60); do
      curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
      sleep 1
    done
  fi
fi

# ngrok: dirección pública fija para llamadas y WhatsApp (cuenta gratuita).
if ! command -v ngrok >/dev/null && command -v apt-get >/dev/null; then
  curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
    | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
    && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
    | sudo tee /etc/apt/sources.list.d/ngrok.list >/dev/null \
    && sudo apt-get update -y && sudo apt-get install -y ngrok \
    || echo "⚠ No se pudo instalar ngrok (solo hace falta para llamadas/WhatsApp)."
fi

say "4/6 OpenJarvis"
cd "$ROOT"
EXTRAS=(--extra server --extra desktop --extra tools-search --extra inference-cloud
        --extra phone --extra faces)
if $TOKEN_SAVER; then EXTRAS+=(--extra token-saver); fi
uv sync "${EXTRAS[@]}"
# Motor nativo en Rust: lo necesitan la memoria de documentos y la búsqueda.
# Primero la versión ya compilada (sin Rust); si no hay, se compila aquí.
# Si falla, Sergio funciona igual pero sin esas funciones.
bash scripts/install/install-native.sh "$ROOT/.venv/bin/python" || true

say "5/6 Extensiones"
( cd extensions/clacky && bundle install )
if $WITH_GLOBE; then
  ( cd extensions/globe && npm ci )
fi
( cd frontend && npx -y npm@11 ci )

say "6/6 Configuración y modelo"
CONFIG_DIR="${OPENJARVIS_HOME:-$HOME/.openjarvis}"
mkdir -p "$CONFIG_DIR"
CONFIG="$CONFIG_DIR/config.toml"
touch "$CONFIG"
add_section() { grep -q "^\[$1\]" "$CONFIG" || printf '\n[%s]\n%s\n' "$1" "$2" >> "$CONFIG"; }
add_section analytics "enabled = false"
add_section intelligence "default_model = \"$MODEL\""
# Evolución: Sergio aprende de cada conversación y consolida tu perfil.
add_section memory "enabled = true"
# Herramientas que Sergio puede usar en el chat (Clacky y los datos del planeta:
# lugares y clima, vuelos, sismos y lanzamientos; el globo no se muestra).
add_section tools 'enabled = ["calculator", "web_search", "file_read", "user_profile_manage", "clacky_task", "globe_view", "live_flights", "flights_overhead", "live_earthquakes", "upcoming_launches", "phone_call", "phone_call_status", "whatsapp_send", "face_identify", "face_list", "skill_guide"]'
if $TOKEN_SAVER; then add_section compression "tool_output = true"; fi
if $WITH_GLOBE; then add_section extensions.globe "enabled = true"; fi
# Voz en español, local: escucha con Whisper y habla con Kokoro.
add_section speech 'language = "es"
compute_type = "int8"
tts_backend = "kokoro_onnx"
voice_id = "em_alex"'
if command -v ollama >/dev/null; then
  curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || (ollama serve >/dev/null 2>&1 &)
  sleep 2
fi
# Descarga el modelo por la API: funciona también con el Ollama de Windows,
# cuyo comando `ollama` no existe dentro de WSL.
if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Descargando el modelo $MODEL (unos 5 GB, solo la primera vez)…"
  curl -fsS http://127.0.0.1:11434/api/pull -d "{\"model\": \"$MODEL\", \"stream\": false}" >/dev/null \
    && echo "Modelo listo." || echo "⚠ No pude descargar $MODEL: en PowerShell ejecuta 'ollama pull $MODEL'."
else
  echo "⚠ Ollama no responde: ábrelo en Windows y ejecuta en PowerShell 'ollama pull $MODEL'."
fi

# ECC: ~350 guías expertas que Sergio consulta solo cuando le sirven.
uv run sergio ecc actualizar || echo "⚠ ECC no se pudo descargar; luego: sergio ecc actualizar"

# Comando `sergio` disponible en cualquier carpeta.
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/sergio" <<EOS
#!/bin/sh
exec uv run --project "$ROOT" sergio "\$@"
EOS
chmod +x "$HOME/.local/bin/sergio"

if $PERMANENT; then
  if systemctl --user show-environment >/dev/null 2>&1; then
    uv run sergio servicio instalar
  else
    echo "⚠ systemd aún no está activo: reinicia WSL (en PowerShell: wsl --shutdown)"
    echo "  y luego ejecuta: cd $ROOT && uv run sergio servicio instalar"
  fi
fi
if $NEEDS_WSL_RESTART; then
  echo "ℹ Activé systemd en WSL: ejecuta 'wsl --shutdown' en PowerShell una vez."
fi

cat <<EOF

✅ Listo. Abre una terminal nueva y ejecuta:

   sergio gui                 # abrir la app ahora
   sergio servicio instalar   # dejarla siempre encendida (http://localhost:8000)

Se abre una sola app con Chat, Globe y Clacky en la barra lateral.
Configuración: $CONFIG
EOF
