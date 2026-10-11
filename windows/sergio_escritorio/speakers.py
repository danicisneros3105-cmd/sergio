"""Who is talking: voiceprints of the people Sergio knows.

A speaker-recognition network (ECAPA-TDNN, trained on VoxCeleb2's 6,000
voices; MIT licence, github.com/TaoRuijie/ECAPA-TDNN) turns a second or two
of speech into 192 numbers that describe the voice, not the words: the same
person saying different things lands close, two people apart. Sergio uses it
to:

* know whether the owner («señor») or someone else in the room is talking,
  and tell the live conversation, so he does not answer people who are
  talking to each other;
* label who said what when he summarises a conversation or a meeting.

Voices are learnt only when asked («aprende mi voz», «aprende la voz de
Ana») and kept on this computer as numbers, never as recordings.

The network runs with PyTorch (installed with Sergio's vision); the model
(67 MB) is downloaded once and checked by SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

log = logging.getLogger(__name__)

RATE = 16_000
MODEL_NAME = "ecapa-tdnn-voxceleb2.model"
MODEL_URL = "https://raw.githubusercontent.com/TaoRuijie/ECAPA-TDNN/main/exps/pretrain.model"
MODEL_SHA256 = "a435faa17622a6bf99db8ec6fb51aafe41eb5396d3d1b837eed7e74af8c5d64f"
HOME = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SergioEscritorio"
# Cosine similarity of two voiceprints (calibrated on LibriSpeech, see
# tests and LEEME): this much and the voice is that person's...
SAME_VOICE = 0.36
SAME_VOICE_LONG = 0.40  # two seconds of speech or more: a stricter bar
# ...and ahead of the next person by this much (no coin tosses).
VOICE_MARGIN = 0.08
TOP_K = 3
MIN_SECONDS = 1.0  # shorter speech says too little about the voice
MAX_PRINTS = 30  # voiceprints kept per person


# -- the network -----------------------------------------------------------------------
def _build(torch: Any) -> Any:
    """ECAPA-TDNN (C=1024), as in TaoRuijie/ECAPA-TDNN (MIT), with its own
    log-Mel front end (no torchaudio needed: the filters ship in the model)."""
    nn = torch.nn
    functional = torch.nn.functional

    class SEModule(nn.Module):
        def __init__(self, channels: int, bottleneck: int = 128) -> None:
            super().__init__()
            self.se = nn.Sequential(
                nn.AdaptiveAvgPool1d(1),
                nn.Conv1d(channels, bottleneck, kernel_size=1, padding=0),
                nn.ReLU(),
                nn.Conv1d(bottleneck, channels, kernel_size=1, padding=0),
                nn.Sigmoid(),
            )

        def forward(self, x: Any) -> Any:
            return x * self.se(x)

    class Bottle2neck(nn.Module):
        def __init__(self, inplanes: int, planes: int, kernel_size: int, dilation: int, scale: int = 8) -> None:
            super().__init__()
            width = int(math.floor(planes / scale))
            self.conv1 = nn.Conv1d(inplanes, width * scale, kernel_size=1)
            self.bn1 = nn.BatchNorm1d(width * scale)
            self.nums = scale - 1
            pad = math.floor(kernel_size / 2) * dilation
            self.convs = nn.ModuleList(
                [nn.Conv1d(width, width, kernel_size=kernel_size, dilation=dilation, padding=pad) for _ in range(self.nums)]
            )
            self.bns = nn.ModuleList([nn.BatchNorm1d(width) for _ in range(self.nums)])
            self.conv3 = nn.Conv1d(width * scale, planes, kernel_size=1)
            self.bn3 = nn.BatchNorm1d(planes)
            self.relu = nn.ReLU()
            self.width = width
            self.se = SEModule(planes)

        def forward(self, x: Any) -> Any:
            residual = x
            out = self.bn1(self.relu(self.conv1(x)))
            spx = torch.split(out, self.width, 1)
            sp = None
            parts = []
            for i in range(self.nums):
                sp = spx[i] if i == 0 else sp + spx[i]
                sp = self.bns[i](self.relu(self.convs[i](sp)))
                parts.append(sp)
            out = torch.cat(parts + [spx[self.nums]], 1)
            out = self.bn3(self.relu(self.conv3(out)))
            return self.se(out) + residual

    class Fbank(nn.Module):
        """Pre-emphasis + 80 log-Mel bands (25 ms windows every 10 ms)."""

        def __init__(self) -> None:
            super().__init__()
            self.register_buffer("flipped_filter", torch.FloatTensor([-0.97, 1.0]).view(1, 1, 2))
            self.register_buffer("window", torch.hamming_window(400))
            self.register_buffer("fb", torch.zeros(257, 80))

        def forward(self, x: Any) -> Any:
            x = functional.conv1d(functional.pad(x.unsqueeze(1), (1, 0), "reflect"), self.flipped_filter).squeeze(1)
            spec = torch.stft(
                x, n_fft=512, hop_length=160, win_length=400, window=self.window,
                center=True, pad_mode="reflect", normalized=False, onesided=True, return_complex=True,
            )
            power = spec.abs() ** 2  # (batch, 257, frames)
            mel = torch.matmul(power.transpose(1, 2), self.fb).transpose(1, 2)
            mel = torch.log(mel + 1e-6)
            return mel - mel.mean(dim=-1, keepdim=True)

    class ECAPA(nn.Module):
        def __init__(self, c: int = 1024) -> None:
            super().__init__()
            self.fbank = Fbank()
            self.conv1 = nn.Conv1d(80, c, kernel_size=5, stride=1, padding=2)
            self.relu = nn.ReLU()
            self.bn1 = nn.BatchNorm1d(c)
            self.layer1 = Bottle2neck(c, c, kernel_size=3, dilation=2)
            self.layer2 = Bottle2neck(c, c, kernel_size=3, dilation=3)
            self.layer3 = Bottle2neck(c, c, kernel_size=3, dilation=4)
            self.layer4 = nn.Conv1d(3 * c, 1536, kernel_size=1)
            self.attention = nn.Sequential(
                nn.Conv1d(4608, 256, kernel_size=1),
                nn.ReLU(),
                nn.BatchNorm1d(256),
                nn.Tanh(),
                nn.Conv1d(256, 1536, kernel_size=1),
                nn.Softmax(dim=2),
            )
            self.bn5 = nn.BatchNorm1d(3072)
            self.fc6 = nn.Linear(3072, 192)
            self.bn6 = nn.BatchNorm1d(192)

        def forward(self, wav: Any) -> Any:
            x = self.fbank(wav)
            x = self.bn1(self.relu(self.conv1(x)))
            x1 = self.layer1(x)
            x2 = self.layer2(x + x1)
            x3 = self.layer3(x + x1 + x2)
            x = self.relu(self.layer4(torch.cat((x1, x2, x3), dim=1)))
            t = x.size()[-1]
            context = torch.cat(
                (
                    x,
                    torch.mean(x, dim=2, keepdim=True).repeat(1, 1, t),
                    torch.sqrt(torch.var(x, dim=2, keepdim=True).clamp(min=1e-4)).repeat(1, 1, t),
                ),
                dim=1,
            )
            w = self.attention(context)
            mu = torch.sum(x * w, dim=2)
            sg = torch.sqrt((torch.sum((x**2) * w, dim=2) - mu**2).clamp(min=1e-4))
            x = self.bn5(torch.cat((mu, sg), 1))
            return self.bn6(self.fc6(x))

    return ECAPA()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(folder: Path | None = None, fetch: Callable[[str, Path], None] | None = None) -> Path:
    """The model file, downloaded once (67 MB) and checked."""
    folder = folder or HOME / "models"
    path = folder / MODEL_NAME
    if path.exists() and path.stat().st_size > 60_000_000:
        return path
    folder.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    if fetch is not None:
        fetch(MODEL_URL, tmp)
    else:
        import httpx

        with httpx.stream("GET", MODEL_URL, timeout=300, follow_redirects=True) as resp:
            resp.raise_for_status()
            with tmp.open("wb") as out:
                for chunk in resp.iter_bytes():
                    out.write(chunk)
    if _sha256(tmp) != MODEL_SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("El modelo de voces descargado no coincide con su huella (SHA-256).")
    tmp.replace(path)
    return path


class Encoder:
    """Speech (16 kHz) -> a voiceprint: 192 numbers, length 1."""

    def __init__(self, model_path: Path | None = None, device: str = "cpu") -> None:
        import torch

        self._torch = torch
        self.device = device
        net = _build(torch)
        state = torch.load(
            str(model_path or ensure_model()), map_location="cpu", weights_only=True
        )
        own = {}
        for key, value in state.items():
            if not key.startswith("speaker_encoder."):
                continue  # the training head
            key = key[len("speaker_encoder.") :]
            key = key.replace("torchfbank.0.flipped_filter", "fbank.flipped_filter")
            key = key.replace("torchfbank.1.spectrogram.window", "fbank.window")
            key = key.replace("torchfbank.1.mel_scale.fb", "fbank.fb")
            own[key] = value
        net.load_state_dict(own, strict=True)
        net.eval()
        self.net = net.to(device)
        self._lock = threading.Lock()

    def embed(self, samples: Any) -> Any:
        """float32 samples in -1..1 at 16 kHz -> unit-length voiceprint."""
        import numpy as np

        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if audio.size < int(RATE * 0.5):
            raise ValueError("Muy poco audio para reconocer una voz.")
        torch = self._torch
        with self._lock, torch.no_grad():
            wav = torch.from_numpy(audio).unsqueeze(0).to(self.device)
            out = self.net(wav)[0].float().cpu().numpy()
        return out / (np.linalg.norm(out) + 1e-9)


def pcm_to_float(pcm: bytes) -> Any:
    import numpy as np

    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def voiced(samples: Any, frame: int = 480, floor: float = 0.0) -> Any:
    """Only the frames with speech (simple energy gate): pauses and room
    noise say nothing about who is talking."""
    import numpy as np

    audio = np.asarray(samples, dtype=np.float32)
    n = audio.size // frame
    if n == 0:
        return audio
    frames = audio[: n * frame].reshape(n, frame)
    energy = np.sqrt(np.mean(frames**2, axis=1))
    threshold = max(floor, float(np.percentile(energy, 20)) * 2.5, 0.004)
    keep = energy > threshold
    return frames[keep].reshape(-1) if keep.any() else audio[:0]


# -- people ------------------------------------------------------------------------------
@dataclass
class Voice:
    name: str  # "" = nobody enrolled sounds like this
    score: float
    margin: float = 0.0
    owner: bool = False
    candidate: str = ""  # the closest person, even when not sure enough

    @property
    def known(self) -> bool:
        return bool(self.name)


def person_score(print_: Any, prints: Any) -> float:
    """Likeness to a person: mean of their TOP_K closest voiceprints."""
    import numpy as np

    scores = np.sort(np.asarray(prints, dtype=np.float32) @ np.asarray(print_, dtype=np.float32))[::-1]
    return float(np.mean(scores[:TOP_K]))


class VoiceBook:
    """Voiceprints of the people Sergio was asked to learn (no recordings)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or HOME / "voces.json"
        self._lock = threading.Lock()
        self._people: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._people is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._people = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._people = {}
        return self._people

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._people or {}), encoding="utf-8")
        tmp.replace(self.path)

    def people(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"name": name, "prints": len(p.get("prints") or []), "learnt_at": p.get("learnt_at")}
                for name, p in sorted(self._load().items())
            ]

    def enroll(self, name: str, prints: Sequence[Any]) -> int:
        """Add voiceprints of *name* (taken while that person spoke)."""
        name = " ".join(str(name or "").split())[:60]
        if not name:
            raise ValueError("¿De quién es la voz?")
        clean = [[round(float(v), 5) for v in p] for p in prints]
        if not clean:
            raise ValueError("No oí voz suficiente.")
        with self._lock:
            people = self._load()
            key = next((k for k in people if k.lower() == name.lower()), name)
            others = {k: v for k, v in people.items() if k != key and v.get("prints")}
            for other, person in others.items():
                import numpy as np

                centre = np.mean(np.asarray(clean, dtype=np.float32), axis=0)
                centre /= np.linalg.norm(centre) + 1e-9
                if person_score(centre, person["prints"]) >= SAME_VOICE + 0.15:
                    raise ValueError(f"Esa voz ya la tengo guardada como {other}.")
            person = people.setdefault(key, {"prints": [], "learnt_at": time.time()})
            person["prints"] = (person["prints"] + clean)[-MAX_PRINTS:]
            person["learnt_at"] = time.time()
            self._save()
            return len(person["prints"])

    def forget(self, name: str) -> bool:
        with self._lock:
            people = self._load()
            key = next((k for k in people if k.lower() == name.strip().lower()), "")
            if not key:
                return False
            del people[key]
            self._save()
            return True

    def identify(self, print_: Any, owner: str = "", seconds: float = 0.0) -> Voice:
        """Whose voice it is. *seconds* of speech it came from: from two
        seconds on the bar is stricter (measured on LibriSpeech: 100 % right,
        2.5 % of strangers let in with ten voices learnt)."""
        with self._lock:
            people = {k: v["prints"] for k, v in self._load().items() if v.get("prints")}
        ranked = sorted(((person_score(print_, prints), name) for name, prints in people.items()), reverse=True)
        if not ranked:
            return Voice("", 0.0)
        best, name = ranked[0]
        runner = ranked[1][0] if len(ranked) > 1 else -1.0
        margin = best - max(runner, 0.0)
        bar = SAME_VOICE_LONG if seconds >= 2.0 else SAME_VOICE
        if best >= bar and best - runner >= VOICE_MARGIN:
            return Voice(name, best, margin, bool(owner) and name.lower() == owner.lower(), name)
        return Voice("", max(best, 0.0), margin, candidate=name)


