"""Salud mental: a survey built from validated university scales, scored in code
and read by the AI about thirty minutes later.

It opens with three picture questions (not feeling enough, thinking too much,
wanting to fit in) and then asks the published items of free, validated scales:

* PHQ-9 (mood) and GAD-7 (anxiety), Columbia University / Kroenke, Spitzer, Williams.
* Rosenberg Self-Esteem Scale (Rosenberg, 1965, Princeton University Press).
* Ruminative Responses Scale, brooding items (Treynor, Gonzalez & Nolen-Hoeksema, 2003).
* PSWQ-3, ultra-brief Penn State Worry Questionnaire (Meyer et al., 1990; Berle et al., 2011).
* Authenticity Scale (Wood, Linley, Maltby, Baliousis & Joseph, 2008).
* UCLA 3-item Loneliness Scale (Hughes, Waite, Hawkley & Cacioppo, 2004).

Scores are sums with the published cut-offs where they exist; where a scale has
no clinical cut-off the bands are labeled as orientative. Nothing here is a
diagnosis, and a risk answer shows the crisis lines at once, never 30 minutes later.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

DELAY_SECONDS = 30 * 60

FREQ_2W = [
    "Ningún día",
    "Varios días",
    "Más de la mitad de los días",
    "Casi todos los días",
]
AGREE_4 = ["Muy en desacuerdo", "En desacuerdo", "De acuerdo", "Muy de acuerdo"]
OFTEN_4 = ["Casi nunca", "A veces", "A menudo", "Casi siempre"]
TYPICAL_5 = [
    "Nada típico de mí",
    "Poco típico de mí",
    "Algo típico de mí",
    "Bastante típico de mí",
    "Muy típico de mí",
]
DESCRIBES_7 = [
    "No me describe en absoluto",
    "No me describe",
    "Me describe poco",
    "Ni sí ni no",
    "Me describe algo",
    "Me describe",
    "Me describe muy bien",
]
UCLA_3 = ["Casi nunca", "A veces", "A menudo"]
PICTURE = ["Nunca", "A veces", "A menudo", "Casi siempre"]


@dataclass(frozen=True)
class Scale:
    key: str
    label: str
    stem: str
    options: List[str]
    first: int  # value of the first option (0 or 1)
    items: List[Tuple[str, str]]  # (id, text)
    reverse: Tuple[str, ...] = ()
    # (upper bound inclusive, band key, words); last bound is the maximum score.
    bands: List[Tuple[int, str, str]] = field(default_factory=list)
    higher_is_better: bool = False
    orientative: bool = False
    source: str = ""
    url: str = ""
    subscales: Dict[str, Tuple[str, Tuple[str, ...]]] = field(default_factory=dict)


PICTURES = [
    {
        "id": "pic_suficiente",
        "image": "no-suficiente",
        "alt": "Un espejo roto frente a una silueta con sombrero",
        "text": "En las últimas semanas, ¿con qué frecuencia ha sentido que no es suficiente o le ha costado quererse?",
        "domain": "autoestima",
    },
    {
        "id": "pic_pensar",
        "image": "pensar-demasiado",
        "alt": "Una figura enterrada bajo montones de periódicos",
        "text": "¿Con qué frecuencia le da vueltas a los problemas, uno encima de otro, sin llegar a nada?",
        "domain": "rumiación",
    },
    {
        "id": "pic_encajar",
        "image": "encajar",
        "alt": "Un hombre con máscara de león rodeado de leones rojos",
        "text": "¿Con qué frecuencia actúa como alguien que no es para encajar con los demás?",
        "domain": "autenticidad",
    },
]

SCALES: List[Scale] = [
    Scale(
        key="phq9",
        label="Ánimo",
        stem="Durante las últimas 2 semanas, ¿con qué frecuencia le ha molestado lo siguiente?",
        options=FREQ_2W,
        first=0,
        items=[
            ("phq9_1", "Poco interés o placer en hacer cosas"),
            ("phq9_2", "Sentirse decaído, deprimido o sin esperanza"),
            (
                "phq9_3",
                "Dificultad para dormirse o mantenerse dormido, o dormir demasiado",
            ),
            ("phq9_4", "Sentirse cansado o con poca energía"),
            ("phq9_5", "Poco apetito o comer en exceso"),
            (
                "phq9_6",
                "Sentirse mal consigo mismo, que es un fracaso o que ha quedado mal consigo mismo o con su familia",
            ),
            (
                "phq9_7",
                "Dificultad para concentrarse en cosas como leer el periódico o ver la televisión",
            ),
            (
                "phq9_8",
                "Moverse o hablar tan despacio que otros lo notarían, o lo contrario: estar tan inquieto que se mueve mucho más de lo normal",
            ),
            (
                "phq9_9",
                "Pensar que estaría mejor muerto o en hacerse daño de alguna manera",
            ),
        ],
        bands=[
            (4, "minimo", "mínimo"),
            (9, "leve", "leve"),
            (14, "moderado", "moderado"),
            (19, "moderado_grave", "moderadamente grave"),
            (27, "grave", "grave"),
        ],
        source="PHQ-9. Kroenke, Spitzer y Williams (2001), Journal of General Internal Medicine; desarrollado en la Universidad de Columbia. Uso libre.",
        url="https://doi.org/10.1046/j.1525-1497.2001.016009606.x",
    ),
    Scale(
        key="gad7",
        label="Ansiedad",
        stem="Durante las últimas 2 semanas, ¿con qué frecuencia le ha molestado lo siguiente?",
        options=FREQ_2W,
        first=0,
        items=[
            ("gad7_1", "Sentirse nervioso, ansioso o con los nervios de punta"),
            (
                "gad7_2",
                "No poder dejar de preocuparse o no poder controlar la preocupación",
            ),
            ("gad7_3", "Preocuparse demasiado por cosas diferentes"),
            ("gad7_4", "Dificultad para relajarse"),
            ("gad7_5", "Estar tan inquieto que le cuesta quedarse quieto"),
            ("gad7_6", "Molestarse o irritarse con facilidad"),
            ("gad7_7", "Sentir miedo de que algo terrible pudiera pasar"),
        ],
        bands=[
            (4, "minimo", "mínima"),
            (9, "leve", "leve"),
            (14, "moderado", "moderada"),
            (21, "grave", "grave"),
        ],
        source="GAD-7. Spitzer, Kroenke, Williams y Löwe (2006), Archives of Internal Medicine. Uso libre.",
        url="https://doi.org/10.1001/archinte.166.10.1092",
    ),
    Scale(
        key="rses",
        label="Autoestima",
        stem="¿Qué tan de acuerdo está con cada frase?",
        options=AGREE_4,
        first=1,
        items=[
            (
                "rses_1",
                "Siento que soy una persona digna de aprecio, al menos tanto como los demás.",
            ),
            ("rses_2", "Creo que tengo varias cualidades buenas."),
            (
                "rses_3",
                "Soy capaz de hacer las cosas tan bien como la mayoría de la gente.",
            ),
            ("rses_4", "Tengo una actitud positiva hacia mí mismo."),
            ("rses_5", "En general, estoy satisfecho conmigo mismo."),
            ("rses_6", "Siento que no tengo mucho de lo que estar orgulloso."),
            ("rses_7", "En general, me inclino a pensar que soy un fracasado."),
            ("rses_8", "Me gustaría poder sentir más respeto por mí mismo."),
            ("rses_9", "Hay veces que realmente pienso que no sirvo para nada."),
            ("rses_10", "A veces creo que no soy buena persona."),
        ],
        reverse=("rses_6", "rses_7", "rses_8", "rses_9", "rses_10"),
        bands=[(25, "baja", "baja"), (29, "media", "media"), (40, "alta", "alta")],
        higher_is_better=True,
        source="Escala de Autoestima de Rosenberg (1965), Princeton University Press; versión española de Vázquez, Jiménez y Vázquez-Morejón (2004), Apuntes de Psicología.",
    ),
    Scale(
        key="rrsb",
        label="Rumiación",
        stem="Cuando se siente triste o decaído, ¿con qué frecuencia le pasa esto?",
        options=OFTEN_4,
        first=1,
        items=[
            ("rrsb_1", "Piensa: «¿Qué he hecho yo para merecer esto?»"),
            ("rrsb_2", "Piensa: «¿Por qué siempre reacciono así?»"),
            (
                "rrsb_3",
                "Piensa en algo que pasó hace poco y desea que hubiera salido mejor",
            ),
            ("rrsb_4", "Piensa: «¿Por qué tengo problemas que los demás no tienen?»"),
            ("rrsb_5", "Piensa: «¿Por qué no sé manejar mejor las cosas?»"),
        ],
        bands=[(9, "baja", "baja"), (13, "media", "media"), (20, "alta", "alta")],
        orientative=True,
        source="Escala de Respuestas Rumiativas, ítems de «brooding». Treynor, Gonzalez y Nolen-Hoeksema (2003), Cognitive Therapy and Research.",
        url="https://doi.org/10.1023/A:1023910315561",
    ),
    Scale(
        key="pswq3",
        label="Preocupación",
        stem="¿Qué tan típica de usted es cada frase?",
        options=TYPICAL_5,
        first=1,
        items=[
            ("pswq3_1", "Mis preocupaciones me desbordan."),
            ("pswq3_2", "Muchas situaciones me hacen preocuparme."),
            (
                "pswq3_3",
                "Sé que no debería preocuparme por las cosas, pero no puedo evitarlo.",
            ),
        ],
        bands=[(7, "baja", "baja"), (11, "media", "media"), (15, "alta", "alta")],
        orientative=True,
        source="PSWQ-3, versión ultrabreve del Cuestionario de Preocupación de Penn State. Meyer, Miller, Metzger y Borkovec (1990); Berle et al. (2011).",
        url="https://doi.org/10.1016/0005-7967(90)90135-6",
    ),
    Scale(
        key="auth",
        label="Autenticidad",
        stem="¿Cuánto le describe cada frase?",
        options=DESCRIBES_7,
        first=1,
        items=[
            ("auth_1", "Creo que es mejor ser uno mismo que ser popular."),
            ("auth_2", "No sé lo que de verdad siento por dentro."),
            ("auth_3", "Los demás me influyen mucho."),
            ("auth_4", "Normalmente hago lo que los demás me dicen que haga."),
            ("auth_5", "Siempre defiendo aquello en lo que creo."),
            ("auth_6", "Siento que no me conozco muy bien."),
            (
                "auth_7",
                "Siento que siempre tengo que hacer lo que los demás esperan de mí.",
            ),
            ("auth_8", "Soy fiel a mí mismo en la mayoría de las situaciones."),
            ("auth_9", "Me siento desconectado de quien soy de verdad."),
            ("auth_10", "Las opiniones de los demás me influyen mucho."),
            ("auth_11", "Vivo de acuerdo con mis valores y creencias."),
            ("auth_12", "Me siento extraño a mí mismo."),
        ],
        subscales={
            "vivir": (
                "Vivir según uno mismo",
                ("auth_1", "auth_5", "auth_8", "auth_11"),
            ),
            "influencia": (
                "Aceptar la influencia de otros",
                ("auth_3", "auth_4", "auth_7", "auth_10"),
            ),
            "alienacion": (
                "Desconexión de uno mismo",
                ("auth_2", "auth_6", "auth_9", "auth_12"),
            ),
        },
        orientative=True,
        source="Escala de Autenticidad. Wood, Linley, Maltby, Baliousis y Joseph (2008), Journal of Counseling Psychology. Traducción de trabajo, no la versión española validada.",
        url="https://doi.org/10.1037/0022-0167.55.3.385",
    ),
    Scale(
        key="ucla3",
        label="Soledad",
        stem="¿Con qué frecuencia le pasa esto?",
        options=UCLA_3,
        first=1,
        items=[
            ("ucla3_1", "Siente que le falta compañía."),
            ("ucla3_2", "Se siente excluido."),
            ("ucla3_3", "Se siente aislado de los demás."),
        ],
        bands=[(5, "baja", "sin soledad notable"), (9, "alta", "soledad")],
        source="Escala de Soledad UCLA de 3 ítems. Hughes, Waite, Hawkley y Cacioppo (2004), Research on Aging; Universidad de Chicago.",
        url="https://doi.org/10.1177/0164027504268574",
    ),
]

OPEN = [
    ("open_suficiente", "Cuando siente que no es suficiente, ¿qué se dice a sí mismo?"),
    ("open_vueltas", "¿Qué problemas le dan más vueltas en la cabeza ahora mismo?"),
    (
        "open_encajar",
        "¿En qué situaciones siente que tiene que ser otra persona para encajar?",
    ),
    ("open_cambio", "¿Qué le gustaría que fuera distinto dentro de un mes?"),
]

BY_KEY = {s.key: s for s in SCALES}
ITEM_SCALE = {item_id: s for s in SCALES for item_id, _ in s.items}
PICTURE_IDS = {p["id"] for p in PICTURES}
OPEN_IDS = {k for k, _ in OPEN}

# The short survey uses the published two-item screeners that come from the same
# scales (the same items, so the answers are compatible with the long one).
PHQ2 = Scale(
    key="phq2",
    label="Ánimo",
    stem=BY_KEY["phq9"].stem,
    options=FREQ_2W,
    first=0,
    items=BY_KEY["phq9"].items[:2],
    bands=[
        (2, "minimo", "por debajo del corte"),
        (6, "positivo", "en el corte o por encima (3 o más)"),
    ],
    source="PHQ-2. Kroenke, Spitzer y Williams (2003), Medical Care. Cribado de dos ítems: un resultado de 3 o más pide hablar con un profesional, no es un diagnóstico.",
    url="https://doi.org/10.1097/01.MLR.0000093487.78664.3C",
)
GAD2 = Scale(
    key="gad2",
    label="Ansiedad",
    stem=BY_KEY["gad7"].stem,
    options=FREQ_2W,
    first=0,
    items=BY_KEY["gad7"].items[:2],
    bands=[
        (2, "minimo", "por debajo del corte"),
        (6, "positivo", "en el corte o por encima (3 o más)"),
    ],
    source="GAD-2. Kroenke et al. (2007), Annals of Internal Medicine. Cribado de dos ítems: un resultado de 3 o más pide hablar con un profesional, no es un diagnóstico.",
    url="https://doi.org/10.7326/0003-4819-146-5-200703060-00004",
)
WHO5 = Scale(
    key="who5",
    label="Bienestar",
    stem="Durante las últimas dos semanas…",
    options=[
        "En ningún momento",
        "De vez en cuando",
        "Menos de la mitad del tiempo",
        "Más de la mitad del tiempo",
        "La mayor parte del tiempo",
        "Todo el tiempo",
    ],
    first=0,
    items=[
        ("who5_1", "Me he sentido alegre y de buen humor"),
        ("who5_2", "Me he sentido tranquilo y relajado"),
        ("who5_3", "Me he sentido activo y enérgico"),
        ("who5_4", "Me he despertado fresco y descansado"),
        ("who5_5", "Mi vida diaria ha estado llena de cosas que me interesan"),
    ],
    # Raw 0-25 (×4 = %). ≤ 7 (28 %) suggests depression; ≤ 12 (50 %) low wellbeing.
    bands=[
        (7, "baja", "bajo: conviene hablar con un profesional"),
        (12, "media", "por debajo de lo deseable"),
        (25, "alta", "bueno"),
    ],
    higher_is_better=True,
    source="WHO-5, Índice de Bienestar de la OMS. Topp, Østergaard, Søndergaard y Bech (2015), Psychotherapy and Psychosomatics: 50 % o menos indica bienestar bajo; 28 % o menos, posible depresión. No es un diagnóstico.",
    url="https://doi.org/10.1159/000376585",
)
SISE = Scale(
    key="sise",
    label="Autoestima",
    stem="¿Cuánto se aplica a usted esta frase?",
    options=["Nada", "Poco", "Algo", "Bastante", "Totalmente"],
    first=1,
    items=[("sise_1", "Tengo una alta autoestima")],
    bands=[(2, "baja", "baja"), (3, "media", "media"), (5, "alta", "alta")],
    higher_is_better=True,
    orientative=True,
    source="Single-Item Self-Esteem Scale. Robins, Hendin y Trzesniewski (2001), Personality and Social Psychology Bulletin: una sola frase que se comporta como la escala de Rosenberg. Sin punto de corte clínico: orientativa.",
    url="https://doi.org/10.1177/0146167201272002",
)

# Widgets (owner, 24 Oct. 2026: «pocas preguntas que valgan más que 52»):
# each one a validated short scale on its own card, answered in seconds.
WIDGETS: Dict[str, Dict[str, Any]] = {
    "w_animo": {"label": "Ánimo", "minutes": 1, "scales": [PHQ2],
                "extra_items": {"phq2": [BY_KEY["phq9"].items[8]]}, "open": [], "widget": True},
    "w_nervios": {"label": "Nervios", "minutes": 1, "scales": [GAD2], "extra_items": {}, "open": [], "widget": True},
    "w_bienestar": {"label": "Bienestar", "minutes": 1, "scales": [WHO5], "extra_items": {}, "open": [], "widget": True},
    "w_soledad": {"label": "Compañía", "minutes": 1, "scales": [BY_KEY["ucla3"]], "extra_items": {}, "open": [],
                  "widget": True},
    "w_autoestima": {"label": "Autoestima", "minutes": 1, "scales": [SISE], "extra_items": {}, "open": [],
                     "widget": True},
}  # fmt: skip

ITEM_SCALE.update({i: sc for sc in (WHO5, SISE) for i, _ in sc.items})

VARIANTS: Dict[str, Dict[str, Any]] = {
    "corta": {
        "label": "Corta",
        "minutes": 3,
        "scales": [PHQ2, GAD2, BY_KEY["ucla3"]],
        # PHQ-9 item 9 stays in the short survey: it is the safety question.
        "extra_items": {"phq2": [BY_KEY["phq9"].items[8]]},
        "open": ["open_cambio"],
    },
    "larga": {
        "label": "Larga",
        "minutes": 12,
        "scales": list(SCALES),
        "extra_items": {},
        "open": [k for k, _ in OPEN],
    },
    **WIDGETS,
}
DEFAULT_VARIANT = "larga"


def variant_of(name: str) -> str:
    return name if name in VARIANTS else DEFAULT_VARIANT


def delay_seconds() -> int:
    try:
        return max(0, int(os.environ.get("SERGIO_MIND_DELAY", DELAY_SECONDS)))
    except ValueError:
        return DELAY_SECONDS


def definition(variant: str = DEFAULT_VARIANT) -> Dict[str, Any]:
    """The survey as the app shows it, one question per screen."""
    variant = variant_of(variant)
    plan = VARIANTS[variant]
    pictures = [
        {
            **p,
            "kind": "picture",
            "options": [{"value": i, "label": o} for i, o in enumerate(PICTURE)],
        }
        for p in PICTURES
    ]
    widget = bool(plan.get("widget"))
    sections: List[Dict[str, Any]] = (
        []
        if widget
        else [{"key": "inicio", "title": "Para empezar", "items": pictures}]
    )
    for s in plan["scales"]:
        options = [{"value": s.first + i, "label": o} for i, o in enumerate(s.options)]
        items = list(s.items) + list(plan["extra_items"].get(s.key, []))
        sections.append(
            {
                "key": s.key,
                "title": s.label,
                "stem": s.stem,
                "items": [
                    {"id": i, "kind": "choice", "text": t, "options": options}
                    for i, t in items
                ],
            }
        )
    if plan["open"]:
        sections.append(
            {
                "key": "abiertas",
                "title": "Con sus palabras",
                "items": [
                    {"id": k, "kind": "open", "text": t}
                    for k, t in OPEN
                    if k in plan["open"]
                ],
            }
        )
    return {
        "variant": variant,
        "label": plan["label"],
        "minutes": plan["minutes"],
        "sections": sections,
        "count": sum(len(sec["items"]) for sec in sections),
        "delay_minutes": round(delay_seconds() / 60),
        "sources": sources(variant),
        "variants": [
            {
                "key": k,
                "label": v["label"],
                "minutes": v["minutes"],
                "count": definition_count(k),
            }
            for k, v in VARIANTS.items()
            if not v.get("widget")
        ],
        "widget": widget,
    }


def widgets() -> List[Dict[str, Any]]:
    """The cards: a few questions each, from validated scales."""
    return [
        {"key": k, "label": v["label"], "count": definition_count(k),
         "scale": v["scales"][0].label, "cite": v["scales"][0].source}
        for k, v in WIDGETS.items()
    ]  # fmt: skip


def definition_count(variant: str) -> int:
    plan = VARIANTS[variant_of(variant)]
    return (
        (0 if plan.get("widget") else len(PICTURES))
        + sum(
            len(s.items) + len(plan["extra_items"].get(s.key, []))
            for s in plan["scales"]
        )
        + len(plan["open"])
    )


def sources(variant: str = DEFAULT_VARIANT) -> List[Dict[str, str]]:
    scales = VARIANTS[variant_of(variant)]["scales"]
    return [{"scale": s.label, "cite": s.source, "url": s.url} for s in scales]


def clean_answers(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only known questions with allowed values; open answers up to 2 000 characters."""
    out: Dict[str, Any] = {}
    for key, value in (raw or {}).items():
        if key in OPEN_IDS:
            text = " ".join(str(value or "").split())[:2000]
            if text:
                out[key] = text
            continue
        if key in PICTURE_IDS:
            lo, hi = 0, len(PICTURE) - 1
        elif key in ITEM_SCALE:
            s = ITEM_SCALE[key]
            lo, hi = s.first, s.first + len(s.options) - 1
        else:
            continue
        try:
            n = int(value)
        except (TypeError, ValueError):
            continue
        if lo <= n <= hi:
            out[key] = n
    return out


