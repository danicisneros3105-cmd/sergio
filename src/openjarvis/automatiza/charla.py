"""Automatizar as a conversation: the owner says what he wants done on its own.

The owner (28 Oct 2026): «el apartado de automatizaciones hazlo mejor, tipo
chat, pero mejor y sin caer en solo Instagram y YouTube». He writes («haz 2
shorts al día de datos curiosos para TikTok y YouTube», «¿de qué hago videos
esta semana?», «búscame clientes», «¿cómo va todo?») and Sergio answers with
what it understood and, for anything that changes something, a card with a
button. Reading is done at once; creating, posting, searching or stopping
waits for that tap. Nothing here sends a message, posts or trades without it.

Where Sergio can post by itself (official APIs): YouTube and Instagram. For
TikTok, Facebook, LinkedIn and X the video is made and its package (file,
title, description, hashtags) waits in «Listos para publicar» for the owner
to upload: their posting APIs need an app review that a personal Sergio does
not have, and that is said plainly instead of pretending.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

AUTO_POST = ("youtube", "instagram")  # official APIs Sergio uses
MANUAL_POST = ("tiktok", "facebook", "linkedin", "x")  # the package waits for the owner
PLATFORM_WORDS = {
    "youtube": ("youtube", "shorts", "yt"),
    "instagram": ("instagram", "reels", "insta", "ig"),
    "tiktok": ("tiktok", "tik tok"),
    "facebook": ("facebook", "fb"),
    "linkedin": ("linkedin",),
    "x": ("twitter", " x "),
}
INTENTS = (
    "canal",
    "tendencias",
    "oportunidades",
    "respuestas",
    "trading",
    "estado",
    "estabilidad",
    "ayuda",
)
NUMBERS = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
}

HELP = (
    "Puedo dejar trabajando solo, señor: canales de video (YouTube e Instagram publican "
    "solos; TikTok, Facebook, LinkedIn y X quedan listos para que usted los suba), ideas "
    "de videos con lo que la gente busca hoy, clientes y empleos con su borrador, "
    "respuestas a comentarios que usted aprueba, el trading en papel y el estado de todo. "
    "Dígame qué quiere que pase sin usted."
)


def plain(text: str) -> str:
    text = (
        unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    )
    return " " + " ".join(re.sub(r"[^a-z0-9 ]+", " ", text).split()) + " "


def platforms(text: str) -> List[str]:
    said = plain(text)
    return [
        p
        for p, words in PLATFORM_WORDS.items()
        if any(f" {w.strip()} " in said for w in words)
    ]


def per_day(text: str) -> int:
    """«2 al día», «tres diarios», «cada 8 horas» → videos per day (1–6)."""
    said = plain(text)
    m = re.search(
        r" (\d+|un|una|uno|dos|tres|cuatro|cinco|seis) (?:videos? |shorts? |reels? |clips? )?"
        r"(?:al dia|por dia|diarios?|cada dia)",
        said,
    )
    if m:
        n = NUMBERS.get(m.group(1)) or int(m.group(1))
        return max(1, min(6, n))
    m = re.search(r" cada (\d+) horas? ", said)
    if m:
        return max(1, min(6, round(24 / max(1, int(m.group(1))))))
    return 1 if " diario " in said or " cada dia " in said else 3


def topic(text: str) -> str:
    """What the channel is about: what follows «de», «sobre» or «acerca de»."""
    m = re.search(r"(?:\bsobre\b|\bacerca de\b|\bde\b)\s+(.+)", text, re.I)
    found = (m.group(1) if m else text).strip(" .")
    found = re.split(
        r"\s+(?:para|en)\s+(?:youtube|instagram|tiktok|facebook|linkedin|x|twitter)\b",
        found,
        flags=re.I,
    )[0]
    found = re.sub(
        r"\b(al d[ií]a|por d[ií]a|diarios?|cada \d+ horas?)\b", "", found, flags=re.I
    )
    return " ".join(found.split())[:120]


def classify(text: str, ask: Optional[Callable[..., str]] = None) -> str:
    """The intent: plain words first (instant), a model only when unclear."""
    said = plain(text)
    rules = (
        (
            "tendencias",
            (
                " tendencia",
                " trending",
                " de moda",
                " viral",
                " que hago",
                " de que hago",
                " ideas de video",
                " ideas para video",
                " que esta pegando",
                " mercado",
            ),
        ),
        (
            "oportunidades",
            (" cliente", " empleo", " trabajo", " freelance", " propuesta", " vacante"),
        ),
        ("respuestas", (" comentario", " respuestas", " responde")),
        ("trading", (" trading", " bolsa", " acciones", " invertir", " inversion")),
        ("estabilidad", (" falla", " error", " estabilidad", " reparar", " lento")),
        (
            "estado",
            (" como va", " estado", " en marcha", " resumen", " que hay", " que tengo"),
        ),
        (
            "canal",
            (
                " canal",
                " shorts",
                " reels",
                " publica",
                " publicar",
                " sube ",
                " videos al dia",
                " al dia",
                " cada dia",
                " tiktok",
                " diario",
                " youtube",
                " instagram",
                " facebook",
                " linkedin",
                " twitter",
            ),
        ),
    )
    for intent, words in rules:
        if any(w in said for w in words):
            return intent
    if ask is None:
        return "ayuda"
    try:
        raw = ask(
            "Classify this request to an automation assistant into ONE of: "
            f"{', '.join(INTENTS)}. Request: {text!r}. Answer only the word.",
        )
        word = plain(raw).strip().split(" ")[0]
        return word if word in INTENTS else "ayuda"
    except Exception:  # noqa: BLE001
        return "ayuda"


def _card(
    titulo: str,
    detalle: str = "",
    boton: Optional[Dict[str, Any]] = None,
    tipo: str = "accion",
) -> Dict[str, Any]:
    return {"tipo": tipo, "titulo": titulo, "detalle": detalle, "boton": boton}


def answer(
    text: str,
    *,
    ask: Optional[Callable[..., str]] = None,
    pais: str = "EC",
    readers: Optional[Dict[str, Callable[..., Any]]] = None,
) -> Dict[str, Any]:
    """Sergio's reply: what it understood, what it read, and cards to act."""
    text = " ".join((text or "").split())[:600]
    if not text:
        return {"texto": HELP, "tarjetas": [], "intencion": "ayuda"}
    r = readers or {}
    intent = classify(text, ask)
    if intent == "canal":
        where = platforms(text) or ["youtube"]
        auto = [p for p in where if p in AUTO_POST]
        manual = [p for p in where if p in MANUAL_POST]
        n, about = per_day(text), topic(text)
        if not about or len(about) < 3:
            return {
                "texto": "¿De qué tema quiere el canal, señor? Por ejemplo: «2 shorts al día de datos curiosos "
                "de historia para TikTok y YouTube».",
                "tarjetas": [],
                "intencion": intent,
            }
        names = {
            "youtube": "YouTube",
            "instagram": "Instagram",
            "tiktok": "TikTok",
            "facebook": "Facebook",
            "linkedin": "LinkedIn",
            "x": "X",
        }
        parts = []
        if auto:
            parts.append(f"publica solo en {' y '.join(names[p] for p in auto)}")
        if manual:
            parts.append(
                f"para {' y '.join(names[p] for p in manual)} le dejo cada video listo para subir"
            )
        texto = (
            f"Entendido: {n} video{'s' if n > 1 else ''} al día sobre «{about}»; "
            + "; ".join(parts)
            + f". Tope: {r.get('tope', lambda: 3)()} publicaciones al día. ¿Lo creo?"
        )
        boton = {
            "etiqueta": "Crear canal",
            "metodo": "POST",
            "ruta": "/canal",
            "cuerpo": {
                "idea": about,
                "por_dia": n,
                "formato": "9:16",
                "auto": bool(auto),
                "publicar_en": auto,
            },
        }
        return {
            "texto": texto,
            "intencion": intent,
            "tarjetas": [
                _card(
                    f"Canal: {about}",
                    f"{n} al día · " + ", ".join(names[p] for p in where),
                    boton,
                )
            ],
        }
    if intent == "tendencias":
        niche = re.sub(
            r"(?i)\b(tendencias?|ideas?|de|para|videos?|que|hago|sobre|hoy|esta semana)\b",
            " ",
            text,
        )
        niche = " ".join(niche.split())[:80]
        try:
            got = r.get("ideas", _ideas)(pais, niche)
        except Exception as exc:  # noqa: BLE001
            return {
                "texto": f"No pude leer las tendencias ahora: {exc}",
                "tarjetas": [],
                "intencion": intent,
            }
        ideas = got.get("ideas") or []
        if not ideas:
            return {
                "texto": got.get("aviso")
                or "Hoy no encontré tendencias que encajen; pruebe con otro tema.",
                "tarjetas": [],
                "intencion": intent,
            }
        fuentes = ", ".join(got.get("fuentes") or [])
        cards = [
            _card(
                i["titulo"],
                f"{i['gancho']} — {i['por_que']}",
                {
                    "etiqueta": "Hacer este video",
                    "metodo": "POST",
                    "ruta": "/tendencias/video",
                    "cuerpo": i,
                },
                tipo="idea",
            )
            for i in ideas
        ]
        return {
            "texto": f"Esto es lo que la gente busca y ve hoy ({fuentes}), convertido en videos:",
            "tarjetas": cards,
            "intencion": intent,
        }
    if intent == "oportunidades":
        rows = r.get("oportunidades", lambda: [])()[:5]
        cards = [
            _card(
                x.get("titulo") or "",
                f"{x.get('empresa') or ''} · {x.get('puntos', '')} puntos",
                tipo="lista",
            )
            for x in rows
        ]
        cards.append(
            _card(
                "Buscar ahora",
                "Clientes y empleos nuevos con su borrador (nada se envía solo).",
                {
                    "etiqueta": "Buscar",
                    "metodo": "POST",
                    "ruta": "/oportunidades/buscar",
                    "cuerpo": {},
                },
            )
        )
        return {
            "texto": "Lo mejor que tengo guardado, señor. ¿Busco más?"
            if rows
            else "Aún no he buscado. ¿Empiezo?",
            "tarjetas": cards,
            "intencion": intent,
        }
    if intent == "respuestas":
        n = int(r.get("respuestas", lambda: 0)())
        return {
            "texto": f"Tiene {n} respuesta{'s' if n != 1 else ''} esperando su visto bueno."
            if n
            else "No hay respuestas pendientes.",
            "intencion": intent,
            "tarjetas": [
                _card(
                    "Redactar respuestas nuevas",
                    "Leo los comentarios recientes y redacto; usted aprueba.",
                    {
                        "etiqueta": "Redactar",
                        "metodo": "POST",
                        "ruta": "/respuestas/redactar",
                        "cuerpo": {},
                    },
                )
            ],
        }
    if intent == "trading":
        st = r.get("trading", lambda: {})()
        stop = any(
            w in plain(text)
            for w in (" para ", " deten", " detener", " apaga", " stop ")
        )
        estado = (
            "detenido"
            if st.get("detenido")
            else ("activo" if st.get("activo") else "apagado")
        )
        modo = "dinero real" if st.get("real") and st.get("dinero_real") else "papel"
        cards = []
        if stop:
            cards.append(
                _card(
                    "Detener el trading",
                    "Se para al instante y no vuelve hasta que usted lo reanude.",
                    {
                        "etiqueta": "Detener",
                        "metodo": "POST",
                        "ruta": "/trading/detener",
                        "cuerpo": {},
                    },
                )
            )
        return {
            "texto": f"El trading está {estado}, en {modo}. Nunca le prometo ganancias.",
            "tarjetas": cards,
            "intencion": intent,
        }
    if intent == "estabilidad":
        items = r.get("estabilidad", lambda: [])()
        bad = [c for c in items if c.get("estado") != "ok"]
        return {
            "texto": "Todo responde bien."
            if not bad
            else "Esto necesita atención: "
            + "; ".join(f"{c['nombre']}: {c['detalle']}" for c in bad[:4]),
            "intencion": intent,
            "tarjetas": [
                _card(
                    "Reparar",
                    "Arreglo lo que se puede sin tocar videos en curso.",
                    {
                        "etiqueta": "Reparar",
                        "metodo": "POST",
                        "ruta": "/estabilidad/reparar",
                        "cuerpo": {},
                    },
                )
            ]
            if bad
            else [],
        }
    if intent == "estado":
        st = r.get("estado", lambda: {})()
        prog = st.get("programados") or []
        canales = st.get("canales") or {}
        bits = [
            f"{len(prog)} canal{'es' if len(prog) != 1 else ''} programado{'s' if len(prog) != 1 else ''}",
            f"YouTube {'conectado' if (canales.get('youtube') or {}).get('conectado') else 'sin conectar'}",
            f"Instagram {'conectado' if (canales.get('instagram') or {}).get('conectado') else 'sin conectar'}",
            f"{(st.get('oportunidades') or {}).get('total', 0)} oportunidades guardadas",
            f"trading {'activo' if (st.get('trading') or {}).get('activo') else 'apagado'}",
        ]
        return {
            "texto": "En marcha: " + ", ".join(bits) + ".",
            "tarjetas": [],
            "intencion": intent,
        }
    return {"texto": HELP, "tarjetas": [], "intencion": "ayuda"}


