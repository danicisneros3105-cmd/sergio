"""Analyze what the camera sees: species, age, gender, expression.

Local-first: OpenCV YuNet finds human faces and the FaceBook names enrolled
people (with consent, as before). A vision model (Kimi → Gemini → Ollama, the
same chain as ``vision_look``) then estimates age, gender and expression per
person and detects animals (dog, cat, bird, …). Everything degrades
gracefully: with no vision model available you still get local face
detection and identity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

KNOWN_SPECIES = (
    "humano",
    "perro",
    "gato",
    "pajaro",
    "caballo",
    "otro_animal",
    "objeto",
    "nadie",
)

ANALYSIS_PROMPT = (
    "Eres el sistema de vision de Sergio, un asistente personal. Analiza la "
    "foto y responde SOLO con un JSON valido, sin markdown ni texto extra, "
    "con esta forma exacta:\n"
    '{"personas": [{"edad_aprox": 30, "rango_edad": "25-35", '
    '"genero": "mujer", "expresion": "sonriendo", "detalle": "..."}], '
    '"animales": [{"especie": "perro", "raza_o_tipo": "labrador", '
    '"detalle": "..."}], '
    '"resumen": "frase corta en espanol"}\n'
    "Reglas:\n"
    "- genero solo puede ser 'hombre', 'mujer' o 'indeterminado'.\n"
    "- edad_aprox es un entero (tu mejor estimacion) o null si no se ve.\n"
    "- rango_edad es un rango razonable, p. ej. '25-35' o '60+'.\n"
    "- Si no hay personas, deja \"personas\" como lista vacia.\n"
    "- especie en minusculas y sin acentos: perro, gato, pajaro, caballo u "
    "otra palabra simple.\n"
    "- No inventes lo que no se ve; ante la duda usa 'indeterminado'/null."
)


@dataclass
class PersonInfo:
    """One detected person with estimated attributes."""

    age: int | None = None
    age_range: str = ""
    gender: str = "indeterminado"  # hombre | mujer | indeterminado
    expression: str = ""
    detail: str = ""
    name: str | None = None  # enrolled identity, matched locally
    box: list[int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "nombre": self.name,
            "edad_aprox": self.age,
            "rango_edad": self.age_range or None,
            "genero": self.gender,
            "expresion": self.expression or None,
            "detalle": self.detail or None,
            "box": self.box,
        }

    def describe(self) -> str:
        parts: list[str] = []
        if self.name:
            parts.append(self.name)
        if self.gender not in ("", "indeterminado"):
            parts.append(self.gender)
        if self.age is not None:
            rango = f" ({self.age_range})" if self.age_range else ""
            parts.append(f"~{self.age} anos{rango}")
        elif self.age_range:
            parts.append(f"edad {self.age_range}")
        if self.expression:
            parts.append(self.expression)
        return ", ".join(parts) if parts else "persona"


@dataclass
class AnimalInfo:
    species: str
    breed: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "especie": self.species,
            "raza_o_tipo": self.breed or None,
            "detalle": self.detail or None,
        }

    def describe(self) -> str:
        base = self.species
        if self.breed:
            base += f" ({self.breed})"
        return base


@dataclass
class SceneAnalysis:
    people: list[PersonInfo] = field(default_factory=list)
    animals: list[AnimalInfo] = field(default_factory=list)
    summary: str = ""
    vision_model_used: bool = False

    @property
    def species(self) -> list[str]:
        found: list[str] = []
        if self.people:
            found.append("humano")
        for animal in self.animals:
            sp = animal.species if animal.species in KNOWN_SPECIES else "otro_animal"
            if sp not in found:
                found.append(sp)
        return found or ["nadie"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "especies": self.species,
            "personas": [p.to_dict() for p in self.people],
            "animales": [a.to_dict() for a in self.animals],
            "resumen": self.to_text(),
            "modelo_vision": self.vision_model_used,
        }

    def to_text(self) -> str:
        if self.summary:
            return self.summary
        parts = [p.describe() for p in self.people]
        parts += [a.describe() for a in self.animals]
        if not parts:
            return "No veo a nadie en la imagen."
        return "Veo: " + "; ".join(parts) + "."


def _parse_analysis(text: str) -> dict[str, Any]:
    """Extract the JSON object from a vision-model answer, tolerantly.

    Models sometimes wrap the JSON in markdown fences or add prose around
    it; we cut from the first ``{`` to the last ``}`` and parse that.
    """
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _people_from_json(data: dict[str, Any]) -> list[PersonInfo]:
    people: list[PersonInfo] = []
    for raw in data.get("personas") or []:
        if not isinstance(raw, dict):
            continue
        age = raw.get("edad_aprox")
        try:
            age = int(age) if age is not None else None
        except (TypeError, ValueError):
            age = None
        gender = str(raw.get("genero") or "indeterminado").strip().lower()
        if gender not in ("hombre", "mujer"):
            gender = "indeterminado"
        people.append(
            PersonInfo(
                age=age,
                age_range=str(raw.get("rango_edad") or "").strip(),
                gender=gender,
                expression=str(raw.get("expresion") or "").strip(),
                detail=str(raw.get("detalle") or "").strip(),
            )
        )
    return people


def _animals_from_json(data: dict[str, Any]) -> list[AnimalInfo]:
    animals: list[AnimalInfo] = []
    for raw in data.get("animales") or []:
        if not isinstance(raw, dict):
            continue
        species = str(raw.get("especie") or "").strip().lower()
        if not species:
            continue
        animals.append(
            AnimalInfo(
                species=species,
                breed=str(raw.get("raza_o_tipo") or "").strip(),
                detail=str(raw.get("detalle") or "").strip(),
            )
        )
    return animals


def analyze(
    image_bytes: bytes,
    *,
    book: Any = None,
    use_vision: bool = True,
    mime: str = "image/jpeg",
) -> SceneAnalysis:
    """Analyze a photo: who's in it, what species, age, gender, expression.

    Identity (names) always comes from the local FaceBook — never from the
    vision model — so a cloud model can never claim to recognize someone.
    """
    if not image_bytes:
        raise ValueError("The image is empty.")

    # 1) Local pass: human faces + enrolled identity (YuNet + SFace).
    matches: list[Any] = []
    try:
        if book is None:
            from openjarvis.faces.book import FaceBook

            book = FaceBook()
        matches = book.identify(image_bytes)
    except Exception:  # noqa: BLE001 — identity is a bonus, never a blocker
        matches = []

    # 2) Vision-model pass: attributes + animals.
    data: dict[str, Any] = {}
    vision_used = False
    if use_vision:
        try:
            from openjarvis.tools.vision_look import ask_image

            raw = ask_image(image_bytes, ANALYSIS_PROMPT, mime=mime)
            data = _parse_analysis(raw)
            vision_used = bool(data)
        except Exception:  # noqa: BLE001 — degrade to local-only results
            data = {}

    people = _people_from_json(data)
    animals = _animals_from_json(data)

    # Merge local identity/boxes into the vision results (best effort: the
    # detector and the vision model see faces in the same scan order).
    for i, match in enumerate(matches):
        name = match.name or None
        box = list(match.box)
        if i < len(people):
            people[i].name = name
            people[i].box = box
        else:
            people.append(PersonInfo(name=name, box=box))

    summary = str(data.get("resumen") or "").strip()
    scene = SceneAnalysis(
        people=people,
        animals=animals,
        summary=summary,
        vision_model_used=vision_used,
    )
    if not scene.summary:
        scene.summary = scene.to_text()
    return scene


__all__ = [
    "ANALYSIS_PROMPT",
    "AnimalInfo",
    "KNOWN_SPECIES",
    "PersonInfo",
    "SceneAnalysis",
    "analyze",
]