def _band(s: Scale, total: int) -> Tuple[str, str]:
    for bound, key, words in s.bands:
        if total <= bound:
            return key, words
    return s.bands[-1][1], s.bands[-1][2]


def _value(s: Scale, item: str, answers: Dict[str, Any]) -> int:
    v = int(answers[item])
    if item in s.reverse:
        v = s.first + len(s.options) - 1 - (v - s.first)
    return v


def _sub_band(total: int, low: int, high: int) -> Tuple[str, str]:
    third = (high - low + 1) / 3
    if total < low + third:
        return "baja", "baja"
    if total < low + 2 * third:
        return "media", "media"
    return "alta", "alta"


def score(answers: Dict[str, Any], variant: str = DEFAULT_VARIANT) -> Dict[str, Any]:
    """Sum every complete scale; incomplete scales say how many items are missing."""
    variant = variant_of(variant)
    scales: List[Dict[str, Any]] = []
    for s in VARIANTS[variant]["scales"]:
        ids = [i for i, _ in s.items]
        answered = [i for i in ids if i in answers]
        low = s.first * len(ids)
        high = (s.first + len(s.options) - 1) * len(ids)
        row: Dict[str, Any] = {
            "key": s.key,
            "label": s.label,
            "answered": len(answered),
            "items": len(ids),
            "min": low,
            "max": high,
            "higher_is_better": s.higher_is_better,
            "orientative": s.orientative,
        }
        if len(answered) < len(ids):
            row.update(score=None, band="", words="incompleta")
            scales.append(row)
            continue
        total = sum(_value(s, i, answers) for i in ids)
        row["score"] = total
        if s.subscales:
            subs = []
            for key, (label, sub_ids) in s.subscales.items():
                sub_total = sum(_value(s, i, answers) for i in sub_ids)
                lo_s, hi_s = (
                    s.first * len(sub_ids),
                    (s.first + len(s.options) - 1) * len(sub_ids),
                )
                band, words = _sub_band(sub_total, lo_s, hi_s)
                subs.append(
                    {
                        "key": key,
                        "label": label,
                        "score": sub_total,
                        "min": lo_s,
                        "max": hi_s,
                        "band": band,
                        "words": words,
                        "higher_is_better": key == "vivir",
                    }
                )
            row["subscales"] = subs
            living = next(x for x in subs if x["key"] == "vivir")
            others = [x for x in subs if x["key"] != "vivir"]
            worst = max(o["band"] == "alta" for o in others)
            band = (
                "baja"
                if worst or living["band"] == "baja"
                else ("alta" if living["band"] == "alta" else "media")
            )
            row.update(
                band=band,
                words={"baja": "baja", "media": "media", "alta": "alta"}[band],
                higher_is_better=True,
            )
        else:
            band, words = _band(s, total)
            row.update(band=band, words=words)
        scales.append(row)
    pictures = [
        {
            "id": p["id"],
            "domain": p["domain"],
            "value": answers.get(p["id"]),
            "label": PICTURE[answers[p["id"]]] if p["id"] in answers else "",
        }
        for p in PICTURES
    ]
    return {
        "variant": variant,
        "scales": scales,
        "pictures": pictures,
        "crisis": at_risk(answers),
    }


