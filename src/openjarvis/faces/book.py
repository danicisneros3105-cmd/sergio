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
SCAN_MIN_ANGLES = 3
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
        self._cache: tuple[int, dict[str, Any]] | None = None
        self._learnt: dict[str, list[float]] = {}  # name -> when it learnt alone

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

    def scan(
        self,
        name: str,
        images: list[bytes],
        *,
        consent: bool,
        mesh: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """A Face ID-style scan: one person turning their head slowly in a
        circle. The sharpest photos of each head angle are kept, so Sergio
        knows the face from the front, the sides, above and below (and the
        3D map of its 478 points, in millimetres, when the companion sends it).
        """
        import numpy as np

        raw = (name or "").strip()
        name = clean_name(raw)
        if not consent:
            raise FaceError(
                "Enroll a person only with their consent (confirm consent=true)."
            )
        if not _RAW_NAME.match(raw) or not _NAME.match(name):
            raise FaceError("Use a plain name (letters, spaces, up to 60 characters).")
        shots = []
        for data in images[:80]:
            try:
                found = self._faces(data, old=False)
            except FaceError:
                continue
            if not found:
                continue
            found = sorted(found, key=lambda f: f[1][2] * f[1][3], reverse=True)
            feature, box, *rest = found[0]
            if (
                len(found) > 1
                and found[1][1][2] * found[1][1][3] > 0.5 * box[2] * box[3]
            ):
                continue  # two people in the shot: not a scan of one face
            detection = float(rest[0]) if rest else 1.0
            if min(box[2], box[3]) < MIN_FACE_PX or detection < MIN_DETECTION:
                continue
            pose = tuple(rest[1]) if len(rest) > 1 else (0.0, 0.0)
            sharp = float(rest[2]) if len(rest) > 2 else 0.0
            shots.append((feature, pose, sharp))
        if len(shots) < 3:
            raise FaceError(
                "No vi la cara con claridad durante el escaneo: más luz, la cara "
                "entera en la cámara y gira la cabeza despacio."
            )
        front = [f for f, pose, _ in shots if angle_of(pose) == "C-M"] or [
            f for f, _, _ in shots
        ]
        centre = np.mean(np.asarray(front, dtype=np.float32), axis=0)
        centre /= np.linalg.norm(centre) + 1e-9
        shots = [x for x in shots if float(np.dot(x[0], centre)) >= SCAN_CONSISTENT]
        best: dict[str, list[tuple[Any, tuple[float, float], float]]] = {}
        for shot in sorted(shots, key=lambda x: -x[2]):
            kept = best.setdefault(angle_of(shot[1]), [])
            if len(kept) < SCAN_PER_ANGLE:
                kept.append(shot)
        if len(best) < SCAN_MIN_ANGLES:
            raise FaceError(
                f"Solo vi {len(best)} ángulo(s) de la cara: gira la cabeza despacio "
                "en círculo (izquierda, arriba, derecha, abajo) mientras te escaneo."
            )
        with self._lock:
            people = self._load(strict=True)
            name = next((k for k in people if k.lower() == name.lower()), name)
            _check_same_person(people, name, centre)
            person = people.setdefault(
                name, {"embeddings": [], "enrolled_at": time.time()}
            )
            added = [
                (f.tolist(), None, pose, "escaneo")
                for angle in sorted(best)
                for f, pose, _ in best[angle]
            ]
            _add_samples(person, added)
            person["scanned_at"] = time.time()
            if isinstance(mesh, dict) and mesh.get("points"):
                person["mesh3d"] = mesh
            self._save(people)
            total = len(person["embeddings"])
        return {
            "name": name,
            "samples": total,
            "added": len(added),
            "angles": sorted(best),
            "words": [ANGLE_WORDS.get(a, a) for a in sorted(best)],
        }

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
        self,
        image_bytes: bytes,
        *,
        old: bool | None = False,
        candidates: int = 0,
        learn: bool = False,
    ) -> list[Match]:
        """Who is in the image. *learn*: a face it is very sure of, seen from
        an angle it has few photos of, becomes one more photo of that person
        (it keeps learning your face while it sees you)."""
        faces = self._faces(image_bytes, old=old)
        people = self._gallery()
        matches = []
        for feature, box, *rest in faces:
            detection = float(rest[0]) if rest else 1.0
            pose = tuple(rest[1]) if len(rest) > 1 else (0.0, 0.0)
            ranked = sorted(
                ((person_score(feature, embs), name) for name, embs in people.items()),
                reverse=True,
            )
            best, name = ranked[0] if ranked else (0.0, "")
            runner_up = ranked[1][0] if len(ranked) > 1 else -1.0
            margin = best - max(runner_up, 0.0)
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
            guesses = (
                [(n, max(v, 0.0)) for v, n in ranked[:candidates]]
                if candidates
                else None
            )
            if sure:
                match = Match(
                    name,
                    best,
                    box,
                    quality=quality,
                    candidates=guesses,
                    margin=margin,
                    pose=pose,
                )
                if (
                    learn
                    and best >= LEARN_MIN
                    and margin >= LEARN_MARGIN
                    and min(box[2], box[3]) >= LEARN_MIN_PX
                ):
                    match.learned = self._learn(name, feature, pose)
                matches.append(match)
            else:
                guest = self._guests.number(feature) if quality == "ok" else 0
                matches.append(
                    Match(
                        "",
                        max(best, 0.0),
                        box,
                        guest,
                        quality,
                        candidates=guesses,
                        pose=pose,
                    )
                )
        return matches

    def _learn(self, name: str, feature: Any, pose: tuple[float, float]) -> bool:
        """One more photo of *name* from an angle it lacks (rate-limited)."""
        now = time.time()
        stamps = [t for t in self._learnt.get(name, []) if now - t < 86400]
        if (stamps and now - stamps[-1] < LEARN_GAP) or len(stamps) >= LEARN_DAILY:
            return False
        angle = angle_of(pose)
        with self._lock:
            try:
                people = self._load(strict=True)
            except FaceError:
                return False
            person = people.get(name)
            if not person:
                return False
            count = len(person["embeddings"])
            poses = _column(person, "poses", count)
            if sum(1 for x in poses if x and angle_of(x) == angle) >= LEARN_PER_ANGLE:
                return False
            _add_samples(person, [(feature.tolist(), None, pose, "auto")])
            self._save(people)
        self._learnt[name] = stamps + [now]
        return True


