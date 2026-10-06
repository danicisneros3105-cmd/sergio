"""Meetings, video calls and conversations: Sergio takes the minutes.

«Sergio, toma notas de la reunión» starts it, «termina la reunión» ends it.
Meanwhile two tracks are written to disk (never kept in memory):

* the microphone (the people in the room: you and whoever is with you), and
* what the computer plays (the people in a Zoom/Meet/Teams/WhatsApp call),
  captured from the speakers with WASAPI loopback.

When it ends, each stretch of speech gets a speaker: the voices Sergio knows
by name (``speakers.VoiceBook``), and "Persona 1", "Persona 2"... for the
rest (voices that sound alike are grouped). The mixed audio and that
timeline go to Sergio's server, where Gemini writes the transcript (who said
what), the summary, decisions and tasks; the minutes are saved in
Documentos/Sergio/Reuniones.

Recording other people needs their consent where you live: Sergio reminds
you to tell them.
"""

from __future__ import annotations

import logging
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

RATE = 16_000
FRAME_S = 0.03
MIN_SEGMENT = 0.8  # seconds of speech worth a speaker label
WINDOW = 3.0  # voiceprints over at most this long
# Grouping voices nobody enrolled (cosine of ECAPA voiceprints; on
# LibriSpeech the same person scores ~0.6 on 3 s, ~0.48 on 1.5 s, and two
# people ~0.08 ± 0.09).
LONG_WINDOW = 1.8  # seconds: a piece this long has a reliable voiceprint
SAME_UNKNOWN = 0.40  # a long piece joins a group this alike
SHORT_JOIN = 0.30  # a short piece joins the closest group this alike
MERGE_UNKNOWN = 0.42  # two groups this alike are one person
CRUMB_SECONDS = 2.5  # a "voice" with less speech than this is a crumb...
CRUMB_JOIN = 0.20  # ...that joins its nearest group if at least this alike
ECHO_ALIKE = 0.35  # a room piece this like the call at that moment is echo
KNOWN_LOOSE = 0.28  # in a meeting, a piece this like a known voice...
KNOWN_MARGIN = 0.12  # ...and this far ahead of the others is that person


@dataclass
class Turn:
    start: float
    end: float
    speaker: str
    track: str  # "sala" (microphone) | "llamada" (the computer's sound)

    def to_dict(self) -> dict[str, Any]:
        return {"start": round(self.start, 2), "end": round(self.end, 2), "speaker": self.speaker, "track": self.track}


def mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# -- recording --------------------------------------------------------------------------
class WavTrack:
    """16 kHz mono int16 frames appended to a WAV file as they come."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._wav = wave.open(str(path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(RATE)
        self._lock = threading.Lock()
        self.frames = 0

    def write(self, pcm: bytes) -> None:
        with self._lock:
            if self._wav is not None:
                self._wav.writeframes(pcm)
                self.frames += len(pcm) // 2

    def close(self) -> None:
        with self._lock:
            if self._wav is not None:
                self._wav.close()
                self._wav = None


def to_mono_16k(data: Any, rate: int, channels: int) -> bytes:
    """Any interleaved int16 audio -> 16 kHz mono int16 bytes."""
    import numpy as np

    x = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    if channels > 1:
        x = x[: x.size // channels * channels].reshape(-1, channels).mean(axis=1)
    if rate != RATE and x.size:
        n = max(1, int(round(x.size * RATE / rate)))
        x = np.interp(np.linspace(0, x.size - 1, n), np.arange(x.size), x)
    return np.clip(x, -32768, 32767).astype(np.int16).tobytes()


class Loopback:
    """What the computer plays (the other side of a video call), via WASAPI
    loopback (pyaudiowpatch). ``ok`` is False where it is not available."""

    def __init__(self, write: Callable[[bytes], None]) -> None:
        self.write = write
        self.ok = False
        self.error = ""
        self._pa: Any = None
        self._stream: Any = None

    def start(self) -> bool:
        try:
            import pyaudiowpatch as pyaudio

            pa = pyaudio.PyAudio()
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            if not speakers.get("isLoopbackDevice"):
                for device in pa.get_loopback_device_info_generator():
                    if speakers["name"] in device["name"]:
                        speakers = device
                        break
                else:
                    raise RuntimeError("no encontré la salida de audio para grabarla")
            channels = int(speakers["maxInputChannels"]) or 2
            rate = int(speakers["defaultSampleRate"])

            def callback(data: bytes, _frames: int, _info: Any, _status: Any) -> tuple[None, int]:
                try:
                    self.write(to_mono_16k(data, rate, channels))
                except Exception:  # noqa: BLE001
                    pass
                return None, pyaudio.paContinue

            self._stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=int(speakers["index"]),
                frames_per_buffer=int(rate * 0.1),
                stream_callback=callback,
            )
            self._stream.start_stream()
            self._pa = pa
            self.ok = True
        except Exception as exc:  # noqa: BLE001 — the room still gets recorded
            self.error = str(exc)[:200]
            log.info("loopback unavailable: %s", exc)
            self.ok = False
        return self.ok

    def stop(self) -> None:
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
            if self._pa is not None:
                self._pa.terminate()
        except Exception:  # noqa: BLE001
            pass
        self._stream = self._pa = None


@dataclass
class Recording:
    folder: Path
    room: Path
    call: Path | None
    seconds: float
    started: float


class MeetingRecorder:
    """Writes the microphone and (if it can) the computer's sound to disk."""

    def __init__(
        self,
        tap: Callable[[Callable[[bytes], None]], Callable[[], None]],
        folder: Path,
        *,
        loopback: Callable[[Callable[[bytes], None]], Any] = Loopback,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._tap = tap
        self.folder = folder
        self._loopback_factory = loopback
        self.clock = clock
        self.active = False
        self.started = 0.0
        self.title = ""
        self._room: WavTrack | None = None
        self._call: WavTrack | None = None
        self._untap: Callable[[], None] = lambda: None
        self._loop: Any = None
        self.loopback_error = ""

    def start(self, title: str = "") -> str:
        if self.active:
            return "Ya estoy tomando notas."
        self.started = self.clock()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.started))
        here = self.folder / f"reunion-{stamp}"
        here.mkdir(parents=True, exist_ok=True)
        self._room = WavTrack(here / "sala.wav")
        self._call = WavTrack(here / "llamada.wav")
        self._untap = self._tap(self._room.write)
        self._loop = self._loopback_factory(self._call.write)
        self._loop.start()
        self.loopback_error = "" if self._loop.ok else self._loop.error
        self.title = title.strip()
        self.active = True
        return str(here)

    def stop(self) -> Recording | None:
        if not self.active or self._room is None or self._call is None:
            return None
        self.active = False
        self._untap()
        if self._loop is not None:
            self._loop.stop()
        self._room.close()
        self._call.close()
        call = self._call.path if self._call.frames > RATE else None
        if call is None:
            self._call.path.unlink(missing_ok=True)
        return Recording(self._room.path.parent, self._room.path, call, self.clock() - self.started, self.started)

    @property
    def seconds(self) -> float:
        return self.clock() - self.started if self.active else 0.0