def at_risk(answers: Dict[str, Any]) -> bool:
    """PHQ-9 item 9 above zero, or risk words in what was written."""
    from openjarvis.coach.tasks import at_risk as words_at_risk

    if int(answers.get("phq9_9") or 0) > 0:
        return True
    return any(words_at_risk(str(answers.get(k, ""))) for k in OPEN_IDS)


def crisis_text() -> str:
    from openjarvis.coach.tasks import CRISIS

    return (
        CRISIS + " Si está fuera de Ecuador, llame al número de emergencias de su país."
    )


def needs_professional(scores: Dict[str, Any]) -> bool:
    """Published cut-offs: PHQ-9 and GAD-7 from 10, their two-item screeners from 3."""
    by = {s["key"]: (s["score"] or 0) for s in scores["scales"]}
    return bool(
        scores.get("crisis")
        or by.get("phq9", 0) >= 10
        or by.get("gad7", 0) >= 10
        or by.get("phq2", 0) >= 3
        or by.get("gad2", 0) >= 3
        or any(
            x["key"] == "who5" and x["score"] is not None and x["score"] <= 7
            for x in scores["scales"]
        )
    )


# -- the reading ----------------------------------------------------------------

STEPS = {
    "phq2": "",
    "gad2": "",
    "phq9": "Activación conductual: cada día, una actividad pequeña que antes le gustaba o que tenga sentido para usted, apuntada a una hora fija, aunque no tenga ganas. Es de los tratamientos con más evidencia para el ánimo bajo (Dimidjian et al., 2006, Universidad de Washington).",
    "gad7": "Respiración lenta (unas 6 respiraciones por minuto, 5 minutos) cuando note la tensión, y acercarse poco a poco a lo que evita en lugar de huir de ello.",
    "rses": "Autocompasión: escríbase unas líneas como se las escribiría a un buen amigo que pasa por lo mismo (Neff, Universidad de Texas). Hablarse con dureza no motiva; hablarse con respeto, sí.",
    "rrsb": "Cambie el «¿por qué me pasa esto?» por «¿qué paso concreto puedo dar ahora?». Darle vueltas a los porqués alimenta el malestar; pensar en el cómo lo corta (Watkins, Universidad de Exeter).",
    "pswq3": "Tiempo de preocupación: 15 minutos al día, a la misma hora, para preocuparse a propósito; fuera de ese rato, apunte la preocupación y déjela para entonces (Borkovec, Penn State).",
    "auth": "Escriba sus tres valores más importantes y, esta semana, haga una cosa pequeña que vaya con uno de ellos aunque a otros no les encaje.",
    "ucla3": "Un contacto concreto esta semana: escribir o quedar con alguien con quien se siente cómodo, o sumarse a una actividad de grupo que le interese.",
}