def _sharpness(aligned: Any) -> float:
    """How sharp a face crop is (variance of the Laplacian)."""
    try:
        import cv2

        grey = (
            cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY) if aligned.ndim == 3 else aligned
        )
        return float(cv2.Laplacian(grey, cv2.CV_64F).var())
    except Exception:  # noqa: BLE001 — a missing measure only changes the order
        return 0.0


def _column(person: dict[str, Any], key: str, count: int) -> list[Any]:
    """A per-photo list (signatures, poses, sources), as long as the photos."""
    values = list(person.get(key) or [])[:count]
    return values + [None] * (count - len(values))


def _add_samples(
    person: dict[str, Any], items: list[tuple[Any, Any, Any, str]]
) -> None:
    """Append (embedding, signature, pose, source) photos, then trim to
    MAX_SAMPLES: photos it learnt by itself go first, then plain photos,
    and the scan's angles last (they are what covers the whole head)."""
    count = len(person.get("embeddings") or [])
    columns = {
        "embeddings": list(person.get("embeddings") or []),
        "signatures": _column(person, "signatures", count),
        "poses": _column(person, "poses", count),
        "sources": [x or "foto" for x in _column(person, "sources", count)],
    }
    for embedding, signature, pose, source in items:
        columns["embeddings"].append(list(embedding))
        columns["signatures"].append(signature)
        columns["poses"].append(list(pose) if pose is not None else None)
        columns["sources"].append(source)
    while len(columns["embeddings"]) > MAX_SAMPLES:
        sources = columns["sources"]
        drop = next(
            (
                i
                for kind in ("auto", "foto", "escaneo")
                for i, x in enumerate(sources)
                if x == kind
            ),
            0,
        )
        for values in columns.values():
            del values[drop]
    person.update(columns)


