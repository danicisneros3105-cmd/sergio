"""Enroll, identify and forget faces (OpenCV YuNet + SFace)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Pinned models: downloaded once, verified by SHA-256 before use.
MODELS = {
    "detector": (
        "face_detection_yunet_2023mar.onnx",
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "recognizer": (
        "face_recognition_sface_2021dec.onnx",
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}

# Cosine-similarity threshold recommended for SFace (higher = same person).
MATCH_THRESHOLD = 0.363
MAX_SAMPLES = 20
MAX_IMAGE_BYTES = 10 * 1024 * 1024
_NAME = re.compile(r"^[\w .'-]{1,60}$", re.UNICODE)


class FaceError(ValueError):
    """A face operation that cannot be done (no face, bad name, …)."""


@dataclass
class Match:
    name: str  # "" when the face does not match anyone enrolled
    score: float
    box: tuple[int, int, int, int]  # x, y, width, height

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name or None,
            "score": round(self.score, 3),
            "box": list(self.box),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(kind: str, models_dir: Path) -> Path:
    name, url, sha = MODELS[kind]
    path = models_dir / name
    if path.exists() and _sha256(path) == sha:
        return path
    models_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=models_dir, suffix=".part")  # unique per call
    tmp = Path(tmp_name)
    try:
        with (
            urllib.request.urlopen(url, timeout=120) as resp,
            os.fdopen(fd, "wb") as out,
        ):  # noqa: S310 — fixed https URL
            while chunk := resp.read(1 << 20):
                out.write(chunk)
        if _sha256(tmp) != sha:
            raise FaceError(f"Downloaded {name} does not match its checksum")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


class FaceBook:
    """People the user enrolled, stored as face embeddings (not photos)."""

    def __init__(self, root: Path | None = None, models_dir: Path | None = None):
        if root is None:
            from openjarvis.core.paths import get_config_dir

            root = get_config_dir() / "faces"
        self._root = Path(root)
        self._models_dir = Path(models_dir) if models_dir else self._root / "models"
        self._lock = threading.Lock()
        self._init_lock = threading.Lock()
        self._detector: Any = None
        self._recognizer: Any = None

    # -- storage -----------------------------------------------------------

    @property
    def _db(self) -> Path:
        return self._root / "people.json"

    def _load(self, *, strict: bool = False) -> dict[str, dict[str, Any]]:
        """Enrolled people. *strict* (write paths) refuses a damaged file
        instead of treating it as empty, so one bad read can never erase
        everyone else on the next save."""
        if not self._db.exists():
            return {}
        try:
            data = json.loads(self._db.read_text())
            if not isinstance(data, dict):
                raise ValueError("not an object")
            return data
        except (OSError, ValueError) as exc:
            if strict:
                raise FaceError(
                    f"{self._db} is damaged ({exc}); restore or delete it."
                ) from exc
            return {}

    def _save(self, people: dict[str, dict[str, Any]]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        tmp = self._db.with_suffix(".tmp")
        tmp.write_text(json.dumps(people))
        tmp.replace(self._db)
        self._db.chmod(0o600)

    def people(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "samples": len(p["embeddings"]),
                "enrolled_at": p["enrolled_at"],
            }
            for name, p in sorted(self._load().items())
        ]

    def forget(self, name: str) -> bool:
        with self._lock:
            people = self._load(strict=True)
            if people.pop(name, None) is None:
                return False
            self._save(people)
            return True

    # -- vision ------------------------------------------------------------

    def _models(self) -> tuple[Any, Any]:
        import cv2

        with self._init_lock:  # first use may download the models
            return self._load_models(cv2)

    def _load_models(self, cv2: Any) -> tuple[Any, Any]:
        if self._detector is None:
            self._detector = cv2.FaceDetectorYN.create(
                str(ensure_model("detector", self._models_dir)), "", (320, 320), 0.8
            )
            self._recognizer = cv2.FaceRecognizerSF.create(
                str(ensure_model("recognizer", self._models_dir)), ""
            )
        return self._detector, self._recognizer

    def _faces(self, image_bytes: bytes) -> list[tuple[Any, tuple[int, int, int, int]]]:
        """Embeddings and boxes of every face in the image."""
        import cv2
        import numpy as np

        if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
            raise FaceError("The image is empty or larger than 10 MB.")
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FaceError("The file is not a readable image.")
        detector, recognizer = self._models()
        with self._lock:  # OpenCV DNN objects are not thread-safe
            height, width = image.shape[:2]
            detector.setInputSize((width, height))
            _, found = detector.detect(image)
            results = []
            for face in found if found is not None else []:
                aligned = recognizer.alignCrop(image, face)
                feature = recognizer.feature(aligned).flatten()
                box = tuple(int(v) for v in face[:4])
                results.append((feature / (np.linalg.norm(feature) + 1e-9), box))
        return results

    def enroll(self, name: str, image_bytes: bytes, *, consent: bool) -> int:
        """Add one photo of *name*; returns the number of stored samples."""
        name = (name or "").strip()
        if not consent:
            raise FaceError(
                "Enroll a person only with their consent (confirm consent=true)."
            )
        if not _NAME.match(name):
            raise FaceError("Use a plain name (letters, spaces, up to 60 characters).")
        faces = self._faces(image_bytes)
        if len(faces) != 1:
            raise FaceError(
                f"The photo must show exactly one face (found {len(faces)})."
            )
        with self._lock:
            people = self._load(strict=True)
            person = people.setdefault(
                name, {"embeddings": [], "enrolled_at": time.time()}
            )
            person["embeddings"] = (person["embeddings"] + [faces[0][0].tolist()])[
                -MAX_SAMPLES:
            ]
            self._save(people)
            return len(person["embeddings"])

    def identify(self, image_bytes: bytes) -> list[Match]:
        import numpy as np

        faces = self._faces(image_bytes)
        people = self._load()
        known = [
            (name, np.asarray(emb, dtype=np.float32))
            for name, p in people.items()
            for emb in p["embeddings"]
        ]
        matches = []
        for feature, box in faces:
            best_name, best = "", -1.0
            for name, emb in known:
                score = float(np.dot(feature, emb))
                if score > best:
                    best_name, best = name, score
            matched = best >= MATCH_THRESHOLD
            matches.append(Match(best_name if matched else "", max(best, 0.0), box))
        return matches


__all__ = ["FaceBook", "FaceError", "MATCH_THRESHOLD", "Match", "ensure_model"]
