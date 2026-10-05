"""Enroll, identify and forget faces (OpenCV YuNet + SFace + face geometry).

Each person keeps, per photo, two descriptions of the face:

* a deep embedding (SFace: 128 numbers learnt from millions of faces) that
  decides who someone is, and
* a geometric signature (``signature.py``: 175 craniofacial measurements
  from MediaPipe's 478-point 3D mesh) that adds evidence, helps with old
  photos and drives the family-resemblance estimate.

Old, faded or scanned photos are contrast-equalised (CLAHE) before reading
them, which measurably raises the match of the same face (see the tests).
"""

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

# Cosine similarity (SFace) needed to say "this is <name>". OpenCV's 0.363 is
# for comparing two photos; Sergio compares a webcam face with every photo
# of every enrolled person, so a single lucky photo used to make strangers
# "Daniel". Now a person's score is the mean of their best 3 photos, it must
# reach MATCH_THRESHOLD and beat the next person by MATCH_MARGIN.
MATCH_THRESHOLD = 0.42
MATCH_MARGIN = 0.06
TOP_K = 3
MIN_FACE_PX = 40  # smaller faces are too blurry to name
MIN_DETECTION = 0.85
GUEST_SAME = 0.5  # an unknown face this close to a recent one is the same guest
GUEST_TTL = 1800.0
MAX_SAMPLES = 20
# A new photo saved under a name must look like that person's photos: one
# stranger saved as "Daniel" used to make everyone "Daniel" afterwards.
SAME_PERSON_MIN = 0.30
CLUSTER_LINK = 0.36  # two photos this alike are the same person (SFace)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
_NAME = re.compile(r"^[\w .'-]{1,60}$", re.UNICODE)
_RAW_NAME = re.compile(r"^[\w .,'-]{1,80}$", re.UNICODE)  # before cleaning
_LOWER = {"de", "del", "la", "las", "los", "y", "da", "do", "dos", "van", "von"}


def clean_name(name: str) -> str:
    """'daniel cisneros .' -> 'Daniel Cisneros' (as people write names)."""
    words = re.sub(r"[^\w' -]", " ", name or "", flags=re.UNICODE).split()
    out = []
    for i, word in enumerate(words):
        low = word.lower()
        out.append(low if i and low in _LOWER else low[:1].upper() + low[1:])
    return " ".join(out)[:60]


class FaceError(ValueError):
    """A face operation that cannot be done (no face, bad name, …)."""


@dataclass
class Match:
    name: str  # "" when the face does not match anyone enrolled
    score: float
    box: tuple[int, int, int, int]  # x, y, width, height
    guest: int = 0  # unknown faces: the same stranger keeps the same number
    quality: str = "ok"  # "pequeña" / "borrosa": too poor to name
    geometry: float | None = None  # 0..1 likeness of the 175 measurements
    candidates: list[tuple[str, float]] | None = None  # best guesses, for photos

    def to_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name or None,
            "score": round(self.score, 3),
            "box": list(self.box),
            "guest": self.guest or None,
            "quality": self.quality,
        }
        if self.geometry is not None:
            out["geometry"] = round(self.geometry, 3)
        if self.candidates is not None:
            out["candidates"] = [[n, round(v, 3)] for n, v in self.candidates]
        return out


# Family resemblance: relatives' deep embeddings sit between strangers
# (~0.1) and the same person (> 0.42); bone proportions add the rest.
KIN_LOW, KIN_HIGH = 0.12, 0.40


def kin_score(sface: float, geometry: float | None) -> float:
    """0..1 family resemblance from the two descriptions of two faces."""
    deep = min(1.0, max(0.0, (sface - KIN_LOW) / (KIN_HIGH - KIN_LOW)))
    if geometry is None:
        return deep
    return 0.65 * deep + 0.35 * geometry


def kin_words(score: float) -> str:
    if score >= 0.65:
        return "parecido familiar alto"
    if score >= 0.45:
        return "parecido familiar moderado"
    if score >= 0.25:
        return "parecido familiar bajo"
    return "sin parecido familiar claro"


