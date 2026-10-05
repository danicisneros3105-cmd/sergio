"""``sergio nube`` — use cloud models (Kimi, Gemini) instead of the local one.

Keys are stored only in ~/.openjarvis/sergio.env (readable by the user only),
never in config.toml or the repository. The local model stays as fallback.
"""

from __future__ import annotations

import subprocess

import click
import httpx
from rich.console import Console
from rich.markup import escape

console = Console()

KIMI_PREFERENCE = ("kimi-k2.6", "kimi-k2.5", "kimi-k2-turbo")
GEMINI_MODEL = "gemini-3.8-flash"  # fast, sees images, thinking levels
GEMINI_DEEP_MODEL = "gemini-3.1-pro-preview"  # for hard tasks (effort "profundo")
KIMI_URLS = ("https://api.moonshot.ai/v1", "https://api.moonshot.cn/v1")


def clean_key(raw: str) -> str:
    """Undo copy-paste damage: full-width letters, invisible chars, quotes."""
    import unicodedata

    key = unicodedata.normalize("NFKC", raw or "")
    key = "".join(c for c in key if c.isprintable() and not c.isspace())
    key = key.strip("'\"`")
    if not key.isascii():
        bad = "".join(sorted({c for c in key if not c.isascii()}))
        raise click.ClickException(
            f"La clave tiene caracteres extraños ({bad!r}). Cópiala de nuevo "
            "desde la página de Kimi/Google y pégala en el Bloc de notas primero."
        )
    return key


def kimi_models(key: str, base_url: str, http: httpx.Client | None = None) -> list[str]:
    """Model ids the key can use; raises httpx.HTTPStatusError on a bad key."""
    client = http or httpx.Client(timeout=20)
    resp = client.get(f"{base_url}/models", headers={"Authorization": f"Bearer {key}"})
    resp.raise_for_status()
    return [m["id"] for m in resp.json().get("data", [])]


def pick_kimi(models: list[str]) -> str:
    for wanted in KIMI_PREFERENCE:
        if wanted in models:
            return wanted
    kimi = sorted((m for m in models if m.startswith("kimi")), reverse=True)
    return kimi[0] if kimi else (models[0] if models else KIMI_PREFERENCE[0])


def find_kimi(key: str, http: httpx.Client | None = None) -> tuple[str, list[str]]:
    """Try the international then the China endpoint; return (base_url, models)."""
    last: Exception | None = None
    for url in KIMI_URLS:
        try:
            return url, kimi_models(key, url, http)
        except httpx.HTTPError as exc:
            last = exc
    raise click.ClickException(f"Kimi rejected the key or is unreachable: {last}")


@click.group()
def nube() -> None:
    """Cloud models (Kimi, Gemini) for Sergio's brain."""


