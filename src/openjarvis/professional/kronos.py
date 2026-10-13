"""Validated, offline Kronos handoff. Forecasts are scenarios, never trade orders."""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path

from openjarvis.security.process_runner import run_bounded

REVISION = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"


def validate(rows: list[dict], future: list[str]) -> dict:
    if not isinstance(rows, list) or not 16 <= len(rows) <= 512:
        raise ValueError("Kronos requiere de 16 a 512 velas históricas.")
    if not isinstance(future, list) or not 1 <= len(future) <= 120:
        raise ValueError(
            "Proporcione de 1 a 120 fechas futuras del calendario de su mercado."
        )
    dates = []
    clean = []
    for row in rows:
        values = {}
        for key in ("open", "high", "low", "close", "volume", "amount"):
            raw = row.get(key, 0) if key in ("volume", "amount") else row.get(key)
            if (
                type(raw) not in (int, float)
                or not math.isfinite(raw)
                or raw < 0
                or (key in ("open", "high", "low", "close") and raw == 0)
            ):
                raise ValueError(
                    "Las velas requieren valores finitos y precios positivos."
                )
            values[key] = float(raw)
        if not (
            values["low"]
            <= min(values["open"], values["close"])
            <= max(values["open"], values["close"])
            <= values["high"]
        ):
            raise ValueError("OHLC incoherente: low ≤ open/close ≤ high.")
        stamp = datetime.fromisoformat(
            str(row.get("timestamp", "")).replace("Z", "+00:00")
        )
        if stamp.tzinfo is None:
            raise ValueError("Todas las fechas requieren zona horaria.")
        dates.append(stamp)
        clean.append({"timestamp": stamp.isoformat(), **values})
    all_dates = dates + [
        datetime.fromisoformat(str(s).replace("Z", "+00:00")) for s in future
    ]
    if any(d.tzinfo is None for d in all_dates) or any(
        a >= b for a, b in zip(all_dates, all_dates[1:])
    ):
        raise ValueError(
            "Fechas estrictamente crecientes, sin duplicados ni fuga de datos futuros."
        )
    return {"rows": clean, "future": [d.isoformat() for d in all_dates[len(dates) :]]}


def forecast(rows: list[dict], future: list[str]) -> dict:
    payload = validate(rows, future)
    root = Path(
        os.environ.get(
            "SERGIO_KRONOS_DIR", Path.home() / ".local/share/sergio-integrations/Kronos"
        )
    )
    python = (
        root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    model = root / "weights" / "model"
    tokenizer = root / "weights" / "tokenizer"
    if not python.is_file() or not model.is_dir() or not tokenizer.is_dir():
        raise ValueError(
            "Kronos no está preparado: instale el entorno y sus pesos locales. "
            "No descargué modelos ni inventé una previsión."
        )
    worker = Path(__file__).with_name("kronos_worker.py")
    # No provider keys, proxy settings or implicit Hugging Face downloads.
    env = {
        k: v
        for k, v in os.environ.items()
        if k in {"PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG"}
    }
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="2")
    with tempfile.TemporaryDirectory(prefix="sergio-kronos-") as temp:
        source = Path(temp) / "input.json"
        source.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
        source.chmod(0o600)
        result = run_bounded(
            [str(python), "-I", str(worker), str(root), str(source)],
            timeout=120,
            env=env,
            max_output_bytes=500_000,
        )
    if result.timed_out or result.truncated or result.returncode:
        raise ValueError("Kronos no completó el cálculo local dentro de los límites.")
    marker = next(
        (
            s[len("SERGIO_KRONOS ") :]
            for s in result.stdout.splitlines()
            if s.startswith("SERGIO_KRONOS ")
        ),
        "",
    )
    values = json.loads(marker)
    if len(values) != len(future) or any(
        not isinstance(x, dict)
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in x.values())
        for x in values
    ):
        raise ValueError("El modelo devolvió una previsión inválida.")
    return {
        "model": "Kronos (pesos locales)",
        "revision": REVISION,
        "scenario": values,
        "timestamps": payload["future"],
        "last_observed_close": payload["rows"][-1]["close"],
        "trading_enabled": False,
        "kind": "model_scenario",
        "accuracy": "not_calibrated",
    }
