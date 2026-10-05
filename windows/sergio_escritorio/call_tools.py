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
    holo: Callable[[str], str] = _nothing
    blender_holo: Callable[[], str] = _nothing
    blender_object: Callable[[str], str] = _nothing
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
    gym_report: Callable[[], str] = _nothing
    overhead: Callable[[], str] = _nothing
    globe: Callable[[str], str] = _nothing
    photo_who: Callable[[str, str], str] = lambda _s, _p: "No disponible en este equipo."
    kinship: Callable[[str, str], str] = lambda _s, _p: "No disponible en este equipo."
    operate: Callable[[str, bool], str] = lambda _g, _c: "No disponible en este equipo."
    operate_answer: Callable[[str, bool], str] = lambda _a, _c: "No disponible en este equipo."
    message: Callable[[str, str, str, str, bool], str] = lambda *_a: "No disponible en este equipo."
    call_person: Callable[[str, str, bool], str] = lambda *_a: "No disponible en este equipo."
    remember_contact: Callable[[str, str, str], str] = lambda *_a: "No disponible en este equipo."
    screenshot: Callable[[], str] = _nothing
    quick: Callable[[str], str] = _nothing  # an instant order, as said
    video: Callable[[str], str] = _nothing  # find and play a YouTube video
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
            return f"Abierto: {target}; ya está en pantalla."
        try:
            done = str(ab.act({"action": "open_app", "target": target}) or "")
        except LookupError as exc:
            from sergio_escritorio.quick import SITES

            site = SITES.get(target.lower().strip())
            if site:
                ab.act({"action": "open", "target": site})
                return f"{target} no está instalada; abrí su web en el navegador."
            return f"{exc} Puedo buscarla en internet o instalarla con winget si quiere."
        if "still starting" in done:
            return f"{target} está arrancando; aparecerá al frente en su pantalla en unos segundos."
        if "(web" in done:
            return f"No está instalada como app; abrí su web. {done.split(' | ')[-1]}"
        front = done.split("now in front:", 1)[-1].strip() if "now in front:" in done else ""
        return f"Abierto {target}, al frente en su pantalla" + (f" ({front})." if front else ".")

    def cerrar(args: dict) -> str:
        app = str(args.get("app") or "").strip()
        try:
            ab.act({"action": "close_app", "target": app})
        except ValueError:
            return f"No veo {app} abierto."
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
        ab.act({"action": "key", "keys": key, "repeat": 1 if key == "volumemute" else steps})
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
            "poner_video",
            "Busca en YouTube el video que el usuario describe y lo reproduce con "
            "el cursor, a la vista (abre los resultados y hace clic en el correcto). "
            "Pasa la petición completa, con lo que debe verse: «MrBeast con traje negro».",
            lambda a: ab.video(str(a.get("peticion") or "")),
            _obj(peticion=_str("Qué video, con todos los detalles", required=True)),
        ),
        ClientTool(
            "control_equipo",
            "Controla la computadora al instante con una orden en español, tal "
            "como la diría el usuario: «maximiza la ventana», «cierra esta "
            "ventana», «cambia de ventana», «pon el brillo al 70», «baja el "
            "brillo», «modo oscuro», «pon el volumen al 30», «abre la "
            "configuración del wifi», «abre descargas», «copia», «pega», "
            "«guarda», «deshaz», «nueva pestaña», «escribe: <texto>».",
            lambda a: ab.quick(str(a.get("orden") or "")),
            _obj(orden=_str("La orden, en español", required=True)),
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
            "Activa (holo) o apaga (off) las manos del usuario sobre los hologramas "
            "3D de Sergio ve: pellizcar agarra, girar la muñeca gira, dos manos "
            "escalan, soltar en movimiento lanza.",
            lambda a: ab.hands(str(a.get("modo") or "holo")),
            _obj(modo=_str("Modo", required=True, enum=["holo", "off"])),
        ),
        ClientTool(
            "hologramas",
            "Hologramas 3D en Sergio ve, estilo Iron Man: 'crea un cubo rojo', "
            "'crea dos esferas', 'cilindro', 'cono', 'toroide', 'pirámide', "
            "'jarrón', 'diamante', 'más grande', 'gíralo', 'duplícalo', "
            "'bórralo', 'borra todo', 'modo esculpir' (modelar con las manos), "
            "'modo dibujar' (dibujar en el aire: tubo, torno o extrusión), "
            "'suavízalo', 'gravedad' / 'sin gravedad'.",
            lambda a: ab.holo(str(a.get("orden") or "")),
            _obj(orden=_str("La orden, en español", required=True)),
        ),
        ClientTool(
            "hologramas_a_blender",
            "Pasa los hologramas que el usuario creó o modeló con las manos a "
            "Blender y guarda el proyecto (.blend) en Documentos\\Sergio\\Blender.",
            lambda _a: ab.blender_holo(),
        ),
        ClientTool(
            "objeto_a_blender",
            "Analiza el objeto que el usuario tiene en las manos (cámara) y lo "
            "modela con mucho detalle en Blender (piezas, medidas reales, "
            "materiales), guardando el proyecto. Tarda uno o dos minutos: avísale.",
            lambda a: ab.blender_object(str(a.get("nota") or "")),
            _obj(nota=_str("Lo que el usuario dijo del objeto, si algo")),
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
        ClientTool(
            "usar_computadora",
            "Usa la computadora del usuario como una persona, con mouse y teclado, paso "
            "a paso y comprobando cada paso: navegar webs, rellenar formularios, publicar, "
            "configurar algo, cualquier tarea en pantalla. Se detiene y pregunta antes de "
            "enviar, llamar, publicar, comprar o borrar salvo confirmado=true. Si devuelve "
            "PREGUNTA, házsela al usuario y luego usa seguir_tarea con su respuesta.",
            lambda a: ab.operate(str(a.get("objetivo") or ""), bool(a.get("confirmado"))),
            _obj(
                objetivo=_str("La tarea completa con todos los datos", required=True),
                confirmado={"type": "boolean", "description": "true solo si el usuario ya confirmó el envío/llamada/publicación"},
            ),
        ),
        ClientTool(
            "seguir_tarea",
            "Continúa la última tarea de usar_computadora/enviar_mensaje que hizo una "
            "pregunta, con la respuesta del usuario.",
            lambda a: ab.operate_answer(str(a.get("respuesta") or ""), bool(a.get("confirmado"))),
            _obj(
                respuesta=_str("Lo que respondió el usuario", required=True),
                confirmado={"type": "boolean", "description": "true si dijo que sí lo envíe/llame"},
            ),
        ),
        ClientTool(
            "enviar_mensaje",
            "Envía un mensaje o correo a otra persona como lo haría el usuario: WhatsApp, "
            "Instagram, Messenger, Telegram, Gmail, Outlook, SMS, X, TikTok, LinkedIn, "
            "Discord o Teams. 'para' es el nombre del contacto, su @usuario, número o "
            "correo. ANTES lee al usuario a quién y qué se enviará y pregunta; usa "
            "confirmado=true solo cuando diga que sí.",
            lambda a: ab.message(
                str(a.get("plataforma") or "whatsapp"),
                str(a.get("para") or ""),
                str(a.get("mensaje") or ""),
                str(a.get("asunto") or ""),
                bool(a.get("confirmado")),
            ),
            _obj(
                plataforma=_str("whatsapp, instagram, messenger, telegram, gmail, outlook, sms, x...", required=True),
                para=_str("Contacto, @usuario, número o correo", required=True),
                mensaje=_str("El texto exacto", required=True),
                asunto=_str("Asunto (correos)"),
                confirmado={"type": "boolean", "description": "true solo si el usuario confirmó el envío"},
            ),
        ),
        ClientTool(
            "llamar",
            "Hace una llamada telefónica (por el celular del usuario con Enlace Móvil) o "
            "por WhatsApp. Confirma antes con el usuario a quién llamará.",
            lambda a: ab.call_person(
                str(a.get("para") or ""), str(a.get("por") or "telefono"), bool(a.get("confirmado"))
            ),
            _obj(
                para=_str("Contacto o número", required=True),
                por=_str("telefono o whatsapp", enum=["telefono", "whatsapp"]),
                confirmado={"type": "boolean", "description": "true si el usuario confirmó la llamada"},
            ),
        ),
        ClientTool(
            "guardar_contacto",
            "Recuerda cómo contactar a alguien: su teléfono/WhatsApp, Instagram, correo, "
            "Telegram, Messenger, X o TikTok.",
            lambda a: ab.remember_contact(
                str(a.get("nombre") or ""), str(a.get("campo") or ""), str(a.get("valor") or "")
            ),
            _obj(
                nombre=_str("Nombre de la persona", required=True),
                campo=_str("telefono, instagram, correo, telegram, messenger, x, tiktok", required=True),
                valor=_str("El número, usuario o correo", required=True),
            ),
        ),
        ClientTool(
            "quien_es_en_foto",
            "Reconoce a las personas de una foto, también antigua, descolorida o "
            "escaneada: la foto que el usuario sostiene frente a la cámara, la que "
            "está en pantalla o un archivo. Compara la red neuronal y 175 medidas "
            "de la cara con las personas registradas.",
            lambda a: ab.photo_who(str(a.get("origen") or "camara"), str(a.get("ruta") or "")),
            _obj(
                origen=_str("De dónde sale la foto", enum=["camara", "pantalla", "archivo"]),
                ruta=_str("Nombre o ruta del archivo (origen archivo)"),
            ),
        ),
        ClientTool(
            "parecido_familiar",
            "Estima el parecido familiar de las caras de una foto (cámara, pantalla "
            "o archivo) con las personas registradas. Es un indicio, no una prueba "
            "de parentesco (eso solo lo da el ADN): dilo así.",
            lambda a: ab.kinship(str(a.get("origen") or "camara"), str(a.get("ruta") or "")),
            _obj(
                origen=_str("De dónde sale la foto", enum=["camara", "pantalla", "archivo"]),
                ruta=_str("Nombre o ruta del archivo (origen archivo)"),
            ),
        ),
        ClientTool(
            "vuelo_encima",
            "Qué avión pasa AHORA MISMO justo encima del usuario: usa su ubicación "
            "exacta (GPS/Wi-Fi de Windows) y la hora actual con datos ADS-B en vivo: "
            "vuelo, aerolínea, avión, ruta, altura, velocidad y hacia dónde mirar. "
            "Tarda unos segundos; deja el globo apuntando a ese avión.",
            lambda _a: ab.overhead(),
        ),
        ClientTool(
            "mostrar_en_globo",
            "Abre God's Eye View (el globo 3D) en su propia ventana mostrando un "
            "lugar (\"Cuenca\", \"Quito\", \"Tokio\"). Con lugar vacío muestra el "
            "último avión consultado.",
            lambda a: ab.globe(str(a.get("lugar") or "")),
            _obj(lugar=_str("Lugar; vacío = el avión de antes")),
        ),
        ClientTool(
            "progreso_gimnasio",
            "¿Funciona el gimnasio mental? Su progreso en los ejercicios y si mejora "
            "en la prueba de control no entrenada (con intervalo de confianza).",
            lambda _a: ab.gym_report(),
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