# -- who spoke when ------------------------------------------------------------------------
def read_wav(path: Path) -> Any:
    import numpy as np

    with wave.open(str(path), "rb") as wav:
        data = wav.readframes(wav.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def speech_segments(audio: Any, *, gap: float = 0.5, min_len: float = MIN_SEGMENT) -> list[tuple[float, float]]:
    """(start, end) seconds of speech: an adaptive energy gate, pauses
    shorter than *gap* kept inside a segment."""
    import numpy as np

    hop = int(RATE * FRAME_S)
    n = audio.size // hop
    if n == 0:
        return []
    energy = np.sqrt(np.mean(audio[: n * hop].reshape(n, hop) ** 2, axis=1))
    floor = float(np.percentile(energy, 20))
    loud = energy > max(0.006, floor * 3.0)
    out: list[tuple[float, float]] = []
    start = None
    quiet = 0
    for i, on in enumerate(loud):
        if on:
            if start is None:
                start = i
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet * FRAME_S >= gap:
                end = i - quiet + 1
                if (end - start) * FRAME_S >= min_len:
                    out.append((start * FRAME_S, end * FRAME_S))
                start, quiet = None, 0
    if start is not None and (n - start) * FRAME_S >= min_len:
        out.append((start * FRAME_S, n * FRAME_S))
    return out


def _windows(start: float, end: float) -> list[tuple[float, float]]:
    """A long stretch of speech in ~WINDOW s pieces (a speaker may change)."""
    length = end - start
    count = max(1, int(round(length / WINDOW)))
    step = length / count
    return [(start + i * step, start + (i + 1) * step) for i in range(count)]


@dataclass
class _Piece:
    track: str
    start: float
    end: float
    print_: Any
    name: str = ""
    group: int = -1

    @property
    def length(self) -> float:
        return self.end - self.start


def _centre(prints: list[Any]) -> Any:
    import numpy as np

    c = np.mean(prints, axis=0)
    return c / (np.linalg.norm(c) + 1e-9)


def group_unknown(pieces: list[_Piece]) -> None:
    """Number the voices nobody enrolled: long stretches (reliable
    voiceprints) form the groups first; short ones join the closest group;
    groups that sound alike merge; crumbs join their nearest group."""
    import numpy as np

    unknown = [p for p in pieces if not p.name]
    groups: list[list[_Piece]] = []

    def best_group(piece: _Piece, bar: float) -> int:
        best, score = -1, bar
        for i, members in enumerate(groups):
            s = float(np.dot(piece.print_, _centre([m.print_ for m in members])))
            if s >= score:
                best, score = i, s
        return best

    for piece in sorted(unknown, key=lambda p: -p.length):
        long = piece.length >= LONG_WINDOW
        found = best_group(piece, SAME_UNKNOWN if long else SHORT_JOIN)
        if found < 0:
            groups.append([piece])
        else:
            groups[found].append(piece)
    # Merge groups that are one person.
    changed = True
    while changed and len(groups) > 1:
        changed = False
        centres = [_centre([m.print_ for m in g]) for g in groups]
        pairs = [
            (float(np.dot(centres[i], centres[j])), i, j)
            for i in range(len(groups))
            for j in range(i)
        ]
        score, i, j = max(pairs)
        if score >= MERGE_UNKNOWN:
            groups[j].extend(groups.pop(i))
            changed = True
    # Crumbs (a cough, two words) go to their nearest real group.
    big = [g for g in groups if sum(m.length for m in g) >= CRUMB_SECONDS]
    if big:
        for g in [g for g in groups if sum(m.length for m in g) < CRUMB_SECONDS]:
            centres = [_centre([m.print_ for m in b]) for b in big]
            c = _centre([m.print_ for m in g])
            scores = [float(np.dot(c, b)) for b in centres]
            k = int(np.argmax(scores))
            if scores[k] >= CRUMB_JOIN:
                big[k].extend(g)
                groups.remove(g)
    # Number them in order of first appearance.
    groups.sort(key=lambda g: min(m.start for m in g))
    for number, g in enumerate(groups, 1):
        for m in g:
            m.group = number


def second_chance(voice: Any) -> bool:
    """A short, noisy piece that still clearly leans to one known person."""
    return bool(getattr(voice, "candidate", "")) and voice.score >= KNOWN_LOOSE and voice.margin >= KNOWN_MARGIN


def drop_echo(pieces: list[_Piece]) -> list[_Piece]:
    """The microphone also hears the call from the speakers: a room piece
    that overlaps a call piece in time and sounds like it is that echo."""
    import numpy as np

    calls = [p for p in pieces if p.track == "llamada"]
    kept = []
    for piece in pieces:
        if piece.track == "sala":
            echo = False
            for other in calls:
                overlap = min(piece.end, other.end) - max(piece.start, other.start)
                if overlap > 0.5 * piece.length and float(np.dot(piece.print_, other.print_)) >= ECHO_ALIKE:
                    echo = True
                    break
            if echo:
                continue
        kept.append(piece)
    return kept


def diarize(
    tracks: dict[str, Any],
    embed: Callable[[Any], Any],
    identify: Callable[[Any], Any],
    *,
    describe: Callable[[Any], str] = lambda v: v.name,
) -> list[Turn]:
    """Who spoke when, on each track ("sala", "llamada").

    Known voices get their name (``identify`` -> speakers.Voice); unknown
    ones are grouped by likeness into "Persona 1", "Persona 2"...
    """
    pieces: list[_Piece] = []
    for track, audio in tracks.items():
        for start, end in speech_segments(audio):
            for a, b in _windows(start, end):
                chunk = audio[int(a * RATE) : int(b * RATE)]
                if chunk.size < int(0.6 * RATE):
                    continue
                print_ = embed(chunk)
                voice = identify(print_)
                name = describe(voice) if voice.name else ""
                if not name and second_chance(voice):
                    name = voice.candidate  # a meeting is mostly a closed group
                pieces.append(_Piece(track, a, b, print_, name))
    pieces = drop_echo(pieces)
    group_unknown(pieces)
    # A whole group of short pieces says more than each piece: it may still
    # be someone Sergio knows.
    for number in sorted({p.group for p in pieces if not p.name}):
        members = [p for p in pieces if not p.name and p.group == number]
        voice = identify(_centre([m.print_ for m in members]))
        name = describe(voice) if voice.name else (voice.candidate if second_chance(voice) else "")
        for m in members if name else ():
            m.name = name
    left = sorted({p.group for p in pieces if not p.name}, key=lambda g: min(p.start for p in pieces if p.group == g))
    renumber = {g: i for i, g in enumerate(left, 1)}
    for p in pieces:
        if not p.name:
            p.group = renumber[p.group]
    turns: list[Turn] = []
    for piece in sorted(pieces, key=lambda p: p.start):
        name = piece.name or f"Persona {piece.group}"
        last = next((t for t in reversed(turns) if t.track == piece.track), None)
        if last is not None and last is turns[-1] and last.speaker == name and piece.start - last.end < 1.0:
            last.end = piece.end
        else:
            turns.append(Turn(piece.start, piece.end, name, piece.track))
    return turns


def timeline_text(turns: list[Turn]) -> str:
    lines = []
    for t in turns:
        where = " (videollamada)" if t.track == "llamada" else ""
        lines.append(f"{mmss(t.start)}-{mmss(t.end)} {t.speaker}{where}")
    return "\n".join(lines)


def mix(tracks: dict[str, Any]) -> Any:
    """Both tracks into one, each at a comfortable loudness."""
    import numpy as np

    length = max((a.size for a in tracks.values()), default=0)
    out = np.zeros(length, dtype=np.float32)
    for audio in tracks.values():
        if not audio.size:
            continue
        peak = float(np.percentile(np.abs(audio), 99.5)) or 1.0
        out[: audio.size] += audio * min(4.0, 0.5 / peak)
    return np.clip(out, -1.0, 1.0)


def encode(audio: Any, folder: Path) -> tuple[Path, str]:
    """Compressed audio for the trip to the server: OGG Vorbis (~10 MB an
    hour) with soundfile, else WAV."""
    try:
        import soundfile as sf

        path = folder / "reunion.ogg"
        sf.write(str(path), audio, RATE, format="OGG", subtype="VORBIS")
        return path, "audio/ogg"
    except Exception:  # noqa: BLE001 — no libsndfile: plain WAV
        import numpy as np

        path = folder / "reunion.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        return path, "audio/wav"


@dataclass
class Minutes:
    title: str
    markdown: str
    summary: str
    path: Path | None = None
    speakers: list[str] = field(default_factory=list)


def spoken_summary(data: dict[str, Any]) -> str:
    """What Sergio says when the minutes are ready (short)."""
    summary = str(data.get("resumen") or data.get("summary") or "").strip()
    tasks = data.get("tareas") or []
    parts = [summary.split("\n")[0][:400]] if summary else []
    if tasks:
        first = tasks[0]
        who = str(first.get("quien") or "").strip()
        what = str(first.get("que") or "").strip()
        more = f" y {len(tasks) - 1} más" if len(tasks) > 1 else ""
        if what:
            parts.append(f"Tarea: {who + ', ' if who else ''}{what}{more}.")
    return " ".join(parts) or "Listo, tengo las notas."


__all__ = [
    "Loopback",
    "MeetingRecorder",
    "Minutes",
    "Recording",
    "Turn",
    "WavTrack",
    "diarize",
    "encode",
    "mix",
    "mmss",
    "read_wav",
    "speech_segments",
    "spoken_summary",
    "timeline_text",
    "to_mono_16k",
]