def looks_old(image: Any) -> bool:
    """Faded, sepia or black-and-white: an old or scanned photo."""
    import numpy as np

    small = image[:: max(1, image.shape[0] // 200), :: max(1, image.shape[1] // 200)].astype(np.float32)
    colour = float(np.mean(np.std(small, axis=2)))  # ~0 for grey/sepia-ish
    contrast = float(np.std(small.mean(axis=2)))
    return colour < 12.0 or contrast < 38.0


def enhance(image: Any) -> Any:
    """Equalise contrast locally (CLAHE) on the lightness channel."""
    import cv2

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)
    light = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(light)
    return cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)


class _Guests:
    """Strangers seen recently, so "Persona 2" stays "Persona 2"."""

    def __init__(self) -> None:
        self._seen: list[tuple[int, Any, float]] = []  # (number, embedding, time)
        self._next = 1

    def number(self, feature: Any) -> int:
        import numpy as np

        now = time.monotonic()
        self._seen = [g for g in self._seen if now - g[2] < GUEST_TTL]
        best, best_score = None, GUEST_SAME
        for i, (_n, emb, _t) in enumerate(self._seen):
            score = float(np.dot(feature, emb))
            if score >= best_score:
                best, best_score = i, score
        if best is not None:
            n, emb, _t = self._seen[best]
            self._seen[best] = (n, emb, now)
            return n
        if not self._seen:
            self._next = 1  # nobody around for a while: numbering restarts
        n = self._next
        self._next += 1
        self._seen.append((n, feature, now))
        return n


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
        self._guests = _Guests()
        self._measurer: Any = None

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
            return _tidy(data)
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
                "signatures": sum(1 for g in p.get("signatures") or [] if g),
            }
            for name, p in sorted(self._load().items())
        ]

    def forget(self, name: str) -> bool:
        with self._lock:
            people = self._load(strict=True)
            key = next(
                (k for k in people if k.lower() == clean_name(name).lower()), name
            )
            if people.pop(key, None) is None:
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

    def _decode(self, image_bytes: bytes) -> Any:
        import cv2
        import numpy as np

        if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
            raise FaceError("The image is empty or larger than 10 MB.")
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FaceError("The file is not a readable image.")
        return image

    def _signature(self, image: Any, box: tuple[int, int, int, int]) -> list[float] | None:
        """The 175 measurements (None when MediaPipe is not installed)."""
        if self._measurer is None:
            from openjarvis.faces.signature import Measurer

            self._measurer = Measurer(self._models_dir)
        try:
            with self._lock:
                return self._measurer.signature(image, box)
        except Exception:  # noqa: BLE001 — geometry is extra evidence only
            return None

    def _measured(
        self, box: tuple[int, int, int, int], faces: list[dict] | None
    ) -> list[float] | None:
        """The 175 measurements from the points the companion measured."""
        if not faces:
            return None
        from openjarvis.faces.signature import from_points, match_points

        face = match_points(box, faces)
        return from_points(face.get("points") or {}) if face else None

    def _signature_of(self, image_bytes: bytes, box: tuple[int, int, int, int]) -> list[float] | None:
        try:
            image = self._decode(image_bytes)
        except FaceError:
            return None
        return self._signature(enhance(image) if looks_old(image) else image, box)

    def _faces(
        self, image_bytes: bytes, *, old: bool | None = False, image: Any = None
    ) -> list[tuple[Any, tuple[int, int, int, int], float]]:
        """Embeddings, boxes and detection scores of every face in the image.

        *old*: True = always enhance, None = enhance if it looks old.
        """
        image = self._decode(image_bytes) if image is None else image
        if old or (old is None and looks_old(image)):
            image = enhance(image)
        return self._faces_in(image)

    def _faces_in(self, image: Any) -> list[tuple[Any, tuple[int, int, int, int], float]]:
        import numpy as np

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
                score = float(face[14]) if len(face) > 14 else 1.0
                results.append(
                    (feature / (np.linalg.norm(feature) + 1e-9), box, score)
                )
        return results

    def enroll(
        self, name: str, image_bytes: bytes, *, consent: bool, faces: list[dict] | None = None
    ) -> int:
        """Add one photo of *name*; returns the number of stored samples."""
        raw = (name or "").strip()
        name = clean_name(raw)
        if not consent:
            raise FaceError(
                "Enroll a person only with their consent (confirm consent=true)."
            )
        if not _RAW_NAME.match(raw) or not _NAME.match(name):
            raise FaceError("Use a plain name (letters, spaces, up to 60 characters).")
        found = self._faces(image_bytes, old=None)  # old photos are fine too
        if len(found) != 1:
            raise FaceError(
                f"The photo must show exactly one face (found {len(found)})."
            )
        geometry = self._measured(found[0][1], faces) or self._signature_of(
            image_bytes, found[0][1]
        )
        with self._lock:
            people = self._load(strict=True)
            name = next((k for k in people if k.lower() == name.lower()), name)
            known = (people.get(name) or {}).get("embeddings") or []
            if len(known) >= 2:
                import numpy as np

                alike = person_score(found[0][0], np.asarray(known, dtype=np.float32))
                if alike < SAME_PERSON_MIN:
                    raise FaceError(
                        f"Esa cara no parece de {name} (parecido {alike:.2f}). Si es "
                        "otra persona, guárdala con su propio nombre."
                    )
            person = people.setdefault(
                name, {"embeddings": [], "enrolled_at": time.time()}
            )
            count = len(person["embeddings"])
            signatures = list(person.get("signatures") or [None] * count)[:count]
            signatures += [None] * (count - len(signatures))
            person["embeddings"] = (person["embeddings"] + [found[0][0].tolist()])[
                -MAX_SAMPLES:
            ]
            person["signatures"] = (signatures + [geometry])[-MAX_SAMPLES:]
            self._save(people)
            return len(person["embeddings"])

    def _person_signatures(self) -> dict[str, list[float]]:
        """Each person's mean signature (their stable proportions)."""
        out = {}
        for name, p in self._load().items():
            sigs = [g for g in p.get("signatures") or [] if g]
            if sigs:
                out[name] = [sum(col) / len(sigs) for col in zip(*sigs)]
        return out

    def identify_photo(
        self, image_bytes: bytes, faces: list[dict] | None = None
    ) -> list[Match]:
        """Who is in a photo (also an old, faded or scanned one).

        Same decision as the camera, plus the three best guesses and the
        likeness of the 175 measurements for each face.
        """
        from openjarvis.faces.signature import similarity

        image = self._decode(image_bytes)
        old = looks_old(image)
        matches = self.identify(image_bytes, old=old, candidates=3)
        if matches:
            signatures = self._person_signatures()
            seen = enhance(image) if old else image
            for m in matches:
                geometry = self._measured(m.box, faces) or self._signature(seen, m.box)
                best = m.name or (m.candidates[0][0] if m.candidates else "")
                if geometry is not None and best in signatures:
                    m.geometry = similarity(geometry, signatures[best])
        return matches

    def kinship(
        self, image_bytes: bytes, faces: list[dict] | None = None
    ) -> list[dict[str, Any]]:
        """Family resemblance of each face in the photo with everyone enrolled."""
        import numpy as np

        from openjarvis.faces.signature import similarity

        image = self._decode(image_bytes)
        old = looks_old(image)
        seen = enhance(image) if old else image
        found = self._faces_in(seen)
        people = {
            name: np.asarray(p["embeddings"], dtype=np.float32)
            for name, p in self._load().items()
            if p.get("embeddings")
        }
        signatures = self._person_signatures()
        out = []
        for feature, box, _score in found:
            geometry = self._measured(box, faces) or self._signature(seen, box)
            ranked = []
            for name, embs in people.items():
                deep = person_score(feature, embs)
                geo = (
                    similarity(geometry, signatures[name])
                    if geometry is not None and name in signatures
                    else None
                )
                same = deep >= MATCH_THRESHOLD
                kin = kin_score(deep, geo)
                ranked.append(
                    {
                        "name": name,
                        "same_person": same,
                        "deep": round(deep, 3),
                        "geometry": None if geo is None else round(geo, 3),
                        "kin": round(kin, 3),
                        "words": "es la misma persona" if same else kin_words(kin),
                    }
                )
            ranked.sort(key=lambda r: (r["same_person"], r["kin"]), reverse=True)
            out.append({"box": list(box), "old_photo": old, "people": ranked})
        return out

    def identify(
        self, image_bytes: bytes, *, old: bool | None = False, candidates: int = 0
    ) -> list[Match]:
        import numpy as np

        faces = self._faces(image_bytes, old=old)
        people = {
            name: np.asarray(p["embeddings"], dtype=np.float32)
            for name, p in self._load().items()
            if p.get("embeddings")
        }
        matches = []
        for feature, box, *rest in faces:
            detection = float(rest[0]) if rest else 1.0
            ranked = sorted(
                ((person_score(feature, embs), name) for name, embs in people.items()),
                reverse=True,
            )
            best, name = ranked[0] if ranked else (0.0, "")
            runner_up = ranked[1][0] if len(ranked) > 1 else -1.0
            quality = "ok"
            if min(box[2], box[3]) < MIN_FACE_PX:
                quality = "pequeña"
            elif detection < MIN_DETECTION:
                quality = "borrosa"
            sure = (
                quality == "ok"
                and best >= MATCH_THRESHOLD
                and best - runner_up >= MATCH_MARGIN
            )
            guesses = [(n, max(v, 0.0)) for v, n in ranked[:candidates]] if candidates else None
            if sure:
                matches.append(Match(name, best, box, quality=quality, candidates=guesses))
            else:
                guest = self._guests.number(feature) if quality == "ok" else 0
                matches.append(
                    Match("", max(best, 0.0), box, guest, quality, candidates=guesses)
                )
        return matches