def _check_same_person(people: dict[str, Any], name: str, feature: Any) -> None:
    """A new photo of *name* must look like *name*, and not like someone else
    already saved: one wrong photo used to make everyone "Daniel"."""
    import numpy as np

    known = (people.get(name) or {}).get("embeddings") or []
    own = person_score(feature, np.asarray(known, dtype=np.float32)) if known else None
    if own is not None and len(known) >= 2 and own < SAME_PERSON_MIN:
        raise FaceError(
            f"Esa cara no parece de {name} (parecido {own:.2f}). Si es "
            "otra persona, guárdala con su propio nombre."
        )
    for other, person in people.items():
        if other == name or not person.get("embeddings"):
            continue
        theirs = person_score(
            feature, np.asarray(person["embeddings"], dtype=np.float32)
        )
        # Near-certain only (siblings sit lower): twins can still be saved.
        if theirs >= STRONG_MATCH and (own is None or theirs > own + MATCH_MARGIN):
            raise FaceError(
                f"Esa cara ya está guardada como {other} (parecido {theirs:.2f}). "
                f"Si de verdad es {name}, que se ponga frente a la cámara a solas."
            )


def person_score(feature: Any, embeddings: Any) -> float:
    """How much a face looks like a person: mean of their best TOP_K photos."""
    import numpy as np

    scores = np.sort(embeddings @ feature)[::-1]
    return float(np.mean(scores[:TOP_K]))


def purify(
    embeddings: list, *columns: list, together: list[int] | None = None
) -> tuple[list, ...]:
    """Keep only one person's photos: the biggest group of photos that look
    alike (ties: the group with the oldest photo, the one enrolled first).
    Repairs a person that got other people's faces saved under their name.
    *columns* (signatures, poses, ...) are filtered the same way.
    *together*: photos known to be one person (a scan: one continuous head
    turn); a profile looks little like a front photo, but it is not a
    stranger."""
    import numpy as np

    n = len(embeddings)
    if n < 3:
        return (embeddings, *columns)
    e = np.asarray(embeddings, dtype=np.float32)
    e = e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-9)
    linked = (e @ e.T) >= CLUSTER_LINK
    if together:
        idx = [i for i in together if 0 <= i < n]
        linked[np.ix_(idx, idx)] = True
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
        return (embeddings, *columns)
    idx = [i for i in range(n) if group[i] == keep]
    return (
        [embeddings[i] for i in idx],
        *([column[i] for i in idx] for column in columns),
    )


COLUMNS = ("signatures", "poses", "sources")


def _tidy(people: dict[str, Any]) -> dict[str, Any]:
    """Clean names ('Daniel Cisneros .' -> 'Daniel Cisneros'), merging twins,
    and drop faces of other people saved by mistake under a name."""
    out: dict[str, Any] = {}
    for raw, person in people.items():
        name = clean_name(raw) or raw
        key = next((k for k in out if k.lower() == name.lower()), name)
        embs = list(person.get("embeddings") or [])
        cols = {c: _column(person, c, len(embs)) for c in COLUMNS}
        if key in out:
            out[key]["embeddings"] = out[key]["embeddings"] + embs
            for c in COLUMNS:
                out[key][c] = out[key][c] + cols[c]
            for extra in ("mesh3d", "scanned_at"):
                if person.get(extra) and not out[key].get(extra):
                    out[key][extra] = person[extra]
        else:
            out[key] = {**person, "embeddings": embs, **cols}
    for person in out.values():
        try:
            scanned = [i for i, x in enumerate(person["sources"]) if x == "escaneo"]
            embs, *cols = purify(
                person["embeddings"], *(person[c] for c in COLUMNS), together=scanned
            )
            person["embeddings"] = embs
            person.update(dict(zip(COLUMNS, cols)))
        except (ValueError, TypeError):  # odd shapes: leave as they are
            pass
        if (
            len(person["embeddings"]) > MAX_SAMPLES
        ):  # merged twins: trim like new photos
            extra = person["embeddings"]
            person["embeddings"] = []
            cols = {c: person[c] for c in COLUMNS}
            for c in COLUMNS:
                person[c] = []
            _add_samples(
                person,
                [
                    (
                        extra[i],
                        cols["signatures"][i],
                        cols["poses"][i],
                        cols["sources"][i] or "foto",
                    )
                    for i in range(len(extra))
                ],
            )
    return out


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