class LiveVoices:
    """Who is talking right now, from the microphone, without blocking it.

    Every 32 ms frame goes to ``feed``; speech is kept until a pause (or
    every *chunk* seconds of non-stop talk) and its voiceprint is computed
    in a worker thread. ``current`` says who spoke last; ``on_change`` is
    called when the speaker changes (to tell the live conversation). Frames
    are skipped while Sergio himself is talking (*mute* returns True).
    """

    def __init__(
        self,
        encoder: Callable[[], Any],
        book: VoiceBook,
        *,
        owner: Callable[[], str] = lambda: "",
        on_change: Callable[[Voice, Voice | None], None] = lambda _new, _old: None,
        mute: Callable[[], bool] = lambda: False,
        min_seconds: float = 1.2,
        chunk: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
        background: bool = True,
    ) -> None:
        self._encoder_factory = encoder
        self.background = background  # False: label in the caller (tests)
        self._encoder: Any = None
        self.book = book
        self.owner = owner
        self.on_change = on_change
        self.mute = mute
        self.min_seconds = min_seconds
        self.chunk = chunk
        self.clock = clock
        self.current: Voice | None = None
        self.since = 0.0  # when the current speaker started
        self.history: list[tuple[float, Voice]] = []  # (time, who), recent
        self.enabled = True
        self.error = ""
        self._buf: list[bytes] = []
        self._voiced = 0
        self._quiet = 0
        self._noise = 300.0
        self._busy = threading.Lock()
        self._taps: list[Callable[[bytes], None]] = []  # e.g. voice enrolment

    def tap(self, fn: Callable[[bytes], None]) -> Callable[[], None]:
        """Also hand every frame to *fn* (until the returned remover is called)."""
        self._taps.append(fn)
        return lambda: self._taps.remove(fn) if fn in self._taps else None

    def encoder(self) -> Any:
        if self._encoder is None:
            self._encoder = self._encoder_factory()
        return self._encoder

    def feed(self, frame: bytes) -> None:
        for fn in list(self._taps):
            try:
                fn(frame)
            except Exception:  # noqa: BLE001
                pass
        if not self.enabled or self.mute():
            self._buf, self._voiced, self._quiet = [], 0, 0
            return
        import numpy as np

        level = float(np.sqrt(np.mean(np.frombuffer(frame, dtype=np.int16).astype(np.float32) ** 2)))
        loud = level > max(250.0, self._noise * 3)
        if not loud:
            self._noise = 0.98 * self._noise + 0.02 * max(level, 30.0)
        frame_s = len(frame) / 2 / RATE
        if loud:
            self._buf.append(frame)
            self._voiced += 1
            self._quiet = 0
        elif self._buf:
            self._buf.append(frame)
            self._quiet += 1
        seconds = self._voiced * frame_s
        paused = self._quiet * frame_s >= 0.45
        if self._buf and (paused or seconds >= self.chunk):
            pcm, self._buf = b"".join(self._buf), []
            voiced_s, self._voiced, self._quiet = seconds, 0, 0
            if voiced_s >= self.min_seconds and not self._busy.locked():
                if self.background:
                    threading.Thread(target=self._label, args=(pcm,), daemon=True).start()
                else:
                    self._label(pcm)

    def _label(self, pcm: bytes) -> None:
        with self._busy:
            try:
                voice = self.identify_pcm(pcm)
            except Exception as exc:  # noqa: BLE001 — no torch / model: off
                self.error = str(exc)[:200]
                log.info("voice id unavailable: %s", exc)
                self.enabled = False
                return
            self.note(voice)

    def identify_pcm(self, pcm: bytes) -> Voice:
        samples = voiced(pcm_to_float(pcm))
        print_ = self.encoder().embed(samples)
        return self.book.identify(print_, self.owner(), samples.size / RATE)

    def note(self, voice: Voice) -> None:
        now = self.clock()
        old = self.current
        self.history = [(t, v) for t, v in self.history if now - t < 600][-50:] + [(now, voice)]
        if old is None or old.name != voice.name:
            self.current, self.since = voice, now
            self.on_change(voice, old)
        else:
            self.current = voice

    def describe(self, voice: Voice | None = None) -> str:
        """'el señor' / 'Ana' / 'una voz que no conozco'."""
        voice = voice or self.current
        if voice is None:
            return "nadie todavía"
        if voice.owner:
            return "el señor"
        return voice.name or "una voz que no conozco"


__all__ = [
    "Encoder",
    "LiveVoices",
    "MODEL_SHA256",
    "MODEL_URL",
    "RATE",
    "SAME_VOICE",
    "Voice",
    "VoiceBook",
    "ensure_model",
    "pcm_to_float",
    "person_score",
    "voiced",
]
