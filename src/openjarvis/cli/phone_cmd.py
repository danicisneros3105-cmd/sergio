"""``sergio telefono`` — set up calls and WhatsApp step by step."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.markup import escape

console = Console()

SECRET_KEYS = (
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "NGROK_AUTHTOKEN",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_APP_SECRET",
)


def read_env(path: Path) -> dict[str, str]:
    """Parse KEY=value lines like systemd's EnvironmentFile.

    Accepts an optional leading ``export`` and strips matching surrounding
    quotes, so the CLI and the service see exactly the same values.
    """
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :].lstrip()
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    return values


def write_env(path: Path, updates: dict[str, str]) -> None:
    """Set KEY=value lines in *path*, keeping comments and other keys."""
    lines = path.read_text().splitlines() if path.exists() else []
    done: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.partition("=")[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in updates:
            out.append(f"{key}={updates[key]}")
            done.add(key)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in updates.items() if k not in done and v]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")
    path.chmod(0o600)  # secrets: readable by the user only


def update_config(path: Path, sections: dict[str, dict[str, Any]]) -> None:
    """Merge *sections* into config.toml, preserving everything else."""
    import tomlkit

    doc = tomlkit.parse(path.read_text()) if path.exists() else tomlkit.document()
    for name, values in sections.items():
        table = doc.get(name)
        if table is None:
            table = tomlkit.table()
            doc[name] = table
        for key, value in values.items():
            table[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc))


def point_twilio_number(sid: str, token: str, number: str, voice_url: str) -> str:
    """Make the Twilio number send incoming calls to Sergio."""
    from twilio.rest import Client

    found = Client(sid, token).incoming_phone_numbers.list(phone_number=number, limit=1)
    if not found:
        return f"{number} is not a number in this Twilio account"
    found[0].update(voice_url=voice_url, voice_method="POST")
    return ""


def _ask(label: str, current: str = "", *, secret: bool = False) -> str:
    shown = "(already saved)" if (secret and current) else current
    value = click.prompt(
        label, default=shown or "", show_default=bool(shown), hide_input=secret
    )
    return current if value == "(already saved)" else value.strip()


@click.group()
def telefono() -> None:
    """Calls and WhatsApp: guided setup and checks."""


@telefono.command("configurar")
def configurar() -> None:
    """Ask for the accounts step by step and save them."""
    from openjarvis.cli.service_cmd import env_file
    from openjarvis.core.config import load_config
    from openjarvis.core.paths import get_config_dir
    from openjarvis.phone.numbers import to_e164

    cfg = load_config()
    env_path = env_file()
    env = read_env(env_path)
    console.print(
        "[bold]Sergio — calls and WhatsApp setup[/bold]\n"
        "Leave a field empty to skip it. Secrets are stored only in "
        f"{env_path} (readable only by you).\n"
    )

    console.print("[cyan]1. You[/cyan]")
    while True:
        raw = _ask(
            "Your phone (international, e.g. +593991234567)",
            (cfg.phone.owner_numbers or [""])[0],
        )
        try:
            owner = to_e164(raw)
            break
        except ValueError as exc:
            console.print(f"[red]{escape(str(exc))}[/red]")
    name = _ask("Your name (Sergio says it calls on your behalf)", cfg.phone.owner_name)

    console.print("\n[cyan]2. Twilio (phone line) — twilio.com/console[/cyan]")
    sid = _ask("Account SID", env.get("TWILIO_ACCOUNT_SID", ""))
    token = _ask("Auth Token", env.get("TWILIO_AUTH_TOKEN", ""), secret=True)
    number = _ask(
        "Twilio number (e.g. +15551234567)", env.get("TWILIO_PHONE_NUMBER", "")
    )

    console.print("\n[cyan]3. ngrok (public address) — dashboard.ngrok.com[/cyan]")
    ngrok_token = _ask("Authtoken", env.get("NGROK_AUTHTOKEN", ""), secret=True)
    domain = _ask("Static domain (e.g. sergio-abc.ngrok-free.app)", cfg.tunnel.domain)
    domain = domain.removeprefix("https://").strip("/")

    console.print("\n[cyan]4. WhatsApp (optional) — developers.facebook.com[/cyan]")
    wa_token = _ask("Access token", env.get("WHATSAPP_ACCESS_TOKEN", ""), secret=True)
    wa_id = _ask("Phone number ID", env.get("WHATSAPP_PHONE_NUMBER_ID", ""))
    wa_secret = _ask("App secret", env.get("WHATSAPP_APP_SECRET", ""), secret=True)
    verify = env.get("WHATSAPP_VERIFY_TOKEN") or secrets.token_urlsafe(16)

    write_env(
        env_path,
        {
            "TWILIO_ACCOUNT_SID": sid,
            "TWILIO_AUTH_TOKEN": token,
            "TWILIO_PHONE_NUMBER": number,
            "NGROK_AUTHTOKEN": ngrok_token,
            "WHATSAPP_ACCESS_TOKEN": wa_token,
            "WHATSAPP_PHONE_NUMBER_ID": wa_id,
            "WHATSAPP_APP_SECRET": wa_secret,
            "WHATSAPP_VERIFY_TOKEN": verify if wa_token else "",
        },
    )
    # An empty domain keeps the current tunnel (e.g. a Cloudflare setup).
    public = f"https://{domain}" if domain else cfg.phone.public_url
    sections: dict[str, dict[str, Any]] = {
        "phone": {
            "enabled": bool(sid and token and number and public),
            "owner_numbers": [owner],
            "owner_name": name,
            "public_url": public,
        }
    }
    if domain:
        sections["tunnel"] = {"provider": "ngrok", "domain": domain}
    update_config(get_config_dir() / "config.toml", sections)
    console.print("\n[green]Saved.[/green]")

    if sid and token and number and public:
        try:
            problem = point_twilio_number(
                sid, token, number, f"{public}/phone/incoming"
            )
        except Exception as exc:  # noqa: BLE001 — network/credentials
            problem = str(exc)
        if problem:
            console.print(f"[yellow]Twilio: {escape(problem)}[/yellow]")
        else:
            console.print("Twilio: your number now sends calls to Sergio.")
    if wa_token and public:
        console.print(
            "\nIn Meta (WhatsApp → Configuration → Webhook) paste:\n"
            f"  Callback URL: {public}/webhooks/whatsapp\n"
            f"  Verify token: {verify}\n"
            "and subscribe to 'messages'."
        )
    console.print(
        "\nRestart Sergio to apply: [bold]sergio servicio apagar && "
        "sergio servicio encender[/bold]\n"
        "Then test: [bold]sergio telefono probar[/bold]"
    )


@telefono.command("estado")
def estado() -> None:
    """Show what is configured (never prints secrets)."""
    from openjarvis.cli.service_cmd import env_file
    from openjarvis.core.config import load_config

    cfg = load_config()
    env = {**read_env(env_file()), **os.environ}
    rows = [
        ("Calls enabled", "yes" if cfg.phone.enabled else "no"),
        ("Your numbers", ", ".join(cfg.phone.owner_numbers) or "missing"),
        ("Public address", cfg.phone.public_url or "missing"),
        ("Tunnel", cfg.tunnel.provider or "off"),
    ]
    rows += [(k, "saved" if env.get(k) else "missing") for k in SECRET_KEYS]
    for label, value in rows:
        color = "red" if value in ("missing", "no", "off") else "green"
        console.print(f"{label}: [{color}]{escape(value)}[/{color}]")


@telefono.command("probar")
def probar() -> None:
    """Sergio calls you (test call)."""
    from openjarvis.cli.service_cmd import env_file
    from openjarvis.core.config import load_config
    from openjarvis.tools.phone_tools import PhoneCallTool

    for key, value in read_env(env_file()).items():
        os.environ.setdefault(key, value)
    cfg = load_config()
    if not cfg.phone.owner_numbers:
        raise click.ClickException("Run `sergio telefono configurar` first.")
    console.print(f"Calling {cfg.phone.owner_numbers[0]}… answer your phone.")
    result = PhoneCallTool(config=cfg).execute(
        number=cfg.phone.owner_numbers[0],
        goal="Llamada de prueba: saluda, pregunta si se escucha bien y despídete.",
    )
    console.print(escape(result.content))


__all__ = [
    "configurar",
    "estado",
    "point_twilio_number",
    "probar",
    "read_env",
    "SECRET_KEYS",
    "telefono",
    "update_config",
    "write_env",
]
