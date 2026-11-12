"""Budget Control — Control de presupuesto para APIs externas.

EVITA GASTOS EXCESIVOS. Cada llamada a API externa pasa por aqui.
Registra uso diario/mensual y bloquea si se excede el limite.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openjarvis.core.paths import get_config_dir


@dataclass
class BudgetState:
    """Estado actual del presupuesto."""

    day_calls: int = 0
    day_cost_usd: float = 0.0
    month_cost_usd: float = 0.0
    last_reset_day: str = ""
    last_reset_month: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_calls": self.day_calls,
            "day_cost_usd": round(self.day_cost_usd, 4),
            "month_cost_usd": round(self.month_cost_usd, 4),
            "last_reset_day": self.last_reset_day,
            "last_reset_month": self.last_reset_month,
            "history": self.history[-500:],  # Mantener ultimos 500 registros
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetState":
        return cls(
            day_calls=data.get("day_calls", 0),
            day_cost_usd=data.get("day_cost_usd", 0.0),
            month_cost_usd=data.get("month_cost_usd", 0.0),
            last_reset_day=data.get("last_reset_day", ""),
            last_reset_month=data.get("last_reset_month", ""),
            history=data.get("history", []),
        )


class BudgetController:
    """Controla el gasto en APIs externas para mantener rentabilidad."""

    # Costos aproximados por API (USD) — AJUSTAR segun tarifas reales
    COSTS: dict[str, float] = {
        # LLMs (por 1K tokens de entrada)
        "openrouter": 0.003,       # Mixto, varia por modelo
        "gemini": 0.0,             # GRATIS (60 req/min)
        "openai": 0.005,           # GPT-4o
        "anthropic": 0.015,        # Claude 3.5
        # Voz
        "elevenlabs": 0.05,        # Por 1K caracteres (~$5/mes)
        "deepgram": 0.0043,        # Por minuto de audio
        "kokoro": 0.0,             # LOCAL, GRATIS
        # Video generacion (por segundo)
        "kling": 0.15,
        "runway": 0.30,
        "pika": 0.20,
        "luma": 0.25,
        # Imagen
        "image_generate": 0.02,    # Por imagen
        # Otros
        "web_search": 0.005,
        "browser": 0.001,
    }

    def __init__(self) -> None:
        self._state_path = Path(get_config_dir()) / "budget_state.json"
        self._state = self._load()
        self._max_calls_day = int(os.environ.get("SERGIO_MAX_LLAMADAS_DIA", "100"))
        self._max_cost_day = float(os.environ.get("SERGIO_MAX_COSTO_DIA_USD", "2.00"))
        self._max_cost_month = float(os.environ.get("SERGIO_MAX_COSTO_MES_USD", "15.00"))
        self._check_resets()

    def _load(self) -> BudgetState:
        if self._state_path.exists():
            try:
                with open(self._state_path, "r", encoding="utf-8") as f:
                    return BudgetState.from_dict(json.load(f))
            except Exception:
                pass
        return BudgetState()

    def _save(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state.to_dict(), f, indent=2)

    def _check_resets(self) -> None:
        """Reinicia contadores diarios/mensuales si cambio el periodo."""
        today = time.strftime("%Y-%m-%d")
        this_month = time.strftime("%Y-%m")

        if self._state.last_reset_day != today:
            self._state.day_calls = 0
            self._state.day_cost_usd = 0.0
            self._state.last_reset_day = today

        if self._state.last_reset_month != this_month:
            self._state.month_cost_usd = 0.0
            self._state.last_reset_month = this_month

    def can_spend(self, api_name: str, estimated_cost: float | None = None) -> tuple[bool, str]:
        """Podemos hacer esta llamada? Retorna (ok, razon_si_no)."""
        self._check_resets()

        # Limite de llamadas diarias
        if self._state.day_calls >= self._max_calls_day:
            return False, f"Limite diario de llamadas alcanzado ({self._max_calls_day}). Vuelve manana o actualiza tu plan."

        # Calcular costo estimado
        cost = estimated_cost or self.COSTS.get(api_name, 0.01)

        # Limite diario de costo
        if self._state.day_cost_usd + cost > self._max_cost_day:
            return False, f"Limite diario de gasto alcanzado (${self._max_cost_day:.2f}). Vuelve manana o actualiza tu plan."

        # Limite mensual de costo
        if self._state.month_cost_usd + cost > self._max_cost_month:
            return False, f"Limite mensual de gasto alcanzado (${self._max_cost_month:.2f}). Actualiza tu plan para continuar."

        return True, ""

    def record_call(self, api_name: str, cost_usd: float | None = None, details: str = "") -> None:
        """Registra una llamada a API."""
        self._check_resets()
        cost = cost_usd or self.COSTS.get(api_name, 0.01)

        self._state.day_calls += 1
        self._state.day_cost_usd += cost
        self._state.month_cost_usd += cost

        self._state.history.append({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "api": api_name,
            "cost_usd": round(cost, 6),
            "details": details,
        })

        self._save()

    def get_status(self) -> dict[str, Any]:
        """Estado actual del presupuesto para mostrar al usuario."""
        self._check_resets()
        return {
            "day_calls": self._state.day_calls,
            "max_calls_day": self._max_calls_day,
            "day_cost_usd": round(self._state.day_cost_usd, 4),
            "max_cost_day_usd": self._max_cost_day,
            "month_cost_usd": round(self._state.month_cost_usd, 4),
            "max_cost_month_usd": self._max_cost_month,
            "calls_remaining": max(0, self._max_calls_day - self._state.day_calls),
            "budget_remaining_day": max(0.0, self._max_cost_day - self._state.day_cost_usd),
            "budget_remaining_month": max(0.0, self._max_cost_month - self._state.month_cost_usd),
        }

    def suggest_plan(self) -> str:
        """Sugiere un plan segun el uso actual."""
        status = self.get_status()
        month_used = status["month_cost_usd"]

        if month_used < 5:
            return "free"
        elif month_used < 15:
            return "pro"
        else:
            return "studio"


# Singleton
_budget_controller: BudgetController | None = None


def get_budget_controller() -> BudgetController:
    global _budget_controller
    if _budget_controller is None:
        _budget_controller = BudgetController()
    return _budget_controller


def can_spend(api_name: str, estimated_cost: float | None = None) -> tuple[bool, str]:
    """Funcion helper rapida."""
    return get_budget_controller().can_spend(api_name, estimated_cost)


def record_call(api_name: str, cost_usd: float | None = None, details: str = "") -> None:
    """Funcion helper rapida."""
    get_budget_controller().record_call(api_name, cost_usd, details)


def get_budget_status() -> dict[str, Any]:
    """Funcion helper rapida."""
    return get_budget_controller().get_status()
