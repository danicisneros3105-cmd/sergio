# ruff: noqa: E501 — the technique cards are prose
"""Two background specialists for every video, trained on the fly brain.

* **Cine** (shorts, films, ads, animation): the craft of the great film
  directors, as technique cards — Nolan's intercutting, ticking clock,
  practical scale and broken time; Villeneuve's scale; Fincher's control;
  Spielberg's face; Kubrick's symmetry and match cut; Wes Anderson's
  tableaux; Tarantino's tension; Scorsese's energy; Deakins' light;
  Cuarón's long take; Hitchcock's suspense; Kurosawa's weather.
* **Creadores** (YouTube, TikTok, Reels): the craft of the best creators and
  editors — the 3-second hook and the stakes counter, rehooks, jump cuts,
  timelapses, speed ramps, maps and archive, the question hook, build and
  payoff, kinetic captions, food macro, flat explainers, POV, b-roll layers,
  before/after and loops.

The names say where a technique is best known; nobody is imitated. Each
specialist is its own mushroom body in the core (``especialista:cine``,
``especialista:creadores``) on the same measured wiring. It is born by
training on its cards (the requests where each technique fits), measured on
requests it never saw (:func:`learning_curve`), and keeps learning from
every finished video: the techniques it advised are rewarded when the final
review scores high and punished when it scores low (:func:`learn_from_video`).
Its advice (:func:`advise`) goes into the director's treatment and the
editor's plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

PRETRAIN_EPOCHS = 4
PRACTICE_PUNISH = 0.3  # a wrong choice while practising: a little punishment
GOOD_SCORE = 8.0
BAD_SCORE = 6.0


@dataclass(frozen=True)
class Card:
    key: str
    school: str  # where the technique is best known (credit, not imitation)
    how: str  # the instruction, in English, as the prompts are
    train: Tuple[str, ...]  # requests where it fits (it learns from these)
    held: Tuple[str, ...]  # requests it never sees in training (the proof)


CINE: Tuple[Card, ...] = (
    Card("intercut", "Christopher Nolan", "cross-cut two or three parallel lines of action at rising tempo until they converge in one climax",
         ("una historia con dos tiempos que se cruzan", "el rescate mientras la bomba avanza en otra parte",
          "tres personajes en lugares distintos que llegan al mismo final", "parallel stories that meet at the end",
          "montaje paralelo entre el pasado y el presente"),
         ("dos hermanos en ciudades distintas el mismo día", "the heist and the chase happening at once")),
    Card("reloj", "Christopher Nolan", "a ticking clock: a visible deadline, a pulse in the music that keeps rising (Shepard tone), shots shortening toward zero",
         ("quedan diez minutos para que todo explote", "una carrera contra el tiempo", "la cuenta regresiva antes del lanzamiento",
          "suspense with a deadline", "tienen hasta el amanecer para escapar"),
         ("el último tren sale en cinco minutos", "a race before the storm hits")),
    Card("practico", "Christopher Nolan", "practical, in-camera feel: real scale, large-format wide shots, real light and physical effects, no glossy CGI look",
         ("que se sienta real, sin efectos de computadora", "un avión de verdad estrellándose", "escenas a escala real con explosiones físicas",
          "IMAX feel, everything shot for real", "efectos prácticos como en el cine clásico"),
         ("un tráiler que parezca filmado de verdad", "a car stunt that feels physical")),
    Card("no_lineal", "Christopher Nolan", "break time: open on the ending, then go back and reveal the causes piece by piece; each cut answers one question and opens another",
         ("empieza por el final y luego explica cómo llegamos", "una historia contada al revés", "flashbacks que revelan el giro",
          "a mystery told out of order", "el espectador descubre la verdad al final"),
         ("un crimen que se entiende hacia atrás", "memories that only make sense at the end")),
    Card("escala", "Denis Villeneuve", "immense scale: a tiny human against huge brutalist shapes, fog, silence and a deep low drone, slow and patient shots",
         ("una nave gigante sobre el desierto", "algo enorme e inexplicable aparece", "ciencia ficción épica y silenciosa",
          "a lone figure in a vast landscape", "monumental, que te haga sentir pequeño"),
         ("una ciudad del futuro en la niebla", "the alien structure towering over the soldiers")),
    Card("control", "David Fincher", "total control: locked, precise camera that moves only with the actor, cold yellow-green low-key grade, clinical cuts",
         ("un thriller frío y obsesivo", "un detective que investiga un asesino", "algo oscuro, preciso y perturbador",
          "corporate thriller, cold and exact", "una oficina tensa de noche"),
         ("un hacker trabajando de madrugada", "the investigation room at night")),
    Card("rostro", "Steven Spielberg", "the face first: hold on a character looking up in wonder before revealing what they see; a flowing camera, warm backlight",
         ("un niño descubre algo mágico", "el momento de asombro al ver el dinosaurio", "aventura familiar con emoción",
          "the moment of wonder", "alguien mira al cielo y no puede creerlo"),
         ("la familia ve la ballena por primera vez", "a kid finds a spaceship in the woods")),
    Card("simetria", "Stanley Kubrick", "one-point perspective, perfect symmetry, slow zoom or steady track down a corridor, unsettling stillness",
         ("un pasillo inquietante", "algo frío y perfectamente ordenado", "terror psicológico elegante",
          "symmetrical, eerie, controlled", "una estación espacial silenciosa"),
         ("un hotel vacío que da miedo", "a cold geometric hallway")),
    Card("match_cut", "Stanley Kubrick", "a graphic match cut: one shape or motion becomes another across time or place (bone to satellite)",
         ("del pasado al futuro en un solo corte", "transformar un objeto en otro con un corte", "conectar dos épocas",
          "a cut that jumps thousands of years", "una transición ingeniosa entre escenas"),
         ("el hueso que se convierte en nave", "from the old phone to the new one in one cut")),
    Card("diorama", "Wes Anderson", "flat frontal tableaux, centred subjects, pastel palette, whip pans and chapter cards, deadpan comedy",
         ("algo pastel, simétrico y gracioso", "un hotel de colores con personajes raros", "estética de casa de muñecas",
          "quirky storybook look", "una comedia con capítulos y colores suaves"),
         ("la familia excéntrica en su casa rosada", "a whimsical road trip with chapter titles")),
    Card("tension", "Quentin Tarantino", "long tense dialogue that hides a threat, low trunk-shot angles, chapters, then a sudden release",
         ("una conversación tensa antes de la pelea", "diálogo con amenaza escondida", "capítulos con nombre y violencia repentina",
          "a standoff at a diner", "la mesa donde todos sospechan de todos"),
         ("el interrogatorio en la granja", "a tense negotiation that explodes")),
    Card("energia", "Martin Scorsese", "kinetic energy: freeze frames, voice-over, fast push-ins and pop songs that drive the montage",
         ("el ascenso y caída de un gánster", "montaje con canciones y voz en off", "una vida contada a toda velocidad",
          "rise and fall with music", "la historia de un estafador carismático"),
         ("el corredor de bolsa que lo pierde todo", "a crime family over the decades")),
    Card("luz", "Roger Deakins", "one motivated light source, silhouettes, haze and natural colour; light tells the story",
         ("siluetas al atardecer", "luz natural muy cinematográfica", "una escena iluminada solo por fuego",
          "beautiful light, silhouettes in smoke", "fotografía de cine con contraluz"),
         ("un vaquero contra el sol", "a room lit by one window")),
    Card("plano_secuencia", "Alfonso Cuarón", "one long take: the camera floats through the action with no cuts, immersion over coverage",
         ("todo en un solo plano sin cortes", "la cámara sigue al personaje por la batalla", "inmersivo, como si estuvieras ahí",
          "one continuous shot", "un plano largo dentro del caos"),
         ("la persecución en un solo plano", "a long take through the market")),
    Card("suspense", "Alfred Hitchcock", "suspense over surprise: show the audience the danger the character does not see, then hold",
         ("el público sabe algo que el personaje no", "una bomba debajo de la mesa", "suspenso clásico",
          "the audience knows the killer is inside", "alguien que no sabe que lo siguen"),
         ("la mujer que no ve al hombre en la ventana", "a guest unaware of the poison")),
    Card("clima", "Akira Kurosawa", "weather as emotion: rain, wind, fog and dust moving in every frame; telephoto layers",
         ("una batalla bajo la lluvia", "samuráis en la niebla", "el viento y el polvo cuentan la emoción",
          "epic rain-soaked duel", "tormenta dramática durante el enfrentamiento"),
         ("dos guerreros en la tormenta", "the village in the wind and dust")),
)  # fmt: skip

CREADORES: Tuple[Card, ...] = (
    Card("gancho", "MrBeast", "show the payoff and the stakes in the first 3 seconds and say the promise out loud; no intro",
         ("que nadie se salte el inicio", "empieza fuerte para retener", "un video viral que enganche al instante",
          "hook in the first seconds", "cómo hago que no se vayan al principio"),
         ("el inicio de mi video aburre", "grab attention immediately")),
    Card("contador", "MrBeast", "an on-screen stakes counter (money, days, people left) that escalates every act",
         ("el último en salir gana dinero", "sobreviví 100 días", "cuánto dinero queda en el reto",
          "challenge with a prize counter", "días que pasan en la isla"),
         ("100 personas compiten por un premio", "last to leave the circle wins")),
    Card("rehook", "MrBeast", "a new twist, reveal or question every ~30 s so the viewer never has a reason to leave",
         ("que no se aburran a la mitad", "retención durante todo el video", "sorpresas cada poco",
          "keep viewers watching to the end", "un giro cada medio minuto"),
         ("la gente se va a la mitad de mis videos", "more twists in the middle")),
    Card("jump_cut", "Casey Neistat", "jump cuts on the talk, handheld walk-and-talk, titles written on location, honest vlog energy",
         ("un vlog de mi día", "cuento mi viaje a la cámara", "video personal y rápido de mi vida",
          "daily vlog with energy", "habla a cámara caminando por la ciudad"),
         ("mi rutina en Nueva York", "a day in my life video")),
    Card("timelapse", "Casey Neistat", "timelapse and hyperlapse to pass time and change place, sped up city and sky",
         ("mostrar que pasa el día rápido", "el viaje de un lugar a otro", "la ciudad de día a noche",
          "show time passing fast", "construcción acelerada"),
         ("el atardecer acelerado sobre la ciudad", "a road trip compressed")),
    Card("speed_ramp", "Peter McKinnon", "speed ramps and match cuts on movement, whooshes, punchy cinematic b-roll",
         ("b-roll cinematográfico de mi café", "transiciones con movimiento", "video de producto con ritmo",
          "cinematic b-roll with smooth transitions", "cortes que fluyen con el movimiento"),
         ("mi nueva cámara en cámara lenta y rápida", "coffee b-roll with whip transitions")),
    Card("mapas", "Johnny Harris", "maps that zoom and draw, archive documents on a desk, red lines connecting the evidence, a narrator who investigates",
         ("por qué este país es así", "explica la geopolítica con mapas", "una investigación con documentos",
          "geography explainer with maps", "la historia de una frontera"),
         ("por qué Ecuador tiene dos climas", "why this border is so strange")),
    Card("pregunta", "Veritasium", "open with a counter-intuitive question and the common wrong answer, then prove the real one",
         ("explica algo de ciencia que nadie entiende", "un dato que contradice lo que crees", "por qué el cielo es azul",
          "science explainer with a surprising answer", "la respuesta no es la que piensas"),
         ("qué cae más rápido, una pluma o un martillo", "the misconception everyone has")),
    Card("construccion", "Mark Rober", "build and payoff: the problem, the build with failures, the big test in slow motion, the reveal",
         ("construyo una máquina para un reto", "invento algo y lo pruebo", "ingeniería divertida con prueba final",
          "engineering build and test", "hice un dispositivo contra ladrones"),
         ("mi trampa para ardillas", "building the world's largest device")),
    Card("subtitulos", "Ali Abdaal", "kinetic captions: the spoken words pop on screen as they are said, key word highlighted",
         ("subtítulos dinámicos para TikTok", "texto en pantalla mientras hablo", "palabras que aparecen al ritmo",
          "animated captions for shorts", "que se lea sin sonido"),
         ("mi reel necesita letras grandes", "captions that pop word by word")),
    Card("comida", "food creators", "macro food shots, sizzle and crunch sound, slow-motion pours and steam, hands in frame",
         ("video de mi hamburguesa", "receta rápida para redes", "comida que se vea deliciosa",
          "food reel with ASMR", "el queso derritiéndose"),
         ("mi pizzería quiere un video", "a dessert that looks irresistible")),
    Card("explicador", "Kurzgesagt", "flat vector animation, bright palette, a small character guiding, every idea a picture",
         ("explica un tema complejo con animación", "animación educativa sobre el universo", "un explicador bonito y simple",
          "animated science explainer", "cómo funciona el sistema inmune animado"),
         ("qué pasa si el sol desaparece, animado", "an animated guide to black holes")),
    Card("pov", "POV creators", "first-person camera: the viewer is the protagonist, a POV caption on top",
         ("pov: eres el cliente de mi tienda", "en primera persona", "como si el espectador fuera el protagonista",
          "POV video for TikTok", "pov llegas tarde al trabajo"),
         ("pov: tu primer día en mi gimnasio", "first-person view of a chef")),
    Card("capas", "Ali Abdaal", "clean talking head with b-roll layers, screen captures and text overlays to make every point visible",
         ("video educativo hablando a cámara", "consejos de productividad", "explico mi método con ejemplos",
          "talking head with b-roll", "un tutorial claro y bonito"),
         ("mis consejos para estudiar mejor", "how I organise my week")),
    Card("antes_despues", "transformation creators", "before / after: show the end state first, then the transformation, split screen at the reveal",
         ("antes y después de mi cuarto", "transformación de mi cuerpo", "remodelación de la casa",
          "before and after reveal", "cómo quedó después del cambio"),
         ("mi auto viejo restaurado", "the room makeover reveal")),
    Card("bucle", "short-form creators", "vertical 9:16 with safe zones, trending sound, an ending that loops back into the start",
         ("un short que se repita solo", "tiktok con audio en tendencia", "reel corto y adictivo",
          "a loopable short", "que lo vean dos veces sin darse cuenta"),
         ("un video de 15 segundos para tiktok", "a loop that never ends")),
)  # fmt: skip

SPECIALISTS: Dict[str, Tuple[Card, ...]] = {"cine": CINE, "creadores": CREADORES}
BY_STYLE = {
    "corto-3d": "cine",
    "animacion": "cine",
    "anuncio-comida": "cine",
    "lanzamiento-producto": "cine",
    "metas-grandes": "creadores",
    "reto-viral": "creadores",
}
_FILM_WORDS = ("pelicul", "película", "corto", "cine", "film", "movie", "trailer", "tráiler", "escena", "anuncio")  # fmt: skip


def _cards(kind: str) -> Tuple[Card, ...]:
    return SPECIALISTS.get(kind, ())


def _card(kind: str, key: str) -> Optional[Card]:
    return next((c for c in _cards(kind) if c.key == key), None)


def which(style: str = "", brief: str = "") -> str:
    """The specialist for this video: by the style, else by the brief."""
    if style in BY_STYLE:
        return BY_STYLE[style]
    low = (brief or "").lower()
    return "cine" if any(w in low for w in _FILM_WORDS) else "creadores"


def _core(core: Any = None) -> Any:
    if core is not None:
        return core
    from openjarvis.connectome.core import get_core

    return get_core()


def _practice(mb: Any, cards: Sequence[Card]) -> None:
    """One epoch of practice: the right technique is rewarded, and a wrong
    one that the brain would still have chosen gets a little punishment
    (its dopamine neuron depresses it), like a fly learning by trying."""
    actions = [f"tec:{c.key}" for c in cards]
    for c in cards:
        right = f"tec:{c.key}"
        for text in c.train:
            mb.learn(text, right, 1.0)
            s = mb.scores(text, actions)
            for a in sorted(actions, key=lambda a: -s[a])[:3]:
                if a != right and s[a] >= s[right]:
                    mb.learn(text, a, -PRACTICE_PUNISH)


def pretrain(mb: Any, kind: str, epochs: int = PRETRAIN_EPOCHS) -> Dict[str, Any]:
    """Born knowing its craft: every card's requests, a few epochs."""
    cards = _cards(kind)
    for _ in range(epochs):
        _practice(mb, cards)
    mb.meta["specialist"] = {
        "kind": kind,
        "epochs": epochs,
        "cards": len(cards),
        "examples": sum(len(c.train) for c in cards),
    }
    mb.save()
    return mb.meta["specialist"]


