"""The sound of a video essay: sound effects, a music bed and the mix.

Everything is made here, from noise and tones (no sound library to license):

* effects on the cuts: whoosh (filtered noise sweeping up), click, impact
  (low thump with a crack), typewriter (short clicks) and riser (rising
  noise and tone before a payoff);
* when the owner gives no music, a bed that starts quiet and builds:
  a minor-key chord progression with a soft pulse that grows toward the end;
* the mix: the music ducks under the voice (it breathes down while Sergio
  talks and comes back up in the pauses), effects on top, and the whole at
  the loudness platforms ask for (-14 LUFS is set when muxing with ffmpeg).
"""

from __future__ import annotations

import io
import wave
from typing import Dict, List, Optional, Tuple

import numpy as np

SR = 48_000


def _env(n: int, attack: float, release: float) -> np.ndarray:
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    env = np.ones(n, dtype=np.float32)
    env[:a] = np.linspace(0, 1, min(a, n), dtype=np.float32)[: min(a, n)]
    if r < n:
        env[-r:] *= np.linspace(1, 0, r, dtype=np.float32)
    return env


def _lowpass(x: np.ndarray, cutoff: np.ndarray | float) -> np.ndarray:
    """One-pole low-pass; *cutoff* (Hz) may change sample by sample."""
    cut = np.broadcast_to(np.asarray(cutoff, dtype=np.float32), x.shape)
    alpha = 1 - np.exp(-2 * np.pi * cut / SR)
    out = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):  # short effects only (a few thousand samples)
        acc += alpha[i] * (x[i] - acc)
        out[i] = acc
    return out


def whoosh(seconds: float = 0.45, seed: int = 1) -> np.ndarray:
    n = int(seconds * SR)
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n).astype(np.float32)
    sweep = np.geomspace(300, 6000, n).astype(np.float32)
    body = _lowpass(noise, sweep) - _lowpass(noise, sweep * 0.25)
    t = np.linspace(0, 1, n, dtype=np.float32)
    shape = np.sin(np.pi * t) ** 2
    return (body * shape * 0.9).astype(np.float32)


def click(seed: int = 2) -> np.ndarray:
    n = int(0.03 * SR)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    return (rng.standard_normal(n) * np.exp(-t * 300) * 0.5).astype(np.float32)


def impact(seed: int = 3) -> np.ndarray:
    n = int(0.7 * SR)
    t = np.arange(n) / SR
    freq = 55 + 60 * np.exp(-t * 18)
    thump = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 6)
    rng = np.random.default_rng(seed)
    crack = rng.standard_normal(n) * np.exp(-t * 60) * 0.35
    return ((thump + crack) * 0.8).astype(np.float32)


def typewriter(keys: int = 6, seed: int = 4) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros(int(0.09 * keys * SR + SR * 0.05), dtype=np.float32)
    for k in range(keys):
        at = int((k * 0.09 + rng.uniform(0, 0.02)) * SR)
        c = click(seed + k) * rng.uniform(0.6, 1.0)
        out[at : at + len(c)] += c[: len(out) - at]
    return out


def riser(seconds: float = 1.6, seed: int = 5) -> np.ndarray:
    n = int(seconds * SR)
    t = np.linspace(0, 1, n, dtype=np.float32)
    tone = np.sin(2 * np.pi * np.cumsum(np.geomspace(110, 880, n)) / SR) * 0.25
    rng = np.random.default_rng(seed)
    hiss = rng.standard_normal(n).astype(np.float32) * 0.12
    return ((tone + hiss) * t**2).astype(np.float32)


def pop(seed: int = 6) -> np.ndarray:
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    freq = 900 * np.exp(-t * 25) + 180
    return (np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 40) * 0.7).astype(
        np.float32
    )


def sizzle(seconds: float = 0.9, seed: int = 8) -> np.ndarray:
    """Frying: crackling noise (food videos)."""
    n = int(seconds * SR)
    rng = np.random.default_rng(seed)
    hiss = rng.standard_normal(n).astype(np.float32) * 0.18
    crackle = (rng.random(n) > 0.997).astype(np.float32) * rng.uniform(
        0.3, 0.9, n
    ).astype(np.float32)
    crackle = np.convolve(crackle, np.exp(-np.arange(200) / 25), mode="same").astype(
        np.float32
    )
    body = hiss - np.convolve(hiss, np.ones(8) / 8, mode="same")  # keep the high part
    return ((body + crackle * 0.6) * _env(n, 0.05, 0.3)).astype(np.float32)


def ding(seed: int = 9) -> np.ndarray:
    """A small bell (an order, a counter reaching its number)."""
    n = int(1.2 * SR)
    t = np.arange(n) / SR
    tone = sum(
        np.sin(2 * np.pi * f * t) * a
        for f, a in ((1568, 0.5), (3136, 0.2), (4704, 0.1))
    )
    return (tone * np.exp(-t * 4) * 0.6).astype(np.float32)


EFFECTS = {
    "pop": pop,
    "sizzle": sizzle,
    "ding": ding,
    "whoosh": whoosh,
    "click": click,
    "impact": impact,
    "typewriter": typewriter,
    "riser": riser,
}