def person_score(feature: Any, embeddings: Any) -> float:
    """How much a face looks like a person: mean of their best TOP_K photos."""
    import numpy as np

    scores = np.sort(embeddings @ feature)[::-1]
    return float(np.mean(scores[:TOP_K]))


def purify(embeddings: list, signatures: list) -> tuple[list, list]:
    """Keep only one person's photos: the biggest group of photos that look
    alike (ties: the group with the oldest photo, the one enrolled first).
    Repairs a person that got other people's faces saved under their name."""
    import numpy as np

    n = len(embeddings)
    if n < 3:
        return embeddings, signatures
    e = np.asarray(embeddings, dtype=np.float32)
    e = e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-9)
    linked = (e @ e.T) >= CLUSTER_LINK
    group = [-1] * n
    for start in range(n):
        if group[start] >= 0:
            continue
        group[start], stack = start, [start]
        while stack:
            i = stack.pop()
            for j in np.flatnonzero(linked[i]):
                if group[j] < 0:
                    group[j] = start
                    stack.append(int(j))
    sizes = {g: group.count(g) for g in set(group)}
    keep = max(sizes, key=lambda g: (sizes[g], -g))
    if sizes[keep] == n:
        return embeddings, signatures
    idx = [i for i in range(n) if group[i] == keep]
    return [embeddings[i] for i in idx], [signatures[i] for i in idx]