def brain_for(kind: str, core: Any = None) -> Optional[Any]:
    if kind not in SPECIALISTS:
        return None
    texts = [t for c in _cards(kind) for t in c.train]
    return _core(core).born(
        f"especialista:{kind}", "specialist", texts, lambda mb: pretrain(mb, kind)
    )


def held_out(mb: Any, kind: str) -> Dict[str, float]:
    """On requests it never saw: right technique first (top-1) / in its 3."""
    cards = _cards(kind)
    actions = [f"tec:{c.key}" for c in cards]
    top1 = top3 = n = 0
    for c in cards:
        for text in c.held:
            s = mb.scores(text, actions)
            ranked = sorted(actions, key=lambda a: -s[a])
            top1 += ranked[0] == f"tec:{c.key}"
            top3 += f"tec:{c.key}" in ranked[:3]
            n += 1
    return {
        "top1": round(top1 / max(1, n), 3),
        "top3": round(top3 / max(1, n), 3),
        "chance_top1": round(1 / max(1, len(cards)), 3),
        "chance_top3": round(3 / max(1, len(cards)), 3),
        "n": n,
    }


def learning_curve(
    kind: str, core: Any = None, epochs: int = 6
) -> List[Dict[str, Any]]:
    """The proof that it learns: a newborn brain on the same wiring, trained
    epoch by epoch, measured each time on requests it never saw."""
    from openjarvis.connectome.core import SPARSITY_BY_PREFIX
    from openjarvis.connectome.mushroom import MushroomBody

    c = _core(core)
    mb = MushroomBody(
        c.wiring,
        None,
        f"prueba-{kind}",
        receptors=c.receptors,
        sparsity=SPARSITY_BY_PREFIX["especialista:"],
    )
    curve = [{"epoch": 0, **held_out(mb, kind), **_synapses(mb)}]
    for e in range(1, epochs + 1):
        _practice(mb, _cards(kind))
        curve.append({"epoch": e, **held_out(mb, kind), **_synapses(mb)})
    return curve