STEPS["phq2"], STEPS["gad2"] = STEPS["phq9"], STEPS["gad7"]
STEPS["who5"] = (
    "Tres cosas pequeñas al día que le recarguen (luz de la mañana, moverse 20 minutos, hablar con alguien) y acostarse a la misma hora; el bienestar sube con la rutina, no con un gran cambio."
)
STEPS["sise"] = STEPS["rses"]


def _concerns(scores: Dict[str, Any]) -> List[str]:
    out = []
    for s in scores["scales"]:
        if s["score"] is None:
            continue
        bad = (
            s["band"] in ("baja",)
            if s["higher_is_better"]
            else s["band"] not in ("minimo", "baja", "leve")
        )
        if bad:
            out.append(s["key"])
    return out


def fallback_reading(scores: Dict[str, Any], answers: Dict[str, Any]) -> str:
    """The reading written in code, when no AI engine answers."""
    concerns = _concerns(scores)
    lines = []
    complete = [s for s in scores["scales"] if s["score"] is not None]
    if complete:
        parts = [f"{s['label'].lower()} {s['words']}" for s in complete]
        lines.append("Lo que dicen sus respuestas: " + ", ".join(parts) + ".")
    good = [s["label"].lower() for s in complete if s["key"] not in concerns]
    if good:
        lines.append("Lo que juega a su favor: " + ", ".join(good) + ".")
    steps = [STEPS[k] for k in concerns][:3] or [STEPS["auth"]]
    lines.append("Para esta semana:\n" + "\n".join(f"- {s}" for s in steps))
    if needs_professional(scores):
        lines.append(
            "Con estas puntuaciones conviene hablar con un profesional de salud mental. "
            "No es un diagnóstico; es una buena razón para pedir una cita."
        )
    return "\n\n".join(lines)


