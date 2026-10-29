"""Sergio uses the computer for you, step by step, like a person would.

Look (screenshot of the screen you are using + its buttons and fields) ->
decide one step (Sergio's server asks Gemini) -> do it with the mouse and
keyboard the human way (``human.py``) -> look again to check -> ... until
the goal is reached, it needs you, or it cannot be done.

Before anything that cannot be undone (sending a message or an email,
calling, posting, buying, deleting) it stops and asks, reading back exactly
what will be sent and to whom — unless you already said "sí, envíalo".
Moving the mouse yourself, or Ctrl+Alt+End, stops it at once.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

MAX_STEPS = 60  # signing in, searching and comparing take more than 20 steps
SETTLE = {
    "open": 1.6,
    "click": 0.7,
    "double_click": 0.9,
    "key": 0.6,
    "type": 0.3,
    "scroll": 0.4,
}


@dataclass
class Task:
    goal: str
    confirmed: bool = False
    history: list[str] = field(default_factory=list)
    steps: int = 0


def is_address(target: str) -> bool:
    return (
        "://" in target
        or target.startswith(("www.", "mailto:", "tel:", "sms:"))
        or ("." in target and " " not in target and not target.endswith(".exe"))
    )


class Operator:
    def __init__(
        self,
        controller: Any,
        decide: Callable[..., dict],
        *,
        on_say: Callable[[str], None] = lambda _t: None,
        on_state: Callable[[str], None] = lambda _s: None,
        sleep: Callable[[float], None] = time.sleep,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self.controller = controller
        self.decide = decide  # (png, goal, history, elements, step, max_steps, confirmed) -> action
        self.on_say = on_say
        self.on_state = on_state
        self.sleep = sleep
        self.max_steps = max_steps
        self.pending: Task | None = None  # waiting for the user's answer

    def run(self, goal: str, confirmed: bool = False) -> str:
        return self._work(Task(goal.strip(), confirmed))

    def answer(self, reply: str, confirmed: bool = False) -> str:
        """Carry on with the task that asked a question ("sí, envíalo")."""
        task = self.pending
        if task is None:
            return "No tengo ninguna tarea esperando respuesta."
        self.pending = None
        task.confirmed = task.confirmed or confirmed
        task.history.append(f"the user answered: {reply}")
        return self._work(task)

    # -- the loop -------------------------------------------------------------
    def _took_over(self) -> bool:
        check = getattr(self.controller.backend, "user_took_over", None)
        try:
            return bool(check()) if check else False
        except Exception:  # noqa: BLE001
            return False

    def _work(self, task: Task) -> str:
        if not task.goal:
            return "¿Qué hago en la computadora?"
        said = ""
        while task.steps < self.max_steps:
            if not getattr(self.controller, "enabled", True):
                return "El control está en pausa (Ctrl+Alt+Fin para reanudarlo)."
            if task.steps and self._took_over():
                return "Vi que usted tomó el mouse, así que me detuve. Dígame si sigo."
            task.steps += 1
            self.on_state("acting")
            png, elements, scale = self.controller.snapshot()
            step = self.decide(
                png,
                task.goal,
                task.history,
                elements,
                task.steps,
                self.max_steps,
                task.confirmed,
            )
            kind = str(step.get("action") or "fail")
            say = str(step.get("say") or "").strip()
            if say and say != said:
                self.on_say(say)
                said = say
            if kind == "done":
                return f"Hecho. {say}".strip()
            if kind == "fail":
                return f"No pude terminarlo: {say or 'no encontré la manera'}."
            if kind == "ask":
                self.pending = task
                return f"PREGUNTA PARA EL USUARIO: {say}"
            try:
                result = self._do(kind, step, scale)
            except PermissionError:
                return "El control está en pausa o usted lo detuvo."
            except Exception as exc:  # noqa: BLE001 — tell the model, try again
                result = f"error: {exc}"
            task.history.append(
                f"step {task.steps}: {self._describe(kind, step)} -> {result}"
            )
            self.sleep(SETTLE.get(kind, 0.5))
        self.pending = task
        return "Llevo muchos pasos sin terminar; ¿sigo intentándolo o lo dejamos?"

    @staticmethod
    def _describe(kind: str, step: dict) -> str:
        if kind == "type":
            return f"typed {step.get('text', '')!r}"
        if kind == "key":
            return f"pressed {step.get('keys')}"
        if kind == "open":
            return f"opened {step.get('target')}"
        if kind == "scroll":
            return f"scrolled {step.get('amount')}"
        if kind == "wait":
            return "waited"
        where = (
            f"element {step['element']}"
            if step.get("element") is not None
            else f"({step.get('x')}, {step.get('y')})"
        )
        return f"{kind} on {where}"

    def _do(self, kind: str, step: dict, scale: Any) -> str:
        act = self.controller.act
        if kind in ("click", "double_click", "right_click"):
            to_screen = getattr(scale, "to_screen", None)
            x, y = (
                to_screen(step["x"], step["y"])
                if to_screen
                else (round(step["x"] * float(scale)), round(step["y"] * float(scale)))
            )
            return act({"action": kind, "x": x, "y": y})
        if kind == "type":
            return act({"action": "type", "text": str(step.get("text") or "")})
        if kind == "key":
            return act({"action": "key", "keys": str(step.get("keys") or "enter")})
        if kind == "scroll":
            return act({"action": "scroll", "amount": int(step.get("amount") or -5)})
        if kind == "open":
            target = str(step.get("target") or "")
            return act(
                {
                    "action": "open" if is_address(target) else "open_app",
                    "target": target,
                }
            )
        self.sleep(1.5)  # wait: something is loading
        return "waited"


__all__ = ["Operator", "Task", "is_address"]
