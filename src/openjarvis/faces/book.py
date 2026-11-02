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
# This sure, a face is named on the first look (the companion waits for a
# second look below it): naming used to take two looks 1.5 s apart.
STRONG_MATCH = 0.55
STRONG_MARGIN = 0.12
TOP_K = 3
MIN_FACE_PX = 40  # smaller faces are too blurry to name
MIN_DETECTION = 0.85
GUEST_SAME = 0.5  # an unknown face this close to a recent one is the same guest
GUEST_TTL = 1800.0
# Photos per person: a Face ID-style scan stores several per head angle.
MAX_SAMPLES = 40
# Head angles (from YuNet's five points): each photo is filed under one of
# nine angles, so a face turned sideways is compared with that person turned
# sideways (SFace scores fall fast with the angle).
YAW_SIDE = 15.0
PITCH_TILT = 12.0
# Learning by itself while it sees you: only faces it is very sure of, only
# angles it lacks, at most one photo a minute and a few a day per person.
LEARN_MIN = 0.60
LEARN_MARGIN = 0.18
LEARN_GAP = 60.0
LEARN_DAILY = 30
LEARN_PER_ANGLE = 3
LEARN_MIN_PX = 80
# A scan is one continuous head turn by one person: every photo must look
# like the scan's own front photos, and it must cover a few angles.
SCAN_CONSISTENT = 0.25
# One clear angle is enough to start (the front); unlocks teach the rest.
SCAN_MIN_ANGLES = 1
# A setup scan keeps frames a little softer than live naming would.
SCAN_MIN_DETECTION = 0.7
SCAN_PER_ANGLE = 2
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
    margin: float = 0.0  # how far ahead of the next person
    pose: tuple[float, float] = (0.0, 0.0)  # yaw, pitch (degrees)
    learned: bool = False  # this look was added to the person's photos

    @property
    def strong(self) -> bool:
        """Sure enough to name on this one look."""
        return (
            bool(self.name)
            and self.quality == "ok"
            and self.score >= STRONG_MATCH
            and self.margin >= STRONG_MARGIN
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name or None,
            "score": round(self.score, 3),
            "box": list(self.box),
            "guest": self.guest or None,
            "quality": self.quality,
            "margin": round(self.margin, 3),
            "strong": self.strong,
            "angle": angle_of(self.pose),
        }
        if self.learned:
            out["learned"] = True
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


def head_pose(row: Any) -> tuple[float, float]:
    """(yaw, pitch) in degrees from a YuNet detection row (its five points:
    eyes, nose tip, mouth corners). Rough, but plenty to file a photo under
    front / left / right / up / down."""
    import math

    try:
        rx, ry, lx, ly, nx, ny, mrx, mry, mlx, mly = (float(v) for v in row[4:14])
    except (TypeError, ValueError, IndexError):
        return 0.0, 0.0
    # Undo the sideways tilt (roll) first: a tilted head is not looking down.
    roll = math.atan2(ly - ry, lx - rx)
    cx, cy = (rx + lx) / 2, (ry + ly) / 2
    cos, sin = math.cos(-roll), math.sin(-roll)

    def level(x: float, y: float) -> tuple[float, float]:
        dx, dy = x - cx, y - cy
        return cx + dx * cos - dy * sin, cy + dx * sin + dy * cos

    rx, ry = level(rx, ry)
    lx, ly = level(lx, ly)
    nx, ny = level(nx, ny)
    mrx, mry = level(mrx, mry)
    mlx, mly = level(mlx, mly)
    eye_x, eye_y = (rx + lx) / 2, (ry + ly) / 2
    mouth_x, mouth_y = (mrx + mlx) / 2, (mry + mly) / 2
    iod = math.hypot(lx - rx, ly - ry)
    span = mouth_y - eye_y
    if iod < 1.0 or span < 1.0:
        return 0.0, 0.0
    # The nose tip stands ~0.55 eye-distances in front of the face: turning
    # the head moves it off the eyes-mouth midline by 0.55 * tan(yaw).
    yaw = math.degrees(math.atan(((nx - (eye_x + mouth_x) / 2) / iod) / 0.55))
    # Level, the nose tip sits ~57% of the way from the eyes to the mouth.
    pitch = (0.57 - (ny - eye_y) / span) * 120.0
    return round(yaw, 1), round(max(-60.0, min(60.0, pitch)), 1)


