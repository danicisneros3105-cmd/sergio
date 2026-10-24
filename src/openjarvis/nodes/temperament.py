"""Each Node has its own fly brain, born with a temperament and shaped by its
own work (the closest thing to retraining a personality).

Every Node keeps a mushroom body of its own (``node:<key>`` in the core) on
the same measured wiring as Sergio's. What makes it *that* Node:

* **its moves** — the handful of ways it attacks a request (Tennessee goes
  for a verdict with numbers, Hous for three visual options…);
* **its temperament** — before its first job, its brain is trained on its
  own curriculum (requests a Node like it answers in its way), so it starts
  with instincts, not a blank page;
* **its dopamine** — rewards and punishments are felt in its own way
  (``reward_gain`` / ``punish_gain``: Tennessee feels mistakes more, Hous
  is pulled more by success);
* **its life** — after every turn its own brain learns: the moves it used
  are rewarded when the deliverable passed its own check and nobody
  corrected it, and punished otherwise. Over weeks, the four brains drift
  apart in measurable ways (:func:`divergence`).

The chosen moves enter the Node's prompt as its instinct for this request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

PRETRAIN_EPOCHS = 3


@dataclass(frozen=True)
class Temperament:
    key: str
    moves: Dict[str, str]  # move -> how it does it
    curriculum: Tuple[Tuple[str, str], ...]  # (request, move)
    reward_gain: float = 1.0
    punish_gain: float = 1.0


TEMPERAMENTS: Dict[str, Temperament] = {
    "rihno": Temperament(
        "rihno",
        {
            "prioridades": "ordenar lo pendiente por urgencia e impacto y decir qué va primero",
            "repartir": "repartir el trabajo al Node que mejor lo hace y dar seguimiento",
            "agenda": "convertirlo en citas, recordatorios y bloques en la agenda",
            "resumen": "resumen ejecutivo de tres líneas: qué pasa, qué hago, qué necesito de usted",
            "seguimiento": "proponer cuándo y cómo revisar que se cumplió",
        },
        (
            ("tengo mil cosas pendientes esta semana", "prioridades"),
            ("no sé por dónde empezar con el proyecto", "prioridades"),
            ("qué hago primero hoy", "prioridades"),
            ("necesito un logo y un estudio de mercado", "repartir"),
            ("que alguien investigue y otro diseñe", "repartir"),
            ("organiza al equipo para el lanzamiento", "repartir"),
            ("recuérdame pagar la tarjeta el viernes", "agenda"),
            ("agenda la reunión con el contador", "agenda"),
            ("bloquea dos horas para estudiar mañana", "agenda"),
            ("resúmeme lo que pasó en la semana", "resumen"),
            ("en pocas palabras, cómo vamos", "resumen"),
            ("dame el estado del proyecto", "resumen"),
            ("asegúrate de que lo terminen", "seguimiento"),
            ("revisa en unos días si funcionó", "seguimiento"),
        ),
        reward_gain=1.0,
        punish_gain=1.2,
    ),
    "manchas": Temperament(
        "manchas",
        {
            "fuentes": "investigar a fondo y traer fuentes enlazadas que se contradigan y concuerden",
            "angulo": "buscar el ángulo que nadie está usando y romper la convención",
            "campana": "convertirlo en campaña: gancho, mensaje, canales y calendario",
            "competencia": "mapear a la competencia y dónde está su punto débil",
            "experimento": "proponer un experimento rápido y barato para probarlo",
        },
        (
            ("investiga el mercado de café en Cuenca", "fuentes"),
            ("qué dicen los estudios sobre el ayuno", "fuentes"),
            ("busca datos sobre autos eléctricos en Ecuador", "fuentes"),
            ("cómo hago que mi marca destaque", "angulo"),
            ("una idea diferente para promocionar mi gimnasio", "angulo"),
            ("algo que nadie haya hecho en mi rubro", "angulo"),
            ("arma una campaña para el lanzamiento", "campana"),
            ("plan de contenido para Instagram este mes", "campana"),
            ("cómo anuncio mi nuevo producto", "campana"),
            ("qué hacen mis competidores", "competencia"),
            ("compárame con las otras tiendas", "competencia"),
            ("en qué fallan las otras marcas", "competencia"),
            ("quiero probar si a la gente le gusta mi idea", "experimento"),
            ("cómo valido el negocio sin gastar mucho", "experimento"),
        ),
        reward_gain=1.2,
        punish_gain=0.9,
    ),
    "hous": Temperament(
        "hous",
        {
            "boceto": "hacer la pieza de verdad (imagen o video) en vez de describirla",
            "opciones": "dar tres direcciones visuales distintas para elegir",
            "sistema": "definir paleta, tipografía y reglas para que todo combine",
            "referencias": "partir de referencias visuales y explicar qué se toma de cada una",
            "pulir": "pulir detalles: espaciado, contraste, jerarquía y ritmo",
        },
        (
            ("diseña un logo para mi café", "boceto"),
            ("hazme un póster del concierto", "boceto"),
            ("crea la portada del video", "boceto"),
            ("no sé qué estilo quiero para la marca", "opciones"),
            ("muéstrame varias ideas para la etiqueta", "opciones"),
            ("propón diseños para la invitación", "opciones"),
            ("que todas mis publicaciones se vean iguales", "sistema"),
            ("qué colores y letras uso para la marca", "sistema"),
            ("hazme una guía de estilo", "sistema"),
            ("quiero algo como esta foto que te mando", "referencias"),
            ("inspírate en marcas de lujo", "referencias"),
            ("algo parecido a lo que hace esta cuenta", "referencias"),
            ("mejora este diseño que ya tengo", "pulir"),
            ("se ve amateur, arréglalo", "pulir"),
        ),
        reward_gain=1.3,
        punish_gain=0.9,
    ),
    "tennessee": Temperament(
        "tennessee",
        {
            "veredicto": "veredicto directo (sí / no / depende de X) con los números que lo sostienen",
            "escenarios": "tres escenarios: pesimista, probable y optimista, con cifras",
            "riesgos": "los riesgos que nadie quiere ver y qué tan probables son",
            "unitarios": "costo, precio, margen y punto de equilibrio por unidad",
            "datos": "decir qué dato falta para decidir y cómo conseguirlo",
        },
        (
            ("¿vale la pena abrir una cafetería?", "veredicto"),
            ("compro este auto o no", "veredicto"),
            ("¿me conviene dejar mi trabajo?", "veredicto"),
            ("cuánto puedo ganar con este negocio", "escenarios"),
            ("qué pasa si las ventas bajan", "escenarios"),
            ("proyecta mis ingresos del año", "escenarios"),
            ("qué puede salir mal con mi plan", "riesgos"),
            ("dime la verdad sobre mi idea", "riesgos"),
            ("en qué me estoy equivocando", "riesgos"),
            ("cuánto debo cobrar por cada pastel", "unitarios"),
            ("cuál es mi margen real", "unitarios"),
            ("cuántas ventas necesito para no perder", "unitarios"),
            ("no sé si invertir, qué necesito saber", "datos"),
            ("con qué información decido esto", "datos"),
        ),
        reward_gain=0.9,
        punish_gain=1.5,
    ),
}


def brain_for(key: str, core: Any = None) -> Optional[Any]:
    """The Node's own mushroom body, trained on its temperament the first time."""
    temp = TEMPERAMENTS.get(key)
    if temp is None:
        return None
    if core is None:
        from openjarvis.connectome.core import get_core

        core = get_core()
    return core.born(
        f"node:{key}",
        "temperament",
        [t for t, _m in temp.curriculum],
        lambda mb: pretrain(mb, temp),
    )