def _synapses(mb: Any) -> Dict[str, int]:
    s = mb.stats()["synapses"]
    return {"changed": s["cambiadas"], "grown": s["nuevas"]}


def advise(
    kind: str, brief: str, core: Any = None, k: int = 3
) -> List[Tuple[str, str, str, float]]:
    """The techniques its brain wants for *brief*: (key, school, how, strength)."""
    mb = brain_for(kind, core)
    if mb is None:
        return []
    cards = _cards(kind)
    s = mb.scores(brief, [f"tec:{c.key}" for c in cards])
    ranked = sorted(cards, key=lambda c: -s[f"tec:{c.key}"])
    return [(c.key, c.school, c.how, round(s[f"tec:{c.key}"], 3)) for c in ranked[:k]]


def prompt_block(advice: Sequence[Tuple[str, str, str, float]], kind: str) -> str:
    if not advice:
        return ""
    who = "film" if kind == "cine" else "creator"
    lines = "\n".join(f"- {how} (as {school} does)" for _k, school, how, _v in advice)
    return (
        f"\nYour {who} specialist, trained on how the best do it, says this brief "
        f"calls for:\n{lines}\nUse them where they serve the story; do not name anyone on screen.\n"
    )


def learn_from_video(
    kind: str,
    brief: str,
    techniques: Sequence[str],
    score: Optional[float],
    core: Any = None,
) -> float:
    """After the final review: its dopamine on the techniques it advised."""
    if not techniques or not isinstance(score, (int, float)):
        return 0.0
    if score >= GOOD_SCORE:
        reward = min(1.0, 0.5 + (score - GOOD_SCORE) / 4)
    elif score < BAD_SCORE:
        reward = -min(1.0, 0.4 + (BAD_SCORE - score) / 6)
    else:
        return 0.0
    mb = brain_for(kind, core)
    if mb is None:
        return 0.0
    for key in techniques:
        if _card(kind, key):
            mb.learn(brief, f"tec:{key}", reward)
    _core(core).save(force=True)
    return reward


def teach(kind: str, brief: str, key: str, liked: bool, core: Any = None) -> bool:
    """The owner's own taste: «this worked» / «not this» for a technique."""
    mb = brain_for(kind, core)
    if mb is None or not _card(kind, key):
        return False
    mb.learn(brief, f"tec:{key}", 1.0 if liked else -0.8)
    _core(core).save(force=True)
    return True


def catalog() -> Dict[str, List[Dict[str, str]]]:
    return {
        kind: [{"key": c.key, "school": c.school, "how": c.how} for c in cards]
        for kind, cards in SPECIALISTS.items()
    }


__all__ = [
    "CINE", "CREADORES", "Card", "SPECIALISTS", "advise", "brain_for", "catalog", "held_out",
    "learn_from_video", "learning_curve", "pretrain", "prompt_block", "teach", "which",
]  # fmt: skip