def reading_prompt(scores: Dict[str, Any], answers: Dict[str, Any]) -> str:
    rows = []
    for s in scores["scales"]:
        if s["score"] is None:
            rows.append(f"- {s['label']}: incompleta")
            continue
        extra = ""
        if s.get("subscales"):
            extra = (
                " ("
                + "; ".join(
                    f"{x['label']}: {x['score']}/{x['max']}, {x['words']}"
                    for x in s["subscales"]
                )
                + ")"
            )
        tag = " [bandas orientativas]" if s["orientative"] else ""
        rows.append(
            f"- {s['label']}: {s['score']} de {s['min']}-{s['max']}, {s['words']}{tag}{extra}"
        )
    pics = [
        f"- {p['domain']}: {p['label'] or 'sin responder'}" for p in scores["pictures"]
    ]
    opens = [f"- {t} {answers[k]}" for k, t in OPEN if answers.get(k)]
    short = (
        "Es la versión CORTA: solo hay cribados de dos ítems (orientan, no miden la gravedad) "
        "y la soledad; no saques conclusiones de lo que no se preguntó.\n"
        if scores.get("variant") == "corta"
        else ""
    )
    return (
        "Resultados de la encuesta de salud mental del señor.\n"
        + short
        + "Punto de partida (preguntas con imagen):\n"
        + "\n".join(pics)
        + "\n"
        "Escalas validadas:\n"
        + "\n".join(rows)
        + "\n"
        + (
            "Lo que escribió con sus palabras:\n" + "\n".join(opens) + "\n"
            if opens
            else ""
        )
        + ("Necesita ver a un profesional: sí.\n" if needs_professional(scores) else "")
    )