def _ideas(pais: str, niche: str) -> Dict[str, Any]:
    from openjarvis.automatiza import tendencias

    return tendencias.ideas(pais, niche)


def order(idea: Dict[str, Any]) -> Dict[str, Any]:
    """The video job for a trend idea (its genre picks the style)."""
    from openjarvis.video_essay import genres

    genre = str(idea.get("genero") or "")
    style = genres.GENRES[genre].style if genre in genres.GENRES else ""
    long = idea.get("formato") == "long"
    signal = idea.get("senal") or {}
    return {
        "mode": "basic",
        "prompt": (
            f"{idea.get('titulo', '')}. Gancho (primera frase): «{idea.get('gancho', '')}». "
            f"Tendencia real: {signal.get('tema', '')} ({signal.get('fuente', '')}). "
            "Cuenta solo hechos comprobables."
        ),
        "topic": "",
        "script": "",
        "reference": "",
        "style": style,
        "seconds": 300.0 if long else 50.0,
        "aspect": "16:9" if long else "9:16",
        "clips": "",
        "music": "",
        "ai_video": False,
        "web_clips": True,
    }


__all__ = [
    "AUTO_POST",
    "HELP",
    "MANUAL_POST",
    "answer",
    "classify",
    "order",
    "per_day",
    "platforms",
    "topic",
]