def effects_track(events: List[Tuple[float, str]], total: float) -> np.ndarray:
    """All the effects, each at its time (a riser ends at its time)."""
    out = np.zeros(int(total * SR) + SR, dtype=np.float32)
    cache: Dict[str, np.ndarray] = {}
    for at, kind in events:
        make = EFFECTS.get(kind)
        if make is None:
            continue
        sound = cache.setdefault(kind, make())
        start = int(at * SR) - (len(sound) if kind == "riser" else int(0.12 * SR))
        start = max(0, start)
        end = min(len(out), start + len(sound))
        out[start:end] += sound[: end - start]
    return out[: int(total * SR)]


# Am - F - C - G, the classic lift of motivational essays.
PROGRESSION = ((57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62))


def _midi(n: int) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def music_bed(total: float, bpm: float = 84.0, seed: int = 7) -> np.ndarray:
    """A bed that builds: pads from the start, a pulse from a third in, and
    more air and weight toward the end."""
    n = int(total * SR)
    t = np.arange(n, dtype=np.float32) / SR
    bar = 4 * 60.0 / bpm
    out = np.zeros(n, dtype=np.float32)
    growth = np.clip(t / max(total, 1.0), 0, 1)
    for i, chord in enumerate(PROGRESSION * int(total / bar / 4 + 2)):
        a, b = int(i * bar * SR), int((i + 1) * bar * SR)
        if a >= n:
            break
        b = min(b, n)
        seg = t[a:b] - t[a]
        pad = np.zeros(b - a, dtype=np.float32)
        for note in chord:
            f = _midi(note)
            pad += np.sin(2 * np.pi * f * seg) * 0.10
            pad += np.sin(2 * np.pi * f * 2.003 * seg) * 0.03  # a slow shimmer
        bass = np.sin(2 * np.pi * _midi(chord[0] - 12) * seg) * 0.18
        pad *= _env(b - a, 0.6, 0.6)
        out[a:b] += pad + bass * growth[a:b]
    beat = 60.0 / bpm
    rng = np.random.default_rng(seed)
    for k in range(int(total / beat)):
        at = k * beat
        if at < total / 3:
            continue
        hit = impact(seed + k)[: int(0.25 * SR)] * 0.25 * float(growth[int(at * SR)])
        s = int(at * SR)
        out[s : s + len(hit)] += hit[: n - s]
        if k % 2:
            hat = rng.standard_normal(int(0.04 * SR)).astype(np.float32)
            hat *= np.exp(-np.arange(len(hat)) / SR * 90) * 0.05
            out[s : s + len(hat)] += hat[: n - s]
    out *= _env(n, 2.0, 2.5)
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak * 0.6


def voice_envelope(voice: np.ndarray, window: float = 0.12) -> np.ndarray:
    """How loud the voice is, smoothed (0..1), for the ducking."""
    w = max(1, int(window * SR))
    power = np.convolve(voice.astype(np.float32) ** 2, np.ones(w) / w, mode="same")
    env = np.sqrt(power)
    top = float(np.percentile(env, 95)) or 1.0
    return np.clip(env / top, 0, 1)


def voiced_spans(
    voice: np.ndarray, sr: int, floor: float = 0.12, gap: float = 0.18
) -> List[Tuple[float, float]]:
    """Where the narration has speech (for word timings without a recogniser)."""
    w = max(1, int(0.03 * sr))
    frames = len(voice) // w
    if frames == 0:
        return []
    energy = np.sqrt(
        np.mean(voice[: frames * w].reshape(frames, w).astype(np.float32) ** 2, axis=1)
    )
    top = float(np.percentile(energy, 95)) or 1.0
    on = energy > floor * top
    spans: List[Tuple[float, float]] = []
    start = None
    for i, v in enumerate(on):
        t = i * w / sr
        if v and start is None:
            start = t
        elif not v and start is not None:
            spans.append((start, t))
            start = None
    if start is not None:
        spans.append((start, frames * w / sr))
    merged: List[Tuple[float, float]] = []
    for a, b in spans:
        if merged and a - merged[-1][1] < gap:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [(a, b) for a, b in merged if b - a > 0.05]


def mix(
    voice: np.ndarray,
    music: Optional[np.ndarray],
    effects: Optional[np.ndarray],
    *,
    music_level: float = 0.32,
    duck: float = 0.65,
) -> np.ndarray:
    """Voice on top, music breathing under it, effects at their moments."""
    n = max(len(voice), len(music) if music is not None else 0)
    out = np.zeros(n, dtype=np.float32)
    out[: len(voice)] += voice
    if music is not None:
        env = np.zeros(n, dtype=np.float32)
        env[: len(voice)] = voice_envelope(voice)
        out[: len(music)] += music[:n] * music_level * (1 - duck * env[: len(music)])
    if effects is not None:
        out[: len(effects)] += effects[:n] * 0.5
    peak = float(np.max(np.abs(out))) or 1.0
    return out / max(peak, 1.0) * 0.98


def read_wav(data: bytes) -> np.ndarray:
    """Mono float samples at SR from WAV bytes (resampled if needed)."""
    with wave.open(io.BytesIO(data)) as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
    x = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    x /= float(np.iinfo(dtype).max)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR and len(x):
        pos = np.arange(int(len(x) * SR / sr)) * (sr / SR)
        x = np.interp(pos, np.arange(len(x)), x).astype(np.float32)
    return x


def write_wav(samples: np.ndarray, sr: int = SR) -> bytes:
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


__all__ = [
    "EFFECTS",
    "SR",
    "effects_track",
    "mix",
    "music_bed",
    "read_wav",
    "voice_envelope",
    "voiced_spans",
    "write_wav",
]
