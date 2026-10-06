"""What the coach does, one function per job (each returns checked JSON)."""

from __future__ import annotations

import json
from typing import Any

from openjarvis.coach.brain import ask, knowledge

SERGIO = (
    "Eres Sergio, el asistente personal del usuario (lo llamas «señor» si es su "
    "dueño). Escribes en español neutro y claro, con frases cortas. Eres experto "
    "y honesto: si algo no se sabe o no hay evidencia, lo dices. Nunca inventes "
    "datos del usuario."
)


def _dump(value: Any, limit: int = 12000) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


def _need(data: Any, *keys: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Se esperaba un objeto JSON")
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValueError("Faltan campos: " + ", ".join(missing))
    return data


def _list(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


# -- profile ------------------------------------------------------------------
def update_profile(context: dict[str, Any], previous: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
    """The key profile update (2-3 times a week): everything Sergio knows ->
    who the user is, what they want and how to adapt to them."""
    prompt = f"""{SERGIO}
Tarea: actualizar el PERFIL del usuario a partir de todo lo que sabes de él.
Perfil anterior: {_dump(previous or {})}
Datos nuevos (gimnasio mental, horario de uso, salud, aprendizaje, temas de
conversación, recordatorios): {_dump(context)}

Devuelve SOLO JSON:
{{"resumen": "3-5 frases sobre quién es y cómo está ahora",
 "rasgos": ["rasgos observados con evidencia, p. ej. 'rinde mejor por la mañana'"],
 "intereses": ["..."], "objetivos": ["..."],
 "horario": {{"mejores_horas": ["HH:MM-HH:MM"], "dias_activos": ["lunes", "..."]}},
 "aprendizaje": {{"estilo": "...", "ritmo": "lento|normal|rapido"}},
 "gimnasio": {{"prioridad": ["habilidades a reforzar"], "dificultad": -1|0|1, "preferidos": ["tipos de ejercicio"]}},
 "salud": {{"foco": ["..."]}},
 "comunicacion": {{"detalle": "breve|normal|detallado", "humor": "poco|normal|mucho", "nota": "cómo prefiere que le hablen"}},
 "ajustes": ["cambios concretos que Sergio aplicará en su comportamiento"],
 "cambios": ["qué cambió respecto al perfil anterior"]}}
Basa cada rasgo en los datos; si no hay datos de algo, deja la lista vacía.
En "comunicacion" y "dificultad" usa "normal" / 0 salvo que los datos muestren
otra cosa. En "gimnasio" usa solo nombres de "habilidades_validas" y
"ejercicios_validos" si vienen en los datos."""
    data = ask(prompt, **kw)
    return _list(_need(data, "resumen"), "rasgos", "intereses", "objetivos", "ajustes", "cambios")


# -- learning -------------------------------------------------------------------
def make_plan(goal: str, kind: str, profile: dict[str, Any], free_slots: list[str], **kw: Any) -> dict[str, Any]:
    """Research the skill (Google Search) and plan the practice for THIS user."""
    topics = ["aprendizaje"] + (["idiomas"] if kind == "idioma" else [])
    prompt = f"""{SERGIO}
{knowledge(*topics)}

El usuario quiere aprender/mejorar: «{goal}» (tipo: {kind}).
Perfil del usuario: {_dump(profile, 4000)}
Huecos en los que suele estar disponible: {_dump(free_slots)}

1) Investiga a fondo en la web cómo se aprende esto bien (fuentes de calidad:
   expertos, universidades, manuales reconocidos). 2) Diseña un plan para ESTA
   persona. Devuelve SOLO JSON (sin texto fuera):
{{"titulo": "...", "resumen": "qué lograrás y en cuánto tiempo",
 "investigacion": ["hallazgos clave, concretos"],
 "subhabilidades": [{{"nombre": "...", "orden": 1, "como_se_practica": "..."}}],
 "metricas": [{{"nombre": "...", "unidad": "...", "mejor": "alto|bajo", "como_medir": "..."}}],
 "errores_comunes": ["..."],
 "sesiones": [{{"dia": 0, "minutos": 20, "objetivo": "...", "pasos": ["..."], "video": true|false}}],
 "nivel_inicial": "cómo evaluar el punto de partida",
 "registro": {{"formal": "...", "informal": "..."}}}}
Incluye 10-14 sesiones para las próximas 2-3 semanas (dia = días desde hoy),
cortas y con repaso espaciado. "video": true en las sesiones donde grabarle y
corregirle en video ayude (habilidades físicas o de pronunciación)."""
    data = ask(prompt, search=True, deep=True, **kw)
    return _list(_need(data, "titulo", "sesiones"), "investigacion", "subhabilidades", "metricas", "errores_comunes")


def next_lesson(goal: dict[str, Any], profile: dict[str, Any], **kw: Any) -> dict[str, Any]:
    """The next session, made for the user's level, errors and interests."""
    kind = goal.get("tipo", "habilidad")
    topics = ["aprendizaje"] + (["idiomas"] if kind == "idioma" else [])
    prompt = f"""{SERGIO}
{knowledge(*topics)}

Meta y progreso del usuario: {_dump(goal, 8000)}
Perfil: {_dump(profile, 3000)}

Prepara la PRÓXIMA sesión, adaptada a sus errores recientes y a sus métricas.
Devuelve SOLO JSON:
{{"titulo": "...", "minutos": 20, "objetivo": "...",
 "calentamiento": ["repaso de lo anterior"],
 "contenido": [{{"tipo": "explicacion|ejemplo|ejercicio|dialogo|vocabulario|practica", "texto": "...", "respuesta": "si aplica"}}],
 "evaluacion": [{{"pregunta": "...", "respuesta": "..."}}],
 "medir": ["qué métricas anotar al final"], "consejo": "..."}}
Para idiomas: incluye registro formal e informal/coloquial cuando venga al caso."""
    return _list(_need(ask(prompt, **kw), "titulo", "contenido"), "evaluacion", "medir", "calentamiento")


def assess(goal: dict[str, Any], results: str, **kw: Any) -> dict[str, Any]:
    """What the user reports (or answered) -> metrics, errors and feedback."""
    prompt = f"""{SERGIO}
{knowledge("aprendizaje")}

Meta y plan: {_dump(goal, 6000)}
Lo que hizo el usuario en la sesión / sus respuestas: {results}

Evalúa como un coach exigente pero amable. Devuelve SOLO JSON:
{{"metricas": {{"nombre de la métrica": número}},
 "bien": ["lo que hizo bien, concreto"], "mal": ["errores concretos"],
 "errores_tipo": {{"tipo": cuántas_veces}},
 "nivel": "estimación del nivel actual", "dificultad": -1|0|1,
 "feedback": "2-3 frases, directas, con la corrección más importante"}}"""
    return _list(_need(ask(prompt, **kw), "feedback"), "bien", "mal")


def review_video(video: bytes, mime: str, goal: str, focus: str = "", **kw: Any) -> dict[str, Any]:
    """Watch a practice video and mark what is right (green) and wrong (red).

    Each mark has the time and where in the picture (x, y, r as fractions of
    the frame) so the companion can circle it on the video."""
    prompt = f"""{SERGIO}
{knowledge("aprendizaje")}

Este video es una práctica del usuario. Meta: «{goal}». {('Fíjate sobre todo en: ' + focus) if focus else ''}
Analízalo fotograma a fotograma como un coach experto. Devuelve SOLO JSON:
{{"resumen": "2-3 frases", "nota": 0-10,
 "marcas": [{{"t": segundos, "duracion": segundos, "x": 0-1, "y": 0-1, "r": 0.03-0.3,
             "bien": true|false, "texto": "qué pasa ahí (máx. 8 palabras)"}}],
 "metricas": {{"nombre": número}},
 "corregir": ["la corrección más importante primero"],
 "siguiente": "qué practicar en la próxima sesión"}}
x, y: centro de la zona (0,0 arriba a la izquierda), r: radio relativo al ancho.
Marca 3-10 momentos, con verdes y rojos, solo lo que realmente se ve."""

    def check(data: Any) -> dict[str, Any]:
        data = _list(_need(data, "resumen"), "marcas", "corregir")
        clean = []
        for m in data["marcas"]:
            try:
                clean.append({
                    "t": max(0.0, float(m["t"])), "duracion": min(4.0, max(0.6, float(m.get("duracion") or 1.5))),
                    "x": min(1.0, max(0.0, float(m["x"]))), "y": min(1.0, max(0.0, float(m["y"]))),
                    "r": min(0.3, max(0.03, float(m.get("r") or 0.08))),
                    "bien": bool(m.get("bien")), "texto": str(m.get("texto") or "")[:60],
                })  # fmt: skip
            except (KeyError, TypeError, ValueError):
                continue
        data["marcas"] = sorted(clean, key=lambda m: m["t"])
        return data

    return ask(prompt, media=[(video, mime)], check=check, **kw)


def read_school(image: bytes, mime: str = "image/jpeg", **kw: Any) -> dict[str, Any]:
    """A screenshot of the school platform -> pending homework and exams."""
    prompt = f"""{SERGIO}
Es una captura de la plataforma escolar del usuario. Extrae SOLO lo que se ve.
Devuelve SOLO JSON:
{{"tareas": [{{"materia": "...", "titulo": "...", "fecha": "AAAA-MM-DD o ''", "detalle": "..."}}],
 "examenes": [{{"materia": "...", "fecha": "AAAA-MM-DD o ''", "temas": ["..."]}}],
 "otros": ["avisos importantes"]}}"""
    return _list(_need(ask(prompt, media=[(image, mime)], **kw), "tareas"), "tareas", "examenes", "otros")


# -- health ------------------------------------------------------------------------
def health_report(data: dict[str, Any], **kw: Any) -> dict[str, Any]:
    """Questionnaire + watch/manual data (+ metrics computed locally) ->
    a health profile, risks, recommendations and routines."""
    prompt = f"""{SERGIO}
{knowledge("salud")}

Datos de salud del usuario (cuestionario, registros diarios, datos del reloj y
métricas ya calculadas): {_dump(data, 14000)}

Analiza en profundidad cruzando todos los datos. Devuelve SOLO JSON:
{{"resumen": "4-6 frases", "puntos_fuertes": ["..."], "a_mejorar": ["..."],
 "alertas": ["señales que merecen consulta médica (vacío si no hay)"],
 "recomendaciones": [{{"area": "sueño|actividad|nutricion|estres|sexual|otro", "accion": "concreta y medible", "por_que": "..."}}],
 "rutina": [{{"dia": "lunes", "actividad": "...", "minutos": 30}}],
 "metas": [{{"metrica": "...", "objetivo": "...", "plazo": "..."}}]}}
Prioriza 3-5 recomendaciones; nada de diagnósticos."""
    return _list(_need(ask(prompt, effort="medium", **kw), "resumen"), "alertas", "recomendaciones", "rutina", "metas")


# -- support -------------------------------------------------------------------------
RISK_WORDS = (
    "suicid", "matarme", "quitarme la vida", "no quiero vivir", "no quiero seguir viviendo",
    "hacerme daño", "cortarme", "autolesi", "desaparecer para siempre", "mejor muerto",
    "acabar con todo", "me quiero morir", "quiero morir",
)  # fmt: skip
CRISIS = (
    "Señor, lo que me cuenta es importante y no quiero que lo lleve solo. Si "
    "corre peligro ahora, llame al ECU 911. Para hablar con un psicólogo, la "
    "Línea 171, opción 6, del Ministerio de Salud es gratuita, todos los días "
    "de 7:00 a 20:00. ¿Hay alguien de confianza que pueda estar con usted "
    "ahora? Sigo aquí."
)


RISK_TIMEOUT = 15.0


def at_risk(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in RISK_WORDS)


def therapy_turn(
    messages: list[dict[str, str]], notes: list[dict[str, Any]], profile: dict[str, Any], **kw: Any
) -> dict[str, Any]:
    """One turn of the support conversation (text or voice).

    Returns the reply plus a short DAP note for the notebook, the mood and a
    risk level; risk words always get the crisis lines, whatever the model
    says."""
    last = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    prompt = f"""{SERGIO}
En este espacio actúas como un psicólogo de apoyo experto (no sustituyes a un
profesional con licencia y no diagnosticas). Cálido, sereno, sin humor negro,
sin sarcasmo. Usa escucha reflexiva y técnicas con evidencia.
{knowledge("psicologia", "psiquiatria")}

Perfil del usuario: {_dump(profile, 3000)}
Notas de sesiones anteriores (las más recientes al final): {_dump(notes[-12:], 6000)}
Conversación de hoy: {_dump(messages[-20:], 8000)}

Responde a su último mensaje. Devuelve SOLO JSON:
{{"respuesta": "lo que le dices (2-6 frases, una sola pregunta como máximo)",
 "nota": {{"datos": "qué contó", "analisis": "patrón o avance", "plan": "tarea o tema para después"}},
 "animo": -5..5, "riesgo": "ninguno|bajo|alto", "tecnica": "la técnica que usaste",
 "temas": ["temas"]}}"""
    risky = at_risk(last)
    if risky:
        # Someone at risk never waits on a busy model: 15 s, then the lines.
        import concurrent.futures

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(ask, prompt, **kw)
        try:
            data = future.result(timeout=RISK_TIMEOUT)
        except Exception:  # noqa: BLE001 — timeout or error: the safe answer
            data = {"respuesta": CRISIS, "riesgo": "alto", "nota": {}, "animo": 0, "temas": []}
        finally:
            pool.shutdown(wait=False)
    else:
        data = ask(prompt, **kw)
    data = _need(data, "respuesta")
    if risky or str(data.get("riesgo")) == "alto":
        data["riesgo"] = "alto"
        if "171" not in data["respuesta"]:
            data["respuesta"] = CRISIS + " " + str(data["respuesta"])
    return data


__all__ = [
    "CRISIS",
    "assess",
    "at_risk",
    "health_report",
    "make_plan",
    "next_lesson",
    "read_school",
    "review_video",
    "therapy_turn",
    "update_profile",
]
