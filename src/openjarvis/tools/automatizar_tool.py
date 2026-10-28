"""«Haz un canal que suba 3 shorts al día», «búscame clientes», «activa el
trading en papel»: Sergio's heavy automation from the chat (owner only).

See :mod:`openjarvis.automatiza` for what each part does and its limits.
"""

from __future__ import annotations

import json
from typing import Any

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("automatizar")
class AutomatizarTool(BaseTool):
    """Channels that post alone, client/job hunting and trading."""

    tool_id = "automatizar"
    is_local = True

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="automatizar",
            description=(
                "Heavy automation for the owner. Actions: 'estado' (what is connected and running); "
                "'canal' (a channel that makes 'por_dia' videos a day about 'idea' and posts them to "
                "'publicar_en': youtube and/or instagram; 'formato' 9:16 for Shorts/Reels; the user "
                "must have connected the account in Sergio → Automatizar; never create accounts); "
                "'respuestas' (draft replies to new YouTube comments; they are sent only when the "
                "user approves them in the app); 'perfil_oportunidades' (save what the user does and "
                "seeks: 'habilidades' list, 'servicio', 'busco' trabajo|clientes|ambos, 'lugar', "
                "'remoto', 'tarifa', 'sobre_mi'); 'buscar_oportunidades' (find jobs and clients, rank "
                "and draft proposals; nothing is sent); 'trading_prueba' (backtest 'estrategia' "
                "cruce_medias|momentum|reversion on 'simbolo' with real prices); 'trading_ajustes' "
                "('activo', 'estrategia', 'simbolos', 'limites'; real money needs the user's own "
                "SERGIO_TRADING_REAL=1 AND 'real' true); 'trading_detener'; 'tendencias' (video ideas "
                "from what people search, read and watch NOW in 'pais' (ISO code, default EC) for "
                "the 'idea' niche: each idea cites its real signal; nothing invented). Never promise "
                "profits."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "estado",
                            "canal",
                            "respuestas",
                            "perfil_oportunidades",
                            "buscar_oportunidades",
                            "trading_prueba",
                            "trading_ajustes",
                            "trading_detener",
                            "tendencias",
                        ],
                    },
                    "idea": {"type": "string"},
                    "por_dia": {"type": "integer"},
                    "formato": {"type": "string", "enum": ["9:16", "16:9", "1:1"]},
                    "segundos": {"type": "integer"},
                    "modo": {"type": "string"},
                    "publicar_en": {"type": "array", "items": {"type": "string"}},
                    "habilidades": {"type": "array", "items": {"type": "string"}},
                    "servicio": {"type": "string"},
                    "busco": {"type": "string"},
                    "lugar": {"type": "string"},
                    "remoto": {"type": "boolean"},
                    "tarifa": {"type": "string"},
                    "sobre_mi": {"type": "string"},
                    "simbolo": {"type": "string"},
                    "estrategia": {"type": "string"},
                    "activo": {"type": "boolean"},
                    "simbolos": {"type": "array", "items": {"type": "string"}},
                    "limites": {"type": "object"},
                    "pais": {"type": "string"},
                },
                "required": ["action"],
            },  # fmt: skip
            category="automation",
            timeout_seconds=600,
            required_capabilities=["network:fetch"],
        )

    def _ok(self, content: str, **meta: Any) -> ToolResult:
        return ToolResult(
            tool_name="automatizar", content=content, success=True, metadata=meta
        )

    def _err(self, content: str) -> ToolResult:
        return ToolResult(tool_name="automatizar", content=content, success=False)

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.automatiza import canales, oportunidades, trading

        action = str(p.get("action") or "estado")
        try:
            if action == "estado":
                data = {"canales": canales.estado(), "trading": trading.estado(),
                        "oportunidades": len(oportunidades.items())}  # fmt: skip
                return self._ok(json.dumps(data, ensure_ascii=False)[:4000])
            if action == "canal":
                from openjarvis.video_essay import schedule

                want = [
                    c
                    for c in p.get("publicar_en") or ["youtube"]
                    if c in ("youtube", "instagram")
                ]
                st = canales.estado()
                missing = [c for c in want if not st[c]["conectado"]]
                per_day = max(1, min(6, int(p.get("por_dia") or 3)))
                every = min(schedule.EVERY_HOURS, key=lambda h: abs(h - 24 / per_day))
                item = schedule.add(
                    str(p.get("idea") or ""), every_hours=every, mode=str(p.get("modo") or "basic"),
                    aspect=str(p.get("formato") or "9:16"), seconds=int(p.get("segundos") or 45),
                    publish_to=want, auto=not missing,
                )  # fmt: skip
                note = (
                    f" Falta conectar {', '.join(missing)} en Automatizar: hasta entonces los videos "
                    "esperan en «Listos para publicar»."
                    if missing
                    else ""
                )
                return self._ok(f"Canal programado: un video cada {every} h sobre «{item['idea']}», "
                                f"publicado en {', '.join(want)}.{note}", programa=item)  # fmt: skip
            if action == "respuestas":
                drafts = canales.draft_replies(canales.youtube_comments())
                return self._ok(
                    f"{len(drafts)} respuestas redactadas; esperan su aprobación en Automatizar."
                )
            if action == "perfil_oportunidades":
                prof = oportunidades.save_profile(
                    {k: v for k, v in p.items() if k != "action"}
                )
                return self._ok(
                    "Perfil guardado: " + json.dumps(prof, ensure_ascii=False)
                )
            if action == "buscar_oportunidades":
                res = oportunidades.hunt()
                return self._ok(json.dumps(res, ensure_ascii=False)[:4000])
            if action == "trading_prueba":
                broker = trading.Broker(real=False)
                closes = broker.closes(
                    str(p.get("simbolo") or "SPY").upper(), days=1500
                )
                res = trading.backtest(
                    closes, str(p.get("estrategia") or "cruce_medias")
                )
                return self._ok(json.dumps(res, ensure_ascii=False))
            if action == "trading_ajustes":
                trading.save_settings(
                    {
                        k: p[k]
                        for k in ("activo", "estrategia", "simbolos", "limites")
                        if k in p
                    }
                )
                return self._ok(json.dumps(trading.estado(), ensure_ascii=False)[:3000])
            if action == "tendencias":
                from openjarvis.automatiza import tendencias

                got = tendencias.ideas(
                    str(p.get("pais") or "EC"), str(p.get("idea") or "")
                )
                if not got.get("ideas"):
                    return self._ok(
                        got.get("aviso") or "Hoy no encontré tendencias que encajen."
                    )
                lines = [
                    f"- {i['titulo']} ({i['formato']}): «{i['gancho']}» — {i['por_que']}"
                    for i in got["ideas"]
                ]
                return self._ok(
                    "Ideas con lo que la gente busca hoy ("
                    + ", ".join(got.get("fuentes") or [])
                    + "):\n"
                    + "\n".join(lines),
                    ideas=got["ideas"],
                )
            if action == "trading_detener":
                trading.stop(True)
                return self._ok("Trading detenido.")
        except Exception as exc:  # noqa: BLE001 — said plainly
            return self._err(str(exc)[:400])
        return self._err("acción desconocida")


__all__ = ["AutomatizarTool"]