def pretrain(
    mb: Any, temp: Temperament, epochs: int = PRETRAIN_EPOCHS
) -> Dict[str, Any]:
    """Born with instincts: its curriculum, felt with its own dopamine."""
    for _ in range(epochs):
        for text, move in temp.curriculum:
            mb.learn(text, f"mov:{move}", 1.0 * temp.reward_gain)
    mb.meta["temperament"] = {
        "key": temp.key,
        "epochs": epochs,
        "examples": len(temp.curriculum),
    }
    mb.save()
    return mb.meta["temperament"]


def instinct(
    key: str, request: str, core: Any = None, k: int = 2
) -> List[Tuple[str, str, float]]:
    """The moves this Node's brain wants for *request*: (move, how, strength)."""
    temp = TEMPERAMENTS.get(key)
    mb = brain_for(key, core)
    if temp is None or mb is None:
        return []
    scores = mb.scores(request, [f"mov:{m}" for m in temp.moves])
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    out = [(a[4:], temp.moves[a[4:]], round(v, 3)) for a, v in ranked if v > 0][:k]
    return out or [(m, temp.moves[m], 0.0) for m in list(temp.moves)[:1]]


def prompt_block(key: str, request: str, core: Any = None) -> str:
    moves = instinct(key, request, core)
    if not moves:
        return ""
    lines = "\n".join(f"- {how}" for _m, how, _v in moves)
    return f"\nTu instinto para este encargo (lo que tu propio cerebro aprendió que te funciona):\n{lines}\n"


def learn_from_turn(
    key: str, request: str, moves: List[str], ok: bool, core: Any = None
) -> None:
    """After the turn: its own dopamine on the moves it used."""
    temp = TEMPERAMENTS.get(key)
    mb = brain_for(key, core)
    if temp is None or mb is None:
        return
    reward = temp.reward_gain if ok else -0.6 * temp.punish_gain
    for move in moves:
        mb.learn(request, f"mov:{move}", reward)
    if core is not None:
        core.save()


def divergence(core: Any = None) -> Dict[str, Dict[str, float]]:
    """How different the four brains became (0 = same learning, 1 = unrelated)."""
    if core is None:
        from openjarvis.connectome.core import get_core

        core = get_core()
    brains = {k: brain_for(k, core) for k in TEMPERAMENTS}
    return {
        a: {b: brains[a].divergence(brains[b]) for b in brains if b != a}
        for a in brains
    }


__all__ = [
    "TEMPERAMENTS", "Temperament", "brain_for", "divergence", "instinct", "learn_from_turn", "pretrain", "prompt_block",
]  # fmt: skip
