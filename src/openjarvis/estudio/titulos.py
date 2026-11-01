"""Only one job: titles for videos and hooks for reels, written and then judged.

A model writes many candidates from different angles (curiosity, a number,
the stakes, the contrarian view, the how-to, the story, the challenge). Then
**code** judges every one with what is known about what makes people click
and what platforms punish:

* length for the place it is read (a YouTube title is cut near 60
  characters on a phone; a reel's hook must be read in about 2 seconds, ~8
  words; TikTok and Shorts in between);
* the topic's key words early (people and search read the start);
* specific (a number, a name, a place) beats vague;
* an open question or a gap («por qué», «lo que nadie…»), but no lie:
  promises the video cannot keep («no creerás», «100 % garantizado», «gratis»
  without reason) and shouting (several words in capitals, «!!!») lose points;
* no emojis (the owner's rule), no hashtags in the title;
* not a copy of another candidate (word overlap) nor of the competition;
* a bonus when it carries a word of a real trend (from :mod:`radar`).

Without a model there are honest templates from the topic. Each result says
why it scored what it scored. Nothing is published.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Optional

LIMITS = {  # (ideal min, ideal max, hard max) in characters; reels in words
    "youtube": (38, 60, 100),
    "shorts": (25, 50, 100),
    "tiktok": (20, 60, 150),
    "reels": (3, 8, 14),
}
ANGLES = ("curiosidad", "numero", "lo que esta en juego", "contrario", "como hacerlo",
          "historia", "reto", "error comun")  # fmt: skip

PROMPT = """You write titles for a {plataforma} video. Topic: {tema}.
{extra}Write {n} different candidates in {idioma}, using these angles (several each): {angulos}.
Rules: true to the video (never promise what it does not deliver), the key words of the topic
in the first words, specific (numbers, names, places) when the topic gives them, no emojis,
no hashtags, no ALL CAPS sentences, no clickbait lies.
{forma}
Answer ONLY JSON: {{"titles": [{{"text": "...", "angle": "..."}}]}}"""

FORMA = {
    "reels": "Each one is the FIRST LINE said and shown on screen of a reel: 3 to 8 words, read in 2 seconds.",
    "youtube": "Each one is a YouTube title: ideally 40-60 characters.",
    "shorts": "Each one is a YouTube Shorts title: ideally under 50 characters.",
    "tiktok": "Each one is a TikTok caption first line: under 60 characters.",
}

CURIOSITY = re.compile(
    r"\b(por qu[eé]|c[oó]mo|lo que|nadie|secreto|verdad|realmente|error|nunca|antes de|"
    r"why|how|what|nobody|secret|truth|mistake|never|before)\b", re.I)  # fmt: skip
LIES = re.compile(
    r"(no creer[aá]s|no lo vas a creer|100 ?%|garantizad|gratis|you won'?t believe|"
    r"shocking|impactante!|te cambiar[aá] la vida|incre[ií]ble!)", re.I)  # fmt: skip
EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿️]")
_STOP = set(
    "el la los las un una de del al y o en con por para que como mas muy su sus es son lo le se "
    "the a an of and or to in on for with is are this that your you".split()
)


def plain(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    )


def words(text: str) -> List[str]:
    return [
        w
        for w in re.findall(r"[a-z0-9]+", plain(text))
        if w not in _STOP and len(w) > 2
    ]


def clean(text: str) -> str:
    text = EMOJI.sub("", str(text or ""))
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    return " ".join(text.split()).strip(" -·|\"'")


def judge(title: str, tema: str, plataforma: str = "youtube",
          trend_words: Iterable[str] = (), others: Iterable[str] = ()) -> Dict[str, Any]:  # fmt: skip
    """Score one title (0–10) and say why."""
    lo, hi, hard = LIMITS.get(plataforma, LIMITS["youtube"])
    size = len(title.split()) if plataforma == "reels" else len(title)
    s, why = 5.0, []
    if lo <= size <= hi:
        s += 1.5
        why.append("largo justo")
    elif size > hard:
        s -= 3.0
        why.append("demasiado largo: se corta")
    elif size > hi:
        s -= 1.0
        why.append("algo largo")
    else:
        s -= 0.8
        why.append("muy corto")
    key = set(words(tema))
    first = words(" ".join(title.split()[:5]))
    if key and key & set(first):
        s += 1.2
        why.append("el tema al principio")
    elif key and not key & set(words(title)):
        s -= 1.5
        why.append("no nombra el tema")
    if re.search(r"\d", title):
        s += 0.8
        why.append("específico (número)")
    if CURIOSITY.search(title):
        s += 0.8
        why.append("abre una pregunta")
    if LIES.search(title):
        s -= 2.5
        why.append("promete de más")
    caps = [
        w
        for w in title.split()
        if len(w) > 2 and w.isupper() and not re.search(r"\d", w)
    ]
    if len(caps) > 1:
        s -= 1.2
        why.append("grita en mayúsculas")
    if title.count("!") > 1:
        s -= 0.6
    trend = {plain(w) for w in trend_words}
    if trend and trend & set(words(title)):
        s += 0.7
        why.append("lleva una palabra en tendencia")
    mine = set(words(title))
    for o in others:
        theirs = set(words(o))
        if mine and theirs and len(mine & theirs) / len(mine | theirs) > 0.7:
            s -= 1.5
            why.append("casi igual a otro")
            break
    return {"puntos": round(max(0.0, min(10.0, s)), 1), "por_que": why}


def templates(tema: str, plataforma: str) -> List[Dict[str, str]]:
    t = tema.strip().rstrip(".")
    if plataforma == "reels":
        return [{"text": f"Nadie te cuenta esto de {t}", "angle": "curiosidad"},
                {"text": f"El error con {t}", "angle": "error comun"},
                {"text": f"{t} en 30 segundos", "angle": "como hacerlo"}]  # fmt: skip
    return [{"text": f"{t}: lo que nadie explica", "angle": "curiosidad"},
            {"text": f"Por qué {t} importa más de lo que crees", "angle": "lo que esta en juego"},
            {"text": f"Cómo entender {t} en 5 pasos", "angle": "numero"},
            {"text": f"El error que todos cometen con {t}", "angle": "error comun"}]  # fmt: skip


def generar(
    tema: str,
    plataforma: str = "youtube",
    *,
    n: int = 5,
    idioma: str = "Spanish",
    tendencias: Iterable[str] = (),
    competencia: Iterable[str] = (),
    ask: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """The *n* best titles for *tema* on *plataforma*, each with its score."""
    plataforma = plataforma if plataforma in LIMITS else "youtube"
    tema = " ".join(str(tema or "").split())[:300]
    if not tema:
        return {"titulos": [], "aviso": "Dígame de qué trata el video."}
    trend = [w for t in tendencias for w in words(t)]
    comp = [clean(c) for c in competencia if c]
    extra = ""
    if trend:
        extra += f"Words trending now (use one only if it fits): {', '.join(sorted(set(trend))[:15])}.\n"
    if comp:
        extra += "Competing titles (do not copy them): " + " | ".join(comp[:8]) + "\n"
    cands: List[Dict[str, str]] = []
    source = "modelo"
    if ask is None:
        try:
            from openjarvis.creator import llm

            def ask(p: str) -> str:
                return llm.ask(p, json_mode=True)
        except Exception:  # noqa: BLE001
            ask = None
    if ask is not None:
        try:
            raw = ask(PROMPT.format(plataforma=plataforma, tema=tema, extra=extra, n=max(16, n * 4),
                                    idioma=idioma, angulos=", ".join(ANGLES), forma=FORMA[plataforma]))  # fmt: skip
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))  # type: ignore[union-attr]
            cands = [c for c in data.get("titles") or [] if isinstance(c, dict)]
        except Exception:  # noqa: BLE001 — no model: templates
            cands = []
    if not cands:
        cands, source = templates(tema, plataforma), "plantillas"
    seen: set = set()
    scored: List[Dict[str, Any]] = []
    for c in cands:
        text = clean(c.get("text") or "")
        if not text or plain(text) in seen:
            continue
        seen.add(plain(text))
        verdict = judge(
            text, tema, plataforma, trend, comp + [s["titulo"] for s in scored]
        )
        scored.append({"titulo": text, "angulo": str(c.get("angle") or ""), **verdict})
    scored.sort(key=lambda s: -s["puntos"])
    best: List[Dict[str, Any]] = []
    angles: Dict[str, int] = {}
    for s in scored:  # variety: at most two of the same angle
        if angles.get(s["angulo"], 0) >= 2:
            continue
        angles[s["angulo"]] = angles.get(s["angulo"], 0) + 1
        best.append(s)
        if len(best) >= n:
            break
    return {"tema": tema, "plataforma": plataforma, "origen": source, "titulos": best,
            "probados": len(scored), "ab": [b["titulo"] for b in best[:2]]}  # fmt: skip


def texto(res: Dict[str, Any]) -> str:
    if not res.get("titulos"):
        return res.get("aviso") or "No pude escribir títulos."
    lines = [
        f"Títulos para {res['plataforma']} ({res['probados']} probados, los mejores):"
    ]
    for t in res["titulos"]:
        lines.append(f"- {t['titulo']} · {t['puntos']}/10 · {', '.join(t['por_que'])}")
    if len(res.get("ab") or []) == 2:
        lines.append(f"Para probar A/B: «{res['ab'][0]}» contra «{res['ab'][1]}».")
    if res.get("origen") == "plantillas":
        lines.append("Sin modelo de IA disponible: son plantillas, revíselas.")
    return "\n".join(lines)


__all__ = ["LIMITS", "clean", "generar", "judge", "texto"]
