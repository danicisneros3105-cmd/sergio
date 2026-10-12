"""Background removal with a real segmentation network, on this computer.

GrabCut guesses the subject from colours inside a rectangle and often cuts
heads or keeps the crowd. Here a U²-Net network ("silueta", Apache-2.0 /
MIT, 43 MB) trained for salient-object cut-outs looks at the whole photo and
returns a soft alpha mask in about 3 s on a CPU, with onnxruntime. It is
downloaded once (checksum pinned) into ~/.openjarvis/models; without it
Creator falls back to GrabCut and says so.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any

MODEL = (
    "silueta.onnx",
    "https://github.com/danielgatis/rembg/releases/download/v0.0.0/silueta.onnx",
    "75da6c8d2f8096ec743d071951be73b4a8bc7b3e51d9a6625d63644f90ffeedb",
)
SIZE = 320
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)

_lock = threading.Lock()
_session: Any = None


def models_dir() -> Path:
    from openjarvis.core.paths import get_config_dir

    return Path(get_config_dir()) / "models"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(folder: Path | None = None) -> Path:
    """The network file, downloaded and verified the first time."""
    name, url, sha = MODEL
    folder = folder or models_dir()
    path = folder / name
    if path.exists() and _sha256(path) == sha:
        return path
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=folder, suffix=".part")
    tmp = Path(tmp_name)
    try:
        with (
            urllib.request.urlopen(url, timeout=180) as resp,  # noqa: S310 — fixed https URL
            os.fdopen(fd, "wb") as out,
        ):
            while chunk := resp.read(1 << 20):
                out.write(chunk)
        if _sha256(tmp) != sha:
            raise RuntimeError("el modelo descargado no coincide con su huella")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def _get_session(folder: Path | None = None) -> Any:
    global _session
    with _lock:
        if _session is None:
            import onnxruntime as ort

            _session = ort.InferenceSession(
                str(ensure_model(folder)), providers=["CPUExecutionProvider"]
            )
        return _session


def alpha(image: Any, folder: Path | None = None) -> Any:
    """Soft alpha (0..1 float, image size) for a BGR image."""
    import cv2
    import numpy as np

    session = _get_session(folder)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x = cv2.resize(rgb, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
    x = (x - np.array(MEAN, np.float32)) / np.array(STD, np.float32)
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    out = session.run(None, {session.get_inputs()[0].name: x})[0][0, 0]
    lo, hi = float(out.min()), float(out.max())
    out = (out - lo) / (hi - lo + 1e-8)
    h, w = image.shape[:2]
    a = cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR)
    # A crisper edge without jaggies: stretch the soft ramp a little.
    return np.clip((a - 0.08) / 0.84, 0.0, 1.0)


__all__ = ["MODEL", "alpha", "ensure_model"]