@nube.command("configurar")
@click.option("--kimi", "kimi_key", default="", help="Kimi (Moonshot) API key.")
@click.option("--gemini", "gemini_key", default="", help="Gemini / Google API key.")
@click.option("--modelo", default="", help="Force a model id (e.g. kimi-k2.6).")
def configurar(kimi_key: str, gemini_key: str, modelo: str) -> None:
    """Save the keys, check them and make Kimi Sergio's main model."""
    from openjarvis.cli.phone_cmd import read_env, update_config, write_env
    from openjarvis.cli.service_cmd import env_file
    from openjarvis.core.paths import get_config_dir

    env_path = env_file()
    env = read_env(env_path)
    if not kimi_key and not gemini_key:
        kimi_key = click.prompt(
            "Clave de Kimi (Enter para omitir)",
            default="",
            hide_input=True,
            show_default=False,
        ).strip()
        gemini_key = click.prompt(
            "Clave de Gemini (Enter para omitir)",
            default="",
            hide_input=True,
            show_default=False,
        ).strip()
    kimi_key = clean_key(kimi_key or env.get("MOONSHOT_API_KEY", ""))
    gemini_key = clean_key(gemini_key or env.get("GEMINI_API_KEY", ""))
    if not kimi_key and not gemini_key:
        raise click.ClickException("No keys given.")

    updates: dict[str, str] = {}
    main_model = modelo
    if kimi_key:
        # A bad Kimi key must not stop Gemini from being saved.
        try:
            base_url, models = find_kimi(kimi_key)
        except click.ClickException as exc:
            console.print(
                f"[yellow]Kimi no funcionó ({escape(exc.message[:200])}); "
                "sigo sin Kimi.[/yellow]"
            )
            updates["MOONSHOT_API_KEY"] = ""  # forget a key that does not work
            if not gemini_key:
                write_env(env_path, updates)
                raise click.ClickException(
                    "Kimi rechazó la clave y no hay clave de Gemini."
                ) from exc
        else:
            chosen = modelo or pick_kimi(models)
            console.print(
                f"[green]Kimi OK[/green] ({base_url}): modelo {escape(chosen)}"
            )
            updates.update(MOONSHOT_API_KEY=kimi_key, MOONSHOT_BASE_URL=base_url)
            main_model = main_model or chosen
    if gemini_key:
        updates["GEMINI_API_KEY"] = gemini_key
        done = subprocess.run(
            ["uv", "pip", "install", "-q", "-U", "google-genai>=2.0"],
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode == 0:
            console.print(
                "[green]Gemini listo[/green] (se usa si eliges un modelo gemini-…)."
            )
        else:
            why = escape(done.stderr[-300:])
            console.print(f"[yellow]No pude instalar google-genai: {why}[/yellow]")
        main_model = main_model or GEMINI_MODEL
    write_env(env_path, updates)

    config_path = get_config_dir() / "config.toml"
    update_config(
        config_path,
        {"intelligence": {"default_model": main_model, "fallback_model": "qwen3:8b"}},
    )
    subprocess.run(
        ["systemctl", "--user", "try-restart", "sergio.service"],
        capture_output=True,
        check=False,
    )
    console.print(
        "\n[green]Listo.[/green] Sergio ahora piensa con "
        f"[bold]{escape(main_model)}[/bold]. "
        "Si no hay internet usa qwen3:8b. Las claves están solo en "
        f"{env_path} (privado)."
    )


@nube.command("voz")
@click.option("--elevenlabs", "eleven_key", default="", help="ElevenLabs API key.")
def voz(eleven_key: str) -> None:
    """Sergio's voice with ElevenLabs (deep, warm, raspy; the lowest delay)."""
    from openjarvis.cli.phone_cmd import read_env, write_env
    from openjarvis.cli.service_cmd import env_file
    from openjarvis.speech.elevenlabs_voice import API, VOICE_ID, VOICE_NAME

    env_path = env_file()
    eleven_key = clean_key(
        eleven_key
        or read_env(env_path).get("ELEVENLABS_API_KEY", "")
        or click.prompt("Clave de ElevenLabs", hide_input=True).strip()
    )
    headers = {"xi-api-key": eleven_key}
    with httpx.Client(timeout=20) as http:
        mine = http.get(f"{API}/voices/{VOICE_ID}", headers=headers)
        if mine.status_code in (401, 403) and "voice" not in mine.text.lower():
            raise click.ClickException("ElevenLabs rechazó la clave.")
        if mine.status_code != 200:
            # A library voice must be in "My Voices" to be used by the API.
            found = http.get(f"{API}/shared-voices", headers=headers,
                             params={"search": "J Thomas Warm Raspy", "page_size": 30})
            owner = next(
                (v.get("public_owner_id") for v in (found.json().get("voices") or [])
                 if v.get("voice_id") == VOICE_ID),
                None,
            ) if found.status_code == 200 else None
            added = (
                http.post(f"{API}/voices/add/{owner}/{VOICE_ID}", headers=headers,
                          json={"new_name": "Sergio (grave y rasposa)"})
                if owner else None
            )
            if added is None or added.status_code != 200:
                console.print(
                    "[yellow]No pude añadir la voz sola. En elevenlabs.io → Voice Library "
                    f"busca «{VOICE_NAME}» y pulsa «Add to my voices».[/yellow]"
                )
    write_env(env_path, {"ELEVENLABS_API_KEY": eleven_key})
    subprocess.run(["systemctl", "--user", "try-restart", "sergio.service"],
                   capture_output=True, check=False)
    console.print(
        "[green]Listo.[/green] Las respuestas de Sergio usan ahora la voz grave y rasposa "
        "de ElevenLabs (empieza a sonar casi al instante). Las llamadas en vivo siguen con "
        "Gemini Live (Algenib). Sin crédito, vuelve a Algenib solo."
    )