def _tidy(people: dict[str, Any]) -> dict[str, Any]:
    """Clean names ('Daniel Cisneros .' -> 'Daniel Cisneros'), merging twins,
    and drop faces of other people saved by mistake under a name."""
    out: dict[str, Any] = {}
    for raw, person in people.items():
        name = clean_name(raw) or raw
        key = next((k for k in out if k.lower() == name.lower()), name)
        embs = list(person.get("embeddings") or [])
        sigs = list(person.get("signatures") or [])[: len(embs)]
        sigs += [None] * (len(embs) - len(sigs))
        if key in out:
            out[key]["embeddings"] = (out[key]["embeddings"] + embs)[-MAX_SAMPLES:]
            out[key]["signatures"] = (out[key]["signatures"] + sigs)[-MAX_SAMPLES:]
        else:
            out[key] = {**person, "embeddings": embs, "signatures": sigs}
    for person in out.values():
        try:
            person["embeddings"], person["signatures"] = purify(
                person["embeddings"], person["signatures"]
            )
        except (ValueError, TypeError):  # odd shapes: leave as they are
            pass
    return out


__all__ = [
    "FaceBook",
    "FaceError",
    "MATCH_THRESHOLD",
    "Match",
    "clean_name",
    "enhance",
    "ensure_model",
    "kin_score",
    "kin_words",
    "looks_old",
    "person_score",
    "purify",
]