READING_SYSTEM = """Eres Sergio, en su papel de apoyo psicológico (no eres un clínico). Analiza a fondo la encuesta del señor y escríbele de usted, cálido, directo y sin rodeos.
Reglas: no diagnostiques ni uses etiquetas clínicas; usa solo lo que está en los datos; une lo que dicen las escalas con lo que escribió; no inventes cifras ni estudios.
Estructura, con estos cuatro títulos en negrita:
**Lo que veo**: 4-6 frases que conecten no sentirse suficiente, pensar demasiado y querer encajar con sus puntuaciones y sus palabras.
**Lo que juega a su favor**: 2-3 frases.
**Para esta semana**: tres pasos concretos y pequeños, con evidencia (activación conductual, autocompasión, pasar del porqué al cómo, tiempo de preocupación, valores, contacto social), adaptados a lo que escribió.
**Cuándo pedir ayuda**: una o dos frases; si «Necesita ver a un profesional: sí», dilo con claridad y sin alarmar.
Cierra recordando que esto no es un diagnóstico."""


def _reading_ok(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict) or len(str(data.get("lectura") or "").strip()) <= 80:
        raise ValueError("lectura vacía o demasiado corta")
    return data


def write_reading(
    scores: Dict[str, Any], answers: Dict[str, Any], generate: Optional[Any] = None
) -> Tuple[str, str]:
    """(text, who) where who is "ia" or "codigo"."""
    from openjarvis.health.privacy import local_only, scrub

    if local_only():  # the owner keeps his mental health on his computer
        return fallback_reading(scores, answers), "codigo"
    prompt = scrub(reading_prompt(scores, answers))
    try:
        if generate is None:
            # The coach's path: Gemini with a hedged backup. (It used to call
            # an engine with chat dicts and no model, which always failed, so
            # every reading was the template written in code.)
            from openjarvis.coach.brain import ask

            data = ask(
                prompt
                + "\nResponde en JSON: "
                + '{"lectura": "<el texto con los cuatro títulos>"}',
                system=READING_SYSTEM,
                max_tokens=4000,
                effort="medium",
                check=_reading_ok,
            )
            return str(data["lectura"]).strip(), "ia"
        res = generate(
            messages=[
                {"role": "system", "content": READING_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=900,
            temperature=0.5,
        )
        text = (
            getattr(res, "content", None)
            or (res.get("content") if isinstance(res, dict) else "")
            or ""
        ).strip()
        if len(text) > 80:
            return text, "ia"
    except Exception:  # noqa: BLE001 - the reading in code below
        pass
    return fallback_reading(scores, answers), "codigo"


__all__ = [
    "DEFAULT_VARIANT",
    "VARIANTS",
    "WIDGETS",
    "widgets",
    "definition_count",
    "variant_of",
    "DELAY_SECONDS",
    "OPEN",
    "PICTURES",
    "SCALES",
    "STEPS",
    "Scale",
    "at_risk",
    "clean_answers",
    "crisis_text",
    "definition",
    "delay_seconds",
    "fallback_reading",
    "needs_professional",
    "reading_prompt",
    "score",
    "sources",
    "write_reading",
]