def angle_of(pose: Any) -> str:
    """One of nine head angles: "C-M" (front), "L-U" (left and up), ..."""
    try:
        yaw, pitch = float(pose[0]), float(pose[1])
    except (TypeError, ValueError, IndexError):
        return "C-M"
    h = "L" if yaw < -YAW_SIDE else "R" if yaw > YAW_SIDE else "C"
    v = "U" if pitch > PITCH_TILT else "D" if pitch < -PITCH_TILT else "M"
    return f"{h}-{v}"


ANGLE_WORDS = {
    "C-M": "de frente", "L-M": "girado a un lado", "R-M": "girado al otro lado",
    "C-U": "mirando arriba", "C-D": "mirando abajo", "L-U": "arriba a un lado",
    "R-U": "arriba al otro lado", "L-D": "abajo a un lado", "R-D": "abajo al otro lado",
}  # fmt: skip


def looks_old(image: Any) -> bool:
    """Faded, sepia or black-and-white: an old or scanned photo."""
    import numpy as np

    small = image[
        :: max(1, image.shape[0] // 200), :: max(1, image.shape[1] // 200)
    ].astype(np.float32)
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


# The recognition methods live in their own module; they look helpers up here.
from openjarvis.faces.book_identify import _IdentifyMixin  # noqa: E402


class FaceBook(_IdentifyMixin):
    """People the user enrolled, stored as face embeddings (not photos)."""

    def __init__(self, root: Path | None = None, models_dir: Path | None = None):
        if root is None:
            from openjarvis.core.paths import get_config_dir

            root = get_config_dir() / "faces"
        self._root = Path(root)
        self._models_dir = Path(models_dir) if models_dir else self._root / "models"
        self._lock = threading.RLock()
        self._init_lock = threading.Lock()
        self._detector: Any = None
        self._recognizer: Any = None
        self._guests = _Guests()
        self._measurer: Any = None
        self._cache: tuple[int, dict[str, Any]] | None = None
        self._learnt: dict[str, list[float]] = {}  # name -> when it learnt alone

    # -- storage -----------------------------------------------------------

    @property
    def _db(self) -> Path:
        return self._root / "people.json"

    @property
    def _key_path(self) -> Path:
        # Kept away from the faces folder: copying people.json alone (a
        # backup, a sync) reveals nothing without this key (Visage keeps its
        # key in the Secure Enclave; this file is NOT hardware-protected).
        return self._root.parent / "keys" / "faces.key"

    def _cipher(self) -> Any:
        from cryptography.fernet import Fernet

        path = self._key_path
        if not path.exists():
            if self._db.exists() and self._db.read_bytes().startswith(b"gAAAA"):
                raise ValueError("encrypted gallery key is missing")
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.parent.chmod(0o700)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "wb") as out:
                    out.write(Fernet.generate_key())
                    out.flush()
                    os.fsync(out.fileno())
        return Fernet(path.read_bytes().strip())

    def _read_db(self) -> str:
        raw = self._db.read_bytes()
        if raw.startswith(b"gAAAA"):  # encrypted (Fernet token)
            from cryptography.fernet import InvalidToken

            try:
                return self._cipher().decrypt(raw).decode()
            except (InvalidToken, OSError) as exc:
                raise ValueError(f"cannot decrypt ({exc.__class__.__name__})") from exc
        return raw.decode()  # older, plain file: encrypted on the next save

    def _load(self, *, strict: bool = False) -> dict[str, dict[str, Any]]:
        """Enrolled people. *strict* (write paths) refuses a damaged file
        instead of treating it as empty, so one bad read can never erase
        everyone else on the next save."""
        with self._lock:
            if not self._db.exists():
                return {}
            try:
                raw = self._db.read_bytes()
                data = json.loads(self._read_db())
                if not isinstance(data, dict):
                    raise ValueError("not an object")
                cleaned = _tidy(data)
                if not raw.startswith(b"gAAAA") and self._db.read_bytes() == raw:
                    # Encrypt valid legacy data on first use, preserving all
                    # original fields. Corruption never triggers a replacement.
                    self._save(data)
                return cleaned
            except (OSError, ValueError) as exc:
                if strict:
                    raise FaceError(
                        f"{self._db} is damaged ({exc}); restore or delete it."
                    ) from exc
                return {}

    def _save(self, people: dict[str, dict[str, Any]]) -> None:
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._root.chmod(0o700)
        encrypted = self._cipher().encrypt(json.dumps(people, allow_nan=False).encode())
        fd, tmp_name = tempfile.mkstemp(dir=self._root, suffix=".tmp")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(encrypted)
                out.flush()
                os.fsync(out.fileno())
            tmp.replace(self._db)
        finally:
            tmp.unlink(missing_ok=True)
        self._db.chmod(0o600)
        self._cache = None

    def _gallery(self) -> dict[str, Any]:
        """Enrolled people as arrays, read again only when people.json
        changes (it used to be read and repaired on every look)."""
        import numpy as np

        try:
            stamp = self._db.stat().st_mtime_ns
        except OSError:
            return {}
        cached = self._cache
        if cached is not None and cached[0] == stamp:
            return cached[1]
        people = {
            name: np.asarray(p["embeddings"], dtype=np.float32)
            for name, p in self._load().items()
            if p.get("embeddings")
        }
        self._cache = (stamp, people)
        return people

    def people(self) -> list[dict[str, Any]]:
        out = []
        for name, p in sorted(self._load().items()):
            poses = [x for x in p.get("poses") or [] if x]
            out.append(
                {
                    "name": name,
                    "samples": len(p["embeddings"]),
                    "enrolled_at": p["enrolled_at"],
                    "signatures": sum(1 for g in p.get("signatures") or [] if g),
                    "angles": len({angle_of(x) for x in poses}),
                    "scanned": bool(p.get("scanned_at")),
                    "mesh3d": bool(p.get("mesh3d")),
                    "learned": sum(1 for x in p.get("sources") or [] if x == "auto"),
                }
            )
        return out

    def mesh(self, name: str) -> dict[str, Any] | None:
        """The 3D map of a person's face (478 points, millimetres), if scanned."""
        people = self._load()
        key = next((k for k in people if k.lower() == clean_name(name).lower()), "")
        return (people.get(key) or {}).get("mesh3d") if key else None

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

    def _signature(
        self, image: Any, box: tuple[int, int, int, int]
    ) -> list[float] | None:
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

    def _signature_of(
        self, image_bytes: bytes, box: tuple[int, int, int, int]
    ) -> list[float] | None:
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

    def _faces_in(
        self, image: Any
    ) -> list[tuple[Any, tuple[int, int, int, int], float]]:
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
                    (
                        feature / (np.linalg.norm(feature) + 1e-9),
                        box,
                        score,
                        head_pose(face),
                        _sharpness(aligned),
                    )
                )
        return results

    def enroll(
        self,
        name: str,
        image_bytes: bytes,
        *,
        consent: bool,
        faces: list[dict] | None = None,
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
        pose = tuple(found[0][3]) if len(found[0]) > 3 else None
        with self._lock:
            people = self._load(strict=True)
            name = next((k for k in people if k.lower() == name.lower()), name)
            _check_same_person(people, name, found[0][0])
            person = people.setdefault(
                name, {"embeddings": [], "enrolled_at": time.time()}
            )
            _add_samples(person, [(found[0][0].tolist(), geometry, pose, "foto")])
            self._save(people)
            return len(person["embeddings"])


COLUMNS = ("signatures", "poses", "sources")


__all__ = [
    "ANGLE_WORDS",
    "FaceBook",
    "FaceError",
    "MATCH_THRESHOLD",
    "Match",
    "angle_of",
    "head_pose",
    "clean_name",
    "enhance",
    "ensure_model",
    "kin_score",
    "kin_words",
    "looks_old",
    "person_score",
    "purify",
]

# Moved to their own module (it looks its helpers up here).
from openjarvis.faces import book_tidy as _book_tidy  # noqa: E402,I001

_sharpness = _book_tidy._sharpness
_column = _book_tidy._column
_add_samples = _book_tidy._add_samples
_check_same_person = _book_tidy._check_same_person
person_score = _book_tidy.person_score
purify = _book_tidy.purify
_tidy = _book_tidy._tidy
