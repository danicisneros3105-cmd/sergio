"""Bolsa: stock and crypto forecasts with Kronos.

Kronos (shiyu-coder/Kronos, MIT) is an open foundation model for financial
candlesticks (OHLCV). It needs PyTorch, which Sergio does not carry, so it
lives in its own folder with its own Python: ``~/.openjarvis/apps/kronos``
(the repository and a venv with the CPU build of torch). Sergio fetches the
price history (Yahoo Finance's public chart data, Stooq as a fallback),
hands it to ``kronos_runner.py`` in that Python and gets the forecast back.

A forecast is a model's guess, never financial advice: the UI and every
answer say so.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from openjarvis.creator.llm import CreatorError

REPO_URL = "https://github.com/shiyu-coder/Kronos"
MODELS = {
    "small": ("NeoQuasar/Kronos-small", "NeoQuasar/Kronos-Tokenizer-base", 512),
    "mini": ("NeoQuasar/Kronos-mini", "NeoQuasar/Kronos-Tokenizer-2k", 2048),
}
PACKAGES = [
    "einops==0.8.1",
    "huggingface_hub>=0.33",
    "safetensors>=0.6",
    "pandas",
    "numpy",
    "tqdm",
]
TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
NOT_ADVICE = "Es una predicción de un modelo, no un consejo financiero."
MAX_HORIZON = 60

_state: dict[str, Any] = {"installing": False, "error": "", "step": ""}
_lock = threading.Lock()


def folder() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "apps" / "kronos"


def python_path(base: Path | None = None) -> Path:
    base = base or folder()
    return (
        base
        / "venv"
        / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    )


def installed(base: Path | None = None) -> bool:
    base = base or folder()
    return (base / "repo" / "model" / "kronos.py").is_file() and (
        base / ".ready"
    ).is_file()


def status() -> dict[str, Any]:
    return {
        "installed": installed(),
        "installing": bool(_state["installing"]),
        "step": _state["step"],
        "error": _state["error"],
    }


def install_steps(base: Path, uv: str | None, git: str) -> list[tuple[str, list[str]]]:
    """What installing Kronos runs, in order (shown to the owner as it goes)."""
    repo, venv, py = base / "repo", base / "venv", python_path(base)
    steps: list[tuple[str, list[str]]] = []
    if (repo / ".git").is_dir():
        steps.append(
            ("Actualizando Kronos", [git, "-C", str(repo), "pull", "--ff-only"])
        )
    else:
        steps.append(
            ("Descargando Kronos", [git, "clone", "--depth", "1", REPO_URL, str(repo)])
        )
    fresh = not py.exists()
    if uv:
        if fresh:
            steps.append(
                ("Preparando su Python", [uv, "venv", "--python", "3.11", str(venv)])
            )
        steps.append(
            (
                "Instalando PyTorch (CPU, unos minutos)",
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(py),
                    "torch",
                    "--index-url",
                    TORCH_INDEX,
                ],
            )
        )
        steps.append(
            (
                "Instalando lo demás",
                [uv, "pip", "install", "--python", str(py), *PACKAGES],
            )
        )
    else:
        if fresh:
            steps.append(
                ("Preparando su Python", [sys.executable, "-m", "venv", str(venv)])
            )
        steps.append(
            (
                "Instalando PyTorch (CPU, unos minutos)",
                [str(py), "-m", "pip", "install", "torch", "--index-url", TORCH_INDEX],
            )
        )
        steps.append(
            ("Instalando lo demás", [str(py), "-m", "pip", "install", *PACKAGES])
        )
    return steps


def install(run: Callable[..., Any] = subprocess.run, base: Path | None = None) -> None:
    base = base or folder()
    base.mkdir(parents=True, exist_ok=True)
    git = shutil.which("git")
    if not git:
        raise CreatorError("Falta git para descargar Kronos.")
    for step, cmd in install_steps(base, shutil.which("uv"), git):
        _state["step"] = step
        done = run(cmd, capture_output=True, text=True, timeout=1800, check=False)
        if getattr(done, "returncode", 1) != 0:
            tail = (getattr(done, "stderr", "") or getattr(done, "stdout", ""))[-300:]
            raise CreatorError(f"{step}: falló ({tail.strip()})")
    (base / ".ready").write_text(datetime.now(timezone.utc).isoformat())
    _state["step"] = ""


def install_in_background() -> dict[str, Any]:
    with _lock:
        if _state["installing"]:
            return status()
        _state.update(installing=True, error="", step="Empezando")

    def work() -> None:
        try:
            install()
        except Exception as exc:  # noqa: BLE001 — shown in the UI
            _state["error"] = str(exc)[:400]
        finally:
            _state["installing"] = False

    threading.Thread(target=work, daemon=True).start()
    return status()


# -- price history ---------------------------------------------------------------------
def _clean_symbol(symbol: str) -> str:
    s = "".join(
        ch for ch in str(symbol or "").upper().strip() if ch.isalnum() or ch in ".-^="
    )
    if not s or len(s) > 20:
        raise CreatorError("Escriba el símbolo: AAPL, MSFT, BTC-USD, ^GSPC…")
    return s


def parse_yahoo(data: dict[str, Any]) -> list[dict[str, Any]]:
    result = ((data or {}).get("chart") or {}).get("result") or []
    if not result:
        return []
    r = result[0]
    stamps = r.get("timestamp") or []
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for i, ts in enumerate(stamps):
        try:
            row = {
                "date": datetime.fromtimestamp(int(ts), timezone.utc).strftime(
                    "%Y-%m-%d"
                ),
                **{k: float(quote[k][i]) for k in ("open", "high", "low", "close")},
                "volume": float(quote.get("volume", [0] * len(stamps))[i] or 0),
            }
        except (KeyError, TypeError, ValueError, IndexError):
            continue  # a day without trading data
        rows.append(row)
    return rows


def parse_stooq(text: str) -> list[dict[str, Any]]:
    rows = []
    for rec in csv.DictReader(io.StringIO(text or "")):
        try:
            rows.append(
                {
                    "date": rec["Date"],
                    "open": float(rec["Open"]),
                    "high": float(rec["High"]),
                    "low": float(rec["Low"]),
                    "close": float(rec["Close"]),
                    "volume": float(rec.get("Volume") or 0),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def history(
    symbol: str, get: Callable[[str], Any] | None = None
) -> list[dict[str, Any]]:
    """About two years of daily candles, oldest first."""
    symbol = _clean_symbol(symbol)
    if get is None:
        import httpx

        def get(url: str) -> Any:
            resp = httpx.get(
                url, timeout=20, headers={"User-Agent": "Mozilla/5.0 Sergio"}
            )
            resp.raise_for_status()
            return (
                resp.json()
                if "json" in resp.headers.get("content-type", "")
                else resp.text
            )

    rows: list[dict[str, Any]] = []
    try:
        rows = parse_yahoo(
            get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d"
            )
        )
    except Exception:  # noqa: BLE001 — try the other source
        rows = []
    if len(rows) < 60:
        stooq = (
            symbol.lower() if "." in symbol or "-" in symbol else f"{symbol.lower()}.us"
        )
        try:
            text = get(f"https://stooq.com/q/d/l/?s={stooq}&i=d")
            rows = parse_stooq(text if isinstance(text, str) else json.dumps(text))[
                -520:
            ]
        except Exception:  # noqa: BLE001
            pass
    if len(rows) < 60:
        raise CreatorError(
            f"No encontré suficientes datos de «{symbol}». Revise el símbolo."
        )
    return rows


def future_days(last: str, horizon: int, every_day: bool) -> list[str]:
    """The next trading days (weekdays for stocks, every day for crypto)."""
    day = date.fromisoformat(last)
    out = []
    while len(out) < horizon:
        day += timedelta(days=1)
        if every_day or day.weekday() < 5:
            out.append(day.isoformat())
    return out


def forecast(
    symbol: str,
    horizon: int = 20,
    size: str = "small",
    *,
    rows: list[dict[str, Any]] | None = None,
    run: Callable[..., Any] = subprocess.run,
    base: Path | None = None,
) -> dict[str, Any]:
    base = base or folder()
    if not installed(base):
        raise CreatorError("Kronos aún no está instalado. Pulse «Instalar Kronos».")
    symbol = _clean_symbol(symbol)
    horizon = max(1, min(int(horizon), MAX_HORIZON))
    model, tokenizer, context = MODELS.get(size, MODELS["small"])
    rows = rows if rows is not None else history(symbol)
    rows = rows[-context:]
    crypto = symbol.endswith(("-USD", "-EUR", "-USDT")) or symbol in {"BTC", "ETH"}
    req = {
        "repo": str(base / "repo"),
        "model": model,
        "tokenizer": tokenizer,
        "max_context": context,
        "rows": rows,
        "future": future_days(rows[-1]["date"], horizon, crypto),
        "samples": 3,
    }
    runner = Path(__file__).with_name("kronos_runner.py")
    done = run(
        [str(python_path(base)), "-I", str(runner)],
        input=json.dumps(req),
        capture_output=True,
        text=True,
        timeout=900,
        cwd=str(base / "repo"),
        check=False,
    )
    if getattr(done, "returncode", 1) != 0:
        tail = (getattr(done, "stderr", "") or "")[-400:]
        raise CreatorError(f"Kronos no pudo predecir ({tail.strip()})")
    try:
        lines = [
            ln for ln in (done.stdout or "").splitlines() if ln.strip().startswith("{")
        ]
        out = json.loads(lines[-1])["forecast"]
    except (IndexError, KeyError, ValueError) as exc:
        raise CreatorError("Kronos no devolvió una predicción.") from exc
    last, end = rows[-1]["close"], out[-1]["close"]
    change = (end - last) / last * 100 if last else 0.0
    return {
        "symbol": symbol,
        "model": f"Kronos-{size}",
        "history": rows[-120:],
        "forecast": out,
        "last_close": last,
        "end_close": end,
        "change_pct": round(change, 2),
        "note": NOT_ADVICE,
    }


__all__ = [
    "MODELS",
    "NOT_ADVICE",
    "forecast",
    "future_days",
    "history",
    "install_in_background",
    "install_steps",
    "installed",
    "parse_stooq",
    "parse_yahoo",
    "status",
]
