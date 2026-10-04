"""What Sergio can do on the laptop during a call (Gemini Live tools).

The live model calls these by name; the companion runs them at once and
answers in a sentence the model can repeat. Sergio's server tools
(desktop_action, files_organize, terminal_run, python_run, web_search, ...)
are offered in the same call by the server itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from sergio_escritorio.call import ClientTool
from sergio_escritorio.jarvis import parse_clock, status_sentence, when_phrase
from sergio_escritorio.quick import SEARCH, parse_quick


def _nothing(*_a: Any, **_k: Any) -> str:
    return "No disponible en este equipo."


@dataclass
class Abilities:
    """The app's abilities the tools use (all optional, for tests)."""

    act: Callable[[dict], Any] = _nothing  # control server action
    snapshot: Callable[[], tuple[bytes, list, float]] | None = None
    screen_help: Callable[[bytes, str, list], dict] | None = None
    point: Callable[[int, int, str], None] = lambda _x, _y, _l: None
    camera: Callable[[bool], str] = _nothing
    hands: Callable[[str], str] = _nothing
    physics: Callable[[str], str] = _nothing
    people: Callable[[], str] = _nothing
    remind: Callable[[float, str], str] = _nothing
    reminders: Callable[[], list] = lambda: []
    status: Callable[[], dict] = lambda: {}
    protocol: Callable[[str], str] = _nothing
    task: Callable[[str], str] = _nothing
    look_screen: Callable[[str], str] = _nothing
    share_screen: Callable[[bool], str] = _nothing
    hang_up: Callable[[], str] = _nothing
    gym: Callable[[], str] = _nothing
    screenshot: Callable[[], str] = _nothing
    now: Callable[[], datetime] = field(default=datetime.now)


def _obj(**props: Any) -> dict[str, Any]:
    required = [k for k, v in props.items() if v.pop("required", False)]
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def _str(desc: str, required: bool = False, enum: list[str] | None = None) -> dict:
    out: dict[str, Any] = {"type": "string", "description": desc, "required": required}
    if enum:
        out["enum"] = enum
    return out


