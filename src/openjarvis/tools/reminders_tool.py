"""``reminders``: Sergio keeps the owner's goals, medications and reminders.

«Recuérdame tomar la pastilla a las 8», «mi meta es correr 5 km en diciembre»,
«ya me tomé la medicina»: the store in :mod:`openjarvis.reminders`. Only
notifications for the owner himself; never a message to anyone else, and
never medical advice about the medications.
"""

from __future__ import annotations

from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


def _line(i: dict) -> str:
    when = ", ".join(i["times"]) or "sin hora"
    days = (
        "todos los días"
        if not i["days"]
        else "días " + ",".join(str(d) for d in i["days"])
    )
    if i["date"]:
        days = i["date"]
    extra = i["extra"].get("dose") or i["extra"].get("why") or ""
    return (
        f"[{i['id']}] {i['kind']}: {i['title']}"
        + (f" ({extra})" if extra else "")
        + f" — {when}, {days}"
    )


@ToolRegistry.register("reminders")
class RemindersTool(BaseTool):
    tool_id = "reminders"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Guarda y consulta las metas, medicinas y recordatorios del señor (avisos para él "
                "mismo en la app). action: 'add' (kind: medicina|meta|recordatorio|pendiente "
                "(pendiente: a to-do with no time), title, times "
                "['08:00'], days [0=lunes..6=domingo, vacío = todos], date 'AAAA-MM-DD' para una sola "
                "vez, dose para medicinas, why para metas), 'list', 'done' (id; slot opcional "
                "'AAAA-MM-DDTHH:MM'), 'pause' (id), 'remove' (id). Nunca des consejo médico."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "list", "done", "pause", "remove"],
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["medicina", "meta", "recordatorio", "pendiente"],
                    },
                    "title": {"type": "string"},
                    "times": {"type": "array", "items": {"type": "string"}},
                    "days": {"type": "array", "items": {"type": "integer"}},
                    "date": {"type": "string"},
                    "dose": {"type": "string"},
                    "why": {"type": "string"},
                    "id": {"type": "string"},
                    "slot": {"type": "string"},
                },
                "required": ["action"],
            },
            category="productivity",
        )

    def execute(self, **params: Any) -> ToolResult:
        from datetime import datetime

        from openjarvis.reminders import get_store

        store = get_store()
        action = params.get("action")
        try:
            if action == "add":
                extra = {k: params[k] for k in ("dose", "why") if params.get(k)}
                item = store.add(
                    str(params.get("kind") or "recordatorio"),
                    str(params.get("title") or ""),
                    times=params.get("times") or [],
                    days=params.get("days") or [],
                    date=str(params.get("date") or ""),
                    extra=extra,
                )
                return ToolResult(self.tool_id, f"Guardado: {_line(item)}", True)
            if action == "list":
                items = store.items(str(params.get("kind") or ""), active_only=True)
                text = (
                    "\n".join(_line(i) for i in items)
                    or "No hay nada guardado todavía."
                )
                return ToolResult(self.tool_id, text, True)
            iid = str(params.get("id") or "")
            if action == "done":
                slot = str(params.get("slot") or "")
                if not slot:
                    due = [d for d in store.due() if d["id"] == iid]
                    slot = (
                        due[0]["slot"]
                        if due
                        else datetime.now().strftime("%Y-%m-%dT%H:%M")
                    )
                ok = store.mark(iid, slot, "hecho")
                return ToolResult(
                    self.tool_id,
                    "Anotado como hecho." if ok else "No encuentro ese id.",
                    ok,
                )
            if action == "pause":
                ok = store.update(iid, active=False) is not None
                return ToolResult(
                    self.tool_id, "En pausa." if ok else "No encuentro ese id.", ok
                )
            if action == "remove":
                ok = store.delete(iid)
                return ToolResult(
                    self.tool_id, "Quitado." if ok else "No encuentro ese id.", ok
                )
        except ValueError as exc:
            return ToolResult(self.tool_id, str(exc), False)
        return ToolResult(self.tool_id, "Acción desconocida.", False)


__all__ = ["RemindersTool"]
