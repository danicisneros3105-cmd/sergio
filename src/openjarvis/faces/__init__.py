"""Local face recognition for Sergio (people the user enrolls, with consent).

Everything runs on the user's computer with OpenCV's YuNet face detector
(MIT) and SFace face recognizer (Apache-2.0). Only people the user enrolls
are recognized; everyone else is reported as unknown. Enrollment is a human
action (web UI or CLI) — the assistant can identify faces but cannot enroll
new people on its own.

``analyze`` adds scene understanding on top: species (human / dog / cat …),
approximate age, gender and expression, using a vision model while identity
always stays local.
"""

from openjarvis.faces.analyze import (
    AnimalInfo,
    PersonInfo,
    SceneAnalysis,
    analyze,
)
from openjarvis.faces.book import FaceBook, FaceError, Match

__all__ = [
    "AnimalInfo",
    "FaceBook",
    "FaceError",
    "Match",
    "PersonInfo",
    "SceneAnalysis",
    "analyze",
]
