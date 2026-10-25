"""How the owner writes, measured on this computer, so Sergio talks the way he does.

No model and nothing sent anywhere: each message the owner writes updates a few
running averages in ``~/.openjarvis/estilo.json`` — how long his messages are,
whether he says «usted» or «tú», the language, emojis, the hours he writes, the
topics that come back, and what he asked of earlier answers («más corto»,
«explica más»). :func:`block` turns that into a few lines for every turn:
how long to answer, how formal, in what language, and to keep the thread of the
conversation like a person would.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

ALPHA = 0.08  # each new message moves the averages this much (≈ the last 25 count)
MIN_MESSAGES = 5  # before this, too little to say anything about him

_SHORTER = re.compile(
    r"\b(mas corto|más corto|resume|resumen|en breve|sin rollo|al grano|menos texto|shorter|tl;?dr)\b",
    re.I,
)
_LONGER = re.compile(
    r"\b(explica(me)? mas|explica(me)? más|mas detalle|más detalle|profundiza|desarrolla|elabora|more detail)\b",
    re.I,
)
_USTED = re.compile(r"\b(usted|le pido|podria usted|sería tan amable|ud\.)\b", re.I)
_TU = re.compile(r"\b(tu|tú|puedes|quieres|dime|hazme|ayudame|ayúdame|oye)\b", re.I)
_EN = re.compile(r"\b(the|and|please|what|how|can you|is|are)\b", re.I)
_ES = re.compile(r"\b(el|la|que|de|por favor|como|cómo|qué|puedes|quiero)\b", re.I)
_EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿]")
_STOP = set(
    "que de la el en y a los las un una por para con no es lo se me mi del al como mas más pero "
    "sus le ya o este esta eso esto hay muy sin sobre tambien también fue ser son tu te yo "
    "the and to of a in is it for you on with that this be are".split()
)


def _plain(word: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", word.lower())
        if not unicodedata.combining(c)
    )


class Style:
    def __init__(self, path: Path, clock: Any = time.time) -> None:
        self.path = Path(path)
        self.clock = clock
        self._lock = threading.Lock()
        self.data: Dict[str, Any] = {
            "n": 0,
            "palabras": 0.0,
            "usted": 0.5,
            "ingles": 0.0,
            "emoji": 0.0,
            "preguntas": 0.0,
            "largo_pedido": 0.0,  # <0: wants shorter answers, >0: longer
            "horas": [0] * 24,
            "temas": {},
        }
        try:
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def _ema(self, key: str, value: float) -> None:
        n = self.data["n"]
        a = 1.0 / n if n <= int(1 / ALPHA) else ALPHA  # a plain mean at first
        self.data[key] = (1 - a) * float(self.data[key]) + a * value

    def observe(self, text: str) -> None:
        text = (text or "").strip()
        if not text or text.startswith("/") or len(text) > 4000:
            return
        words = re.findall(r"[\wáéíóúñü']+", text, re.I)
        with self._lock:
            self.data["n"] += 1
            self._ema("palabras", float(len(words)))
            u, t = len(_USTED.findall(text)), len(_TU.findall(text))
            if u or t:
                self._ema("usted", 1.0 if u > t else 0.0)
            en, es = len(_EN.findall(text)), len(_ES.findall(text))
            if en or es:
                self._ema("ingles", 1.0 if en > es else 0.0)
            self._ema("emoji", 1.0 if _EMOJI.search(text) else 0.0)
            self._ema("preguntas", 1.0 if "?" in text else 0.0)
            if _SHORTER.search(text):
                self.data["largo_pedido"] = max(-3.0, self.data["largo_pedido"] - 1.0)
            elif _LONGER.search(text):
                self.data["largo_pedido"] = min(3.0, self.data["largo_pedido"] + 1.0)
            else:
                self.data["largo_pedido"] *= 0.97  # an old request fades slowly
            hour = time.localtime(self.clock()).tm_hour
            self.data["horas"][hour] += 1
            topics = Counter(self.data["temas"])
            for w in words:
                p = _plain(w)
                if len(p) >= 5 and p not in _STOP and not p.isdigit():
                    topics[p] += 1
            self.data["temas"] = dict(topics.most_common(60))
            self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def profile(self) -> Dict[str, Any]:
        d = self.data
        hours = d["horas"]
        busiest = max(range(24), key=lambda h: hours[h]) if sum(hours) else None
        if d["largo_pedido"] <= -0.8 or d["palabras"] < 12:
            length = "corto"
        elif d["largo_pedido"] >= 0.8 or d["palabras"] > 60:
            length = "detallado"
        else:
            length = "medio"
        return {
            "mensajes": d["n"],
            "largo": length,
            "trato": "usted" if d["usted"] >= 0.5 else "tú",
            "idioma": "inglés" if d["ingles"] > 0.6 else "español",
            "emojis": d["emoji"] > 0.3,
            "pregunta_mucho": d["preguntas"] > 0.6,
            "hora": busiest,
            "temas": [w for w, _ in Counter(d["temas"]).most_common(5)],
        }

    def block(self) -> str:
        if self.data["n"] < MIN_MESSAGES:
            return ""
        p = self.profile()
        length = {
            "corto": "responda corto: 1 a 3 frases, lo esencial primero",
            "medio": "responda a la medida de la pregunta, sin relleno",
            "detallado": "le gustan las respuestas completas: explique con detalle y ejemplos",
        }[p["largo"]]
        lines = [
            "<estilo_del_dueño>",
            f"- {length}.",
            f"- Él escribe de {p['trato']} y en {p['idioma']}; usted siempre le dice «señor».",
            "- Converse como una persona: siga el hilo de lo dicho antes, sin saludar de nuevo"
            " ni repetir lo que ya sabe; una sola pregunta a la vez, al final y solo si hace falta.",
        ]
        if not p["emojis"]:
            lines.append("- Sin emojis.")
        if p["temas"]:
            lines.append(f"- Temas que le importan: {', '.join(p['temas'])}.")
        lines.append("</estilo_del_dueño>")
        return "\n".join(lines)


def enabled() -> bool:
    """SERGIO_ESTILO=0 turns the measuring off (the tests do, like Terry)."""
    import os

    return os.environ.get("SERGIO_ESTILO", "1").strip() not in ("0", "false", "no")


_STYLES: Dict[str, Style] = {}
_GLOBAL = threading.Lock()


def get_style(home: Optional[Path] = None) -> Style:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    path = Path(home) / "estilo.json"
    with _GLOBAL:
        if str(path) not in _STYLES:
            _STYLES[str(path)] = Style(path)
        return _STYLES[str(path)]


__all__ = ["Style", "enabled", "get_style"]
