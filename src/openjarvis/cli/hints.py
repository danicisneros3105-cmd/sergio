"""Rich-formatted error hints for common CLI failure modes."""

from __future__ import annotations

from typing import Optional


def hint_no_config() -> str:
    """Return a suggestion when no config file is found."""
    return (
        "[yellow]Hint:[/yellow] No config file found.\n"
        "  Run [bold]jarvis init[/bold] to detect hardware and generate "
        "[cyan]~/.openjarvis/config.toml[/cyan].\n"
        "  Or run [bold]jarvis quickstart[/bold] for a guided setup."
    )


def hint_no_engine(engine_name: Optional[str] = None) -> str:
    """Return a suggestion when the inference engine is unreachable."""
    name = engine_name or "ollama"
    return (
        f"[yellow]Hint:[/yellow] Engine '{name}' is not reachable.\n"
        f"  Make sure the {name} server is running.\n"
        "  Run [bold]jarvis doctor[/bold] to check all engines.\n"
        "  Run [bold]jarvis quickstart[/bold] for guided setup.\n"
        "\n"
        "  [dim]To use a remote engine:[/dim]\n"
        f"    [cyan]jarvis config set engine.{name}.host http://<remote-ip>:<port>[/cyan]\n"
        f"    [dim]or[/dim] [cyan]export OLLAMA_HOST=http://<remote-ip>:11434[/cyan]"
    )


def hint_engine_error(exc: BaseException, engine_name: Optional[str] = None) -> str:
    """The right advice for an engine failure: a quota, a server error or a
    bad answer is not "the server is not running"."""
    text = str(exc)
    low = text.lower()
    if (
        "429" in text
        or "quota" in low
        or "resource_exhausted" in low
        or "rate limit" in low
    ):
        return (
            "[yellow]Hint:[/yellow] the model is out of quota or rate-limited right now.\n"
            "  Wait a minute and try again, or use another model with "
            "[bold]-m <model>[/bold]."
        )
    if "401" in text or "403" in text or "api key" in low or "unauthorized" in low:
        return (
            "[yellow]Hint:[/yellow] the model rejected the API key.\n"
            "  Check the key: [bold]sergio nube configurar --gemini TU_CLAVE[/bold]."
        )
    if "not json" in low:
        return (
            "[yellow]Hint:[/yellow] something that is not a model server answered on that port.\n"
            f"  Check [bold]engine.{engine_name or 'ollama'}.host[/bold] with "
            "[bold]jarvis config show[/bold]."
        )
    if any(f"http {code}" in low for code in ("500", "502", "503", "504")):
        return (
            f"[yellow]Hint:[/yellow] the {engine_name or 'model'} server had an internal error.\n"
            "  Try again; if it repeats, restart it or check its log."
        )
    return hint_no_engine(engine_name)


def hint_no_model(model_name: Optional[str] = None) -> str:
    """Return a suggestion when no model is available."""
    if model_name:
        return (
            f"[yellow]Hint:[/yellow] Model '{model_name}' not found.\n"
            f"  Try: [bold]ollama pull {model_name}[/bold]\n"
            "  Run [bold]jarvis model list[/bold] to see available models."
        )
    return (
        "[yellow]Hint:[/yellow] No models available.\n"
        "  Pull a model first: [bold]ollama pull qwen3.5:2b[/bold]\n"
        "  Run [bold]jarvis model list[/bold] to see available models."
    )


def mining_not_running_hint(cfg: object | None, sidecar_present: bool) -> Optional[str]:
    """Return a mining hint when configured but no session sidecar exists."""
    if cfg is None or sidecar_present:
        return None
    return "mining configured but not running - start it with `jarvis mine start`"


__all__ = [
    "hint_engine_error",
    "hint_no_config",
    "hint_no_engine",
    "hint_no_model",
    "mining_not_running_hint",
]