def call_tools(ab: Abilities) -> list[ClientTool]:
    def abrir(args: dict) -> str:
        target = str(args.get("objetivo") or "").strip()
        if not target:
            return "¿Qué abro?"
        quick = parse_quick(f"abre {target}")
        if quick is not None and quick.kind == "open_url":
            ab.act({"action": "open", "target": quick.arg})
        else:
            ab.act({"action": "open_app", "target": target})
        return f"Abierto: {target}."

    def cerrar(args: dict) -> str:
        app = str(args.get("app") or "").strip()
        ab.act({"action": "close_app", "target": app})
        return f"Cerrado: {app}."

    def buscar(args: dict) -> str:
        query = str(args.get("consulta") or "").strip()
        site = str(args.get("sitio") or "google").lower()
        from urllib.parse import quote_plus

        url = SEARCH.get(site, SEARCH["google"]).format(quote_plus(query))
        ab.act({"action": "open", "target": url})
        return f"Busqué «{query}» en {site.title()}; ya está en pantalla."

    def volumen(args: dict) -> str:
        what = str(args.get("accion") or "subir")
        steps = max(1, min(int(args.get("pasos") or 5), 25))
        key = {"subir": "volumeup", "bajar": "volumedown", "silenciar": "volumemute"}.get(what, "volumeup")
        for _ in range(1 if key == "volumemute" else steps):
            ab.act({"action": "key", "keys": key})
        return {"subir": "Volumen arriba.", "bajar": "Volumen abajo."}.get(what, "Silenciado.")

    def multimedia(args: dict) -> str:
        what = str(args.get("accion") or "pausa")
        key = {
            "pausa": "playpause",
            "reproducir": "playpause",
            "siguiente": "nexttrack",
            "anterior": "prevtrack",
        }.get(what, "playpause")
        ab.act({"action": "key", "keys": key})
        return "Hecho."

    def senalar(args: dict) -> str:
        what = str(args.get("que") or "").strip()
        if ab.snapshot is None or ab.screen_help is None:
            return "No puedo ver la pantalla ahora."
        png, elements, scale = ab.snapshot()
        reply = ab.screen_help(png, f"Señala dónde está: {what}", elements)
        from sergio_escritorio.voice import target_point

        spot = target_point(reply, elements, scale)
        if spot is None:
            return str(reply.get("answer") or f"No encuentro «{what}» en la pantalla.")
        ab.point(spot[0], spot[1], str(reply.get("label") or what))
        return f"Lo señalé en la pantalla. {reply.get('answer') or ''}".strip()

    def recordatorio(args: dict) -> str:
        text = str(args.get("texto") or "").strip()
        now = ab.now()
        when: datetime | None = None
        if args.get("minutos"):
            when = now + timedelta(minutes=float(args["minutos"]))
        elif args.get("hora"):
            raw = str(args["hora"]).strip().lower()
            when = parse_clock(raw if raw.startswith("a las") else f"a las {raw}", now)
        if when is None:
            return "Necesito en cuántos minutos o a qué hora."
        ab.remind(when.timestamp(), text)
        return f"Le avisaré {when_phrase(when, now)}" + (f": {text}." if text else ".")

    def pendientes(_args: dict) -> str:
        items = ab.reminders()
        if not items:
            return "No hay recordatorios pendientes."
        now = ab.now()
        return "; ".join(
            f"{r.text or 'temporizador'} {when_phrase(datetime.fromtimestamp(r.due), now)}"
            for r in items[:6]
        )

    def estado(_args: dict) -> str:
        return status_sentence(ab.status())

    return [
        ClientTool(
            "colgar",
            "Termina la llamada. Úsala cuando el usuario se despida, después de "
            "decir adiós.",
            lambda _a: ab.hang_up(),
        ),
        ClientTool(
            "mirar_pantalla",
            "Toma una captura de la pantalla del usuario y te la envía para que la "
            "veas (para preguntas sobre lo que hay en pantalla).",
            lambda a: ab.look_screen(str(a.get("pregunta") or "")),
            _obj(pregunta=_str("Qué quiere saber de la pantalla")),
        ),
        ClientTool(
            "compartir_pantalla",
            "Activa o desactiva ver la pantalla del usuario en vivo durante la "
            "llamada (una imagen por segundo).",
            lambda a: ab.share_screen(bool(a.get("activar", True))),
            _obj(activar={"type": "boolean", "description": "true para ver, false para dejar de ver"}),
        ),
        ClientTool(
            "senalar",
            "Vuela el compañero del cursor hasta algo de la pantalla (un botón, "
            "menú, campo o texto) para mostrárselo al usuario.",
            senalar,
            _obj(que=_str("Qué señalar, p. ej. 'el botón Exportar'", required=True)),
        ),
        ClientTool(
            "abrir",
            "Abre al instante una app de Windows o una web por su nombre "
            "(Spotify, Chrome, YouTube, Gmail, WhatsApp, Word, calculadora...).",
            abrir,
            _obj(objetivo=_str("App o sitio a abrir", required=True)),
        ),
        ClientTool(
            "cerrar",
            "Cierra una app de Windows por su nombre (como pulsar la X).",
            cerrar,
            _obj(app=_str("App a cerrar", required=True)),
        ),
        ClientTool(
            "buscar_en_navegador",
            "Abre una búsqueda en el navegador (Google, YouTube, Amazon o Maps).",
            buscar,
            _obj(
                consulta=_str("Qué buscar", required=True),
                sitio=_str("Dónde buscar", enum=["google", "youtube", "amazon", "maps"]),
            ),
        ),
        ClientTool(
            "volumen",
            "Sube, baja o silencia el volumen de la computadora.",
            volumen,
            _obj(
                accion=_str("Qué hacer", required=True, enum=["subir", "bajar", "silenciar"]),
                pasos={"type": "integer", "description": "Cuánto (1-25, normal 5)"},
            ),
        ),
        ClientTool(
            "multimedia",
            "Controla la música o el video: pausa, reproducir, siguiente o anterior.",
            multimedia,
            _obj(accion=_str("Qué hacer", required=True, enum=["pausa", "reproducir", "siguiente", "anterior"])),
        ),
        ClientTool(
            "camara",
            "Abre o cierra la ventana de la cámara. Abierta, recibes sus imágenes "
            "en vivo y ves personas, animales y objetos.",
            lambda a: ab.camera(str(a.get("accion") or "abrir") == "abrir"),
            _obj(accion=_str("abrir o cerrar", required=True, enum=["abrir", "cerrar"])),
        ),
        ClientTool(
            "quien_esta",
            "Dice quién y qué hay frente a la cámara según el reconocimiento facial "
            "y de objetos (nombres de personas conocidas, especies, objetos).",
            lambda _a: ab.people(),
        ),
        ClientTool(
            "manos",
            "Cambia el control con las manos: off, gestos, mouse (mouse en el "
            "aire), 3d (Blender) o fisica (objetos con física en la cámara).",
            lambda a: ab.hands(str(a.get("modo") or "off")),
            _obj(modo=_str("Modo", required=True, enum=["off", "gestos", "mouse", "3d", "fisica"])),
        ),
        ClientTool(
            "fisica",
            "Crea o controla objetos con física real en la cámara: 'crea 5 cubos "
            "rojos', 'lanza una pelota', 'gravedad cero', 'gravedad lunar', "
            "'explota todo', 'borra los objetos'.",
            lambda a: ab.physics(str(a.get("orden") or "")),
            _obj(orden=_str("La orden, en español", required=True)),
        ),
        ClientTool(
            "recordatorio",
            "Pone un temporizador o recordatorio que sonará en voz alta: en X "
            "minutos o a una hora.",
            recordatorio,
            _obj(
                texto=_str("Qué recordar (vacío para un temporizador)"),
                minutos={"type": "number", "description": "Dentro de cuántos minutos"},
                hora=_str("A qué hora, p. ej. '19:30' o '7 y media de la tarde'"),
            ),
        ),
        ClientTool(
            "recordatorios_pendientes",
            "Lista los recordatorios y temporizadores pendientes.",
            pendientes,
        ),
        ClientTool(
            "estado_sistema",
            "Batería, procesador, memoria y disco de la computadora.",
            estado,
        ),
        ClientTool(
            "protocolo",
            "Ejecuta un protocolo (varias acciones de golpe): trabajo, "
            "concentracion, musica, fiesta, descanso.",
            lambda a: ab.protocol(str(a.get("nombre") or "")),
            _obj(nombre=_str("Nombre del protocolo", required=True)),
        ),
        ClientTool(
            "tarea",
            "Encarga a Sergio un trabajo largo o de muchos pasos (investigar, "
            "editar video, Blender, programar, organizar carpetas). Corre en "
            "segundo plano con todas sus herramientas; el resultado te llegará "
            "después como mensaje.",
            lambda a: ab.task(str(a.get("descripcion") or "")),
            _obj(descripcion=_str("El encargo completo, con todos los detalles", required=True)),
        ),
        ClientTool(
            "captura_de_pantalla",
            "Guarda una captura de la pantalla en Imágenes\\Sergio.",
            lambda _a: ab.screenshot(),
        ),
        ClientTool(
            "gimnasio_mental",
            "Empieza ahora un ejercicio del gimnasio mental (no se puede saltar).",
            lambda _a: ab.gym(),
        ),
    ]


def call_context(now: datetime, status: dict, reminders: list, camera_on: bool, owner: str = "") -> str:
    """What Sergio should know when the call starts."""
    from sergio_escritorio.quick import spoken_date, spoken_time

    parts = [f"{spoken_date(now)} {spoken_time(now)} Estamos en Ecuador."]
    if owner:
        parts.append(f"Hablas con {owner}.")
    if "battery" in status:
        charge = ", cargando" if status.get("charging") else ""
        parts.append(f"Batería al {status['battery']}%{charge}.")
    if reminders:
        first = reminders[0]
        parts.append(
            f"Recordatorio pendiente: {first.text or 'temporizador'} "
            f"{when_phrase(datetime.fromtimestamp(first.due), now)}."
        )
    parts.append(
        "La cámara está abierta: recibes sus imágenes."
        if camera_on
        else "La cámara está cerrada (puedes abrirla con camara)."
    )
    return " ".join(parts)


__all__ = ["Abilities", "call_context", "call_tools"]
