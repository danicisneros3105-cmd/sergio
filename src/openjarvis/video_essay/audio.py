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
from pathlib import Path
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


def _bandnoise(n: int, rng: np.random.Generator, low: float, high: float) -> np.ndarray:
    """Noise kept between *low* and *high* Hz (done in the spectrum: fast)."""
    spec = np.fft.rfft(rng.standard_normal(n).astype(np.float32))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[(f < low) | (f > high)] = 0
    return np.fft.irfft(spec, n).astype(np.float32)


def _room(
    x: np.ndarray, seconds: float = 0.5, wet: float = 0.18, seed: int = 0
) -> np.ndarray:
    """A short, dark room tail, so an effect sits in the mix instead of
    floating on top of it (a dry synthetic beep is what sounds cheap)."""
    rng = np.random.default_rng(seed + 99)
    m = int(seconds * SR)
    t = np.arange(m) / SR
    ir = rng.standard_normal(m).astype(np.float32) * np.exp(-t * 7).astype(np.float32)
    ir = _bandnoise_ir(ir)
    n = len(x) + m
    tail = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)[:n].astype(
        np.float32
    )
    tail /= float(np.max(np.abs(tail))) or 1.0
    out = np.zeros(n, dtype=np.float32)
    out[: len(x)] += x
    return out + tail * wet * float(np.max(np.abs(x)) or 1.0)


def _bandnoise_ir(ir: np.ndarray) -> np.ndarray:
    spec = np.fft.rfft(ir)
    f = np.fft.rfftfreq(len(ir), 1 / SR)
    spec *= 1 / (1 + (f / 3500) ** 2)  # a soft, dark room
    return np.fft.irfft(spec, len(ir)).astype(np.float32)


def _norm(x: np.ndarray, peak: float) -> np.ndarray:
    return (x / (float(np.max(np.abs(x))) or 1.0) * peak).astype(np.float32)


def whoosh(seconds: float = 0.5, seed: int = 1) -> np.ndarray:
    """Air passing the camera: a band of noise that sweeps up and away (a
    quick rise, a longer tail), a low body under it and a room tail."""
    rng = np.random.default_rng(seed)
    seconds *= rng.uniform(0.85, 1.15)
    n = int(seconds * SR)
    t = np.linspace(0, 1, n, dtype=np.float32)
    peak_at = rng.uniform(0.35, 0.5)
    sweep = 400 + 5200 * np.exp(-(((t - peak_at) / 0.22) ** 2))
    air = _lowpass(rng.standard_normal(n).astype(np.float32), sweep)
    air -= _lowpass(air, sweep * 0.3)
    body = _bandnoise(n, rng, 60, 260) * 0.6
    shape = np.where(t < peak_at, (t / peak_at) ** 2, np.exp(-(t - peak_at) * 6))
    return _norm(_room((air + body) * shape, 0.4, 0.15, seed), 0.85)


def click(seed: int = 2) -> np.ndarray:
    """A real button: a press and a softer release 40 ms later."""
    rng = np.random.default_rng(seed)
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    for at, level in ((0, 1.0), (int(rng.uniform(0.035, 0.05) * SR), 0.45)):
        m = n - at
        tick = _bandnoise(m, rng, 1800, 7000) * np.exp(-t[:m] * 900)
        body = np.sin(2 * np.pi * rng.uniform(900, 1300) * t[:m]) * np.exp(-t[:m] * 400)
        out[at:] += (tick + body * 0.4) * level
    return _norm(out, 0.5)


def impact(seed: int = 3) -> np.ndarray:
    """A cinematic hit: a sub boom that drops in pitch, a punchy mid body, a
    transient on top and a dark tail."""
    rng = np.random.default_rng(seed)
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    base = rng.uniform(42, 52)
    freq = base + 70 * np.exp(-t * 22)
    boom = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 4.5)
    body = _bandnoise(n, rng, 120, 900) * np.exp(-t * 18) * 0.7
    snap = _bandnoise(n, rng, 2000, 9000) * np.exp(-t * 120) * 0.35
    hit = np.tanh((boom + body + snap) * 1.6)  # a little drive glues it
    return _norm(_room(hit, 0.7, 0.22, seed), 0.9)


def typewriter(keys: int = 6, seed: int = 4) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros(int(0.09 * keys * SR + SR * 0.12), dtype=np.float32)
    for k in range(keys):
        at = int((k * 0.085 + rng.uniform(0, 0.025)) * SR)
        c = click(seed + k) * rng.uniform(0.5, 1.0)
        out[at : at + len(c)] += c[: len(out) - at]
    return _norm(out, 0.5)


def riser(seconds: float = 1.6, seed: int = 5) -> np.ndarray:
    """Tension before a payoff: noise opening up and two detuned tones that
    climb, growing toward the end and stopping dead (the hit lands there)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.linspace(0, 1, n, dtype=np.float32)
    start = rng.uniform(100, 140)
    f = start * (2 ** (2.5 * t))  # two and a half octaves
    tone = (
        sum(np.sin(2 * np.pi * np.cumsum(f * d) / SR) for d in (1.0, 1.006, 2.003)) / 3
    )
    hiss = _lowpass(rng.standard_normal(n).astype(np.float32), 300 + 7000 * t**2)
    out = (tone * 0.5 + hiss * 0.6) * t**2.2
    out[-int(0.01 * SR) :] *= np.linspace(1, 0, int(0.01 * SR), dtype=np.float32)
    return _norm(out, 0.6)


def pop(seed: int = 6) -> np.ndarray:
    """A soft bubble pop for text appearing (not a cartoon boing)."""
    rng = np.random.default_rng(seed)
    n = int(0.1 * SR)
    t = np.arange(n) / SR
    freq = rng.uniform(380, 520) * (1 + 1.2 * (1 - np.exp(-t * 60)))
    tone = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 55)
    air = _bandnoise(n, rng, 1500, 6000) * np.exp(-t * 200) * 0.25
    return _norm(_room(tone + air, 0.25, 0.1, seed), 0.45)


def sizzle(seconds: float = 0.9, seed: int = 8) -> np.ndarray:
    """Frying: crackling noise (food videos)."""
    n = int(seconds * SR)
    rng = np.random.default_rng(seed)
    hiss = _bandnoise(n, rng, 2500, 12000) * 0.25
    crackle = (rng.random(n) > 0.997).astype(np.float32) * rng.uniform(
        0.3, 0.9, n
    ).astype(np.float32)
    crackle = np.convolve(crackle, np.exp(-np.arange(200) / 25), mode="same").astype(
        np.float32
    )
    return _norm((hiss + crackle * 0.6) * _env(n, 0.05, 0.3), 0.5)


def ding(seed: int = 9) -> np.ndarray:
    """A small bell (an order, a counter reaching its number): inharmonic
    partials like real metal, each fading at its own speed."""
    n = int(1.4 * SR)
    t = np.arange(n) / SR
    base = 1318 * np.random.default_rng(seed).uniform(0.97, 1.03)
    tone = sum(
        np.sin(2 * np.pi * base * r * t) * a * np.exp(-t * d)
        for r, a, d in ((1, 0.6, 3), (2.76, 0.25, 6), (5.4, 0.12, 11), (8.93, 0.05, 18))
    )
    return _norm(_room(tone * _env(n, 0.002, 0.2), 0.6, 0.2, seed), 0.45)


def subdrop(seed: int = 10) -> np.ndarray:
    """The low boom under a reveal: a sine that falls from 90 to 30 Hz, driven
    a little so it is heard on a phone speaker too (its second harmonic)."""
    rng = np.random.default_rng(seed)
    n = int(1.4 * SR)
    t = np.arange(n) / SR
    f = 30 + rng.uniform(55, 65) * np.exp(-t * 3.2)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    env = (1 - np.exp(-t * 400)) * np.exp(-t * 2.3)
    return _norm(np.tanh(tone * env * 2.2), 0.85)


def reverse(seconds: float = 0.9, seed: int = 11) -> np.ndarray:
    """A reversed cymbal: air that swells and stops dead on the cut (the
    sound of the edits in trailers and fast explainers)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * rng.uniform(0.9, 1.1) * SR)
    t = np.arange(n) / SR
    crash = _bandnoise(n, rng, 2500, 14000) * np.exp(-t * 5.5)
    shimmer = (
        sum(np.sin(2 * np.pi * rng.uniform(3000, 9000) * t) for _ in range(4))
        * 0.04
        * np.exp(-t * 4)
    )
    wet = _room(crash + shimmer, 0.5, 0.3, seed)[:n]
    out = wet[::-1].copy()
    out[-int(0.006 * SR) :] *= np.linspace(1, 0, int(0.006 * SR), dtype=np.float32)
    return _norm(out, 0.55)


def glitch(seed: int = 12) -> np.ndarray:
    """A digital stutter for a jump cut or a screen: short crushed bursts."""
    rng = np.random.default_rng(seed)
    n = int(0.34 * SR)
    out = np.zeros(n, dtype=np.float32)
    at = 0
    while at < n - int(0.02 * SR):
        m = int(rng.uniform(0.012, 0.045) * SR)
        t = np.arange(m) / SR
        f = rng.uniform(180, 2600)
        burst = (
            np.sign(np.sin(2 * np.pi * f * t)) * 0.5
            + _bandnoise(m, rng, 800, 9000) * 0.6
        )
        hold = int(rng.integers(2, 9))  # sample-and-hold: the crushed, digital edge
        burst = np.repeat(burst[::hold], hold)[:m]
        burst = np.round(burst * 4) / 4
        end = min(n, at + m)
        out[at:end] += burst[: end - at] * _env(m, 0.001, 0.004)[: end - at]
        at = end + int(rng.uniform(0.004, 0.03) * SR)
    return _norm(out, 0.42)


def shutter(seed: int = 13) -> np.ndarray:
    """A camera shutter for a photo or a freeze: two mechanical clacks."""
    rng = np.random.default_rng(seed)
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    for at, level in ((0, 1.0), (int(rng.uniform(0.055, 0.075) * SR), 0.7)):
        m = n - at
        clack = _bandnoise(m, rng, 900, 8000) * np.exp(-t[:m] * 260)
        spring = (
            np.sin(2 * np.pi * rng.uniform(2200, 2800) * t[:m])
            * np.exp(-t[:m] * 180)
            * 0.3
        )
        out[at:] += (clack + spring) * level
    return _norm(_room(out, 0.2, 0.08, seed)[: n + int(0.1 * SR)], 0.5)


def swipe(seed: int = 14) -> np.ndarray:
    """A short bright swish for text or a panel sliding in (lighter than a whoosh)."""
    rng = np.random.default_rng(seed)
    n = int(rng.uniform(0.18, 0.26) * SR)
    t = np.linspace(0, 1, n, dtype=np.float32)
    air = _bandnoise(n, rng, 2200, 11000)
    shape = np.where(t < 0.45, (t / 0.45) ** 1.5, np.exp(-(t - 0.45) * 9))
    return _norm(_room(air * shape, 0.2, 0.08, seed), 0.5)


EFFECTS = {
    "pop": pop,
    "sizzle": sizzle,
    "ding": ding,
    "whoosh": whoosh,
    "click": click,
    "impact": impact,
    "typewriter": typewriter,
    "riser": riser,
    "subdrop": subdrop,
    "reverse": reverse,
    "glitch": glitch,
    "shutter": shutter,
    "swipe": swipe,
}
# what matters most when two effects compete for the same moment
PRIORITY = {"impact": 5, "riser": 5, "subdrop": 5, "reverse": 4, "ding": 4, "whoosh": 3,
            "sizzle": 3, "glitch": 3, "shutter": 3, "typewriter": 2, "swipe": 2, "pop": 1,
            "click": 1}  # fmt: skip
VARIANTS = 4  # the same effect never sounds exactly the same twice in a row
SOUNDS_DIR = "sonidos"  # ~/.openjarvis/sonidos/<effect>*.wav: the owner's own sounds


def thin(
    events: List[Tuple[float, str]], total: float, *, gap: float = 1.8,
    per_minute: float = 14.0,
) -> List[Tuple[float, str]]:  # fmt: skip
    """Fewer, better-placed effects. A sound on every cut turns into noise
    (owner, 28 Oct 2026: «los efectos de sonido están meh»): two effects are
    never closer than *gap* seconds, and there are at most *per_minute* a
    minute; when they compete, the hit or the riser wins over a pop."""
    ranked = sorted(events, key=lambda e: (-PRIORITY.get(e[1], 0), e[0]))
    cap = max(1, int(per_minute * max(total, 1.0) / 60))
    heavy = max(1, cap // 3)  # big hits stay special: a third of them at most
    kept: List[Tuple[float, str]] = []
    for at, kind in ranked:
        if len(kept) >= cap:
            break
        if (
            PRIORITY.get(kind, 0) >= 4
            and sum(PRIORITY.get(k, 0) >= 4 for _, k in kept) >= heavy
        ):
            continue
        if all(abs(at - k) >= gap for k, _ in kept):
            kept.append((at, kind))
    return sorted(kept)


def _owner_sounds(home: Optional[Path]) -> Dict[str, List[np.ndarray]]:
    """The owner's own effects (a pack he bought or a CC0 pack), by the
    first word of the file name: «impact-02.wav» is an impact."""
    out: Dict[str, List[np.ndarray]] = {}
    folder = (home / SOUNDS_DIR) if home else None
    if folder is None or not folder.is_dir():
        return out
    for f in sorted(folder.glob("*.wav"))[:200]:
        kind = f.stem.lower().replace("_", "-").split("-")[0]
        if kind not in EFFECTS:
            continue
        try:
            x = read_wav(f.read_bytes())[: SR * 4]
        except Exception:  # noqa: BLE001 — a file it cannot read is skipped
            continue
        if len(x):
            out.setdefault(kind, []).append(_norm(x, 0.8))
    return out


def effects_track(
    events: List[Tuple[float, str]], total: float, home: Optional[Path] = None
) -> np.ndarray:
    """All the effects, each at its time (a riser ends at its time). Each
    use takes one of a few variants (or one of the owner's own sounds)."""
    out = np.zeros(int(total * SR) + SR, dtype=np.float32)
    cache: Dict[Tuple[str, int], np.ndarray] = {}
    own = _owner_sounds(home)
    count: Dict[str, int] = {}
    for at, kind in events:
        make = EFFECTS.get(kind)
        if make is None:
            continue
        k = count.get(kind, 0)
        count[kind] = k + 1
        if own.get(kind):
            sound = own[kind][k % len(own[kind])]
        else:
            v = k % VARIANTS
            if (kind, v) not in cache:
                cache[(kind, v)] = make(seed=sum(map(ord, kind)) + 17 * v)
            sound = cache[(kind, v)]
        start = int(at * SR) - (len(sound) if kind == "riser" else int(0.08 * SR))
        start = max(0, start)
        end = min(len(out), start + len(sound))
        out[start:end] += sound[: end - start]
    return out[: int(total * SR)]


# -- effects in stereo ---------------------------------------------------------------------
# Owner, 3 Nov 2026: «los efectos son mediocres». A mono effect copied to both
# speakers sits in the middle, on top of the voice. In a studio mix the
# effects move: a whoosh crosses the picture, a riser opens up wide, a hit has
# its punch in the centre and its tail around you, small UI sounds sit a little
# to one side, never twice on the same side.
PAN = {"whoosh": "sweep", "swipe": "sweep", "riser": "widen", "reverse": "widen", "impact": "wide",
       "sizzle": "wide", "subdrop": "centre", "glitch": "jitter", "pop": "side", "click": "side",
       "typewriter": "side", "ding": "side", "shutter": "side"}  # fmt: skip
ENDS_ON_CUT = ("riser", "reverse")  # these finish on the cut
PEAKS_ON_CUT = ("whoosh", "swipe")  # their loudest moment is the cut


def _decorrelated(x: np.ndarray, seed: int) -> np.ndarray:
    """The same sound with its phases scrambled (smoothly across frequency):
    what each ear gets differently in a real room."""
    rng = np.random.default_rng(seed + 501)
    spec = np.fft.rfft(x)
    walk = np.cumsum(rng.normal(0, 0.35, len(spec)))
    return np.fft.irfft(spec * np.exp(1j * walk), len(x)).astype(np.float32)


def _pan(x: np.ndarray, pos: np.ndarray | float) -> np.ndarray:
    """Balance pan, -1 left … 1 right: in the centre both sides as the mono
    copy, and the far side fades (the near side never gets louder: no clip)."""
    p = np.clip(np.asarray(pos, dtype=np.float32), -1, 1)
    return np.stack([x * np.minimum(1, 1 - p), x * np.minimum(1, 1 + p)], axis=1)


def spatial(x: np.ndarray, kind: str, k: int = 0, seed: int = 0) -> np.ndarray:
    """One effect placed in the stereo picture (*k*: its how-many-th use)."""
    mode = PAN.get(kind, "centre")
    n = len(x)
    side = 1.0 if k % 2 == 0 else -1.0
    if mode == "sweep":  # from one side, through the centre on the cut, out the other
        t = (np.arange(n, dtype=np.float32) - _onset(x, "whoosh")) / np.float32(
            0.15 * SR
        )
        return _pan(x, 0.75 * np.tanh(t) * side)
    if mode == "side":
        return _pan(x, 0.28 * side)
    if mode == "jitter":
        rng = np.random.default_rng(seed + k)
        block = int(0.04 * SR)
        pos = np.repeat(rng.uniform(-0.6, 0.6, n // block + 1), block)[:n].astype(
            np.float32
        )
        return _pan(x, pos)
    if mode in ("widen", "wide"):
        t = np.arange(n, dtype=np.float32) / SR
        width = (
            0.85 * (t / max(t[-1], 1e-6)) ** 1.5 if mode == "widen"
            else np.clip((t - 0.03) / 0.15, 0, 1) * 0.7
        )  # fmt: skip
        s = _decorrelated(x, seed + k) * width
        wide = np.stack([x + s, x - s], axis=1)
        peak = float(np.max(np.abs(wide))) or 1.0
        return wide * np.float32(
            min(1.0, float(np.max(np.abs(x))) / peak)
        )  # never over the dry peak
    return np.stack([x, x], axis=1)


def _onset(sound: np.ndarray, kind: str) -> int:
    """How many samples before the cut the sound starts."""
    if kind in ENDS_ON_CUT:
        return len(sound)
    if kind in PEAKS_ON_CUT:
        w = max(1, int(0.01 * SR))
        env = np.convolve(np.abs(sound), np.ones(w, dtype=np.float32) / w, mode="same")
        return int(np.argmax(env))
    return int(
        0.012 * SR
    )  # a hit lands on the cut (12 ms early: the ear hears it on time)


def effects_stereo(
    events: List[Tuple[float, str]], total: float, home: Optional[Path] = None
) -> np.ndarray:
    """All the effects in stereo, (samples, 2): each placed by ``spatial`` and
    lined up so it lands on its cut (``_onset``). The owner's own sounds
    still win, placed the same way."""
    out = np.zeros((int(total * SR) + SR, 2), dtype=np.float32)
    cache: Dict[Tuple[str, int], np.ndarray] = {}
    own = _owner_sounds(home)
    count: Dict[str, int] = {}
    for at, kind in events:
        make = EFFECTS.get(kind)
        if make is None:
            continue
        k = count.get(kind, 0)
        count[kind] = k + 1
        if own.get(kind):
            sound = own[kind][k % len(own[kind])]
        else:
            v = k % VARIANTS
            if (kind, v) not in cache:
                cache[(kind, v)] = make(seed=sum(map(ord, kind)) + 17 * v)
            sound = cache[(kind, v)]
        placed = spatial(sound, kind, k, seed=sum(map(ord, kind)))
        start = max(0, int(at * SR) - _onset(sound, kind))
        end = min(len(out), start + len(placed))
        out[start:end] += placed[: end - start]
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    if peak > 0.98:  # two effects on top of each other: down, never clipped
        out *= np.float32(0.98 / peak)
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
    if effects is not None:  # under the voice too, a little: words come first
        fx = effects[:n]
        env = voice_envelope(voice)[: len(fx)] if len(voice) else np.zeros(0)
        duck_fx = np.ones(len(fx), dtype=np.float32)
        duck_fx[: len(env)] -= 0.4 * env
        out[: len(fx)] += fx * 0.42 * duck_fx
    peak = float(np.max(np.abs(out))) or 1.0
    return out / max(peak, 1.0) * 0.98


def read_wav(data: bytes) -> np.ndarray:
    """Mono float samples at SR from WAV bytes (resampled if needed)."""
    with wave.open(io.BytesIO(data)) as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width == 1:  # 8-bit WAV is unsigned, centred on 128
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 3:  # 24-bit (studio recordings): three bytes, little-endian
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = v.astype(np.float32) / 8388608.0
    elif width in (2, 4):
        dtype = {2: np.int16, 4: np.int32}[width]
        x = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        x /= float(np.iinfo(dtype).max)
    else:
        raise ValueError(f"WAV de {width * 8} bits no soportado")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR and len(x):
        pos = np.arange(int(len(x) * SR / sr)) * (sr / SR)
        x = np.interp(pos, np.arange(len(x)), x).astype(np.float32)
    return x


def write_wav(samples: np.ndarray, sr: int = SR) -> bytes:
    """16-bit WAV; a (samples, 2) array is written in stereo."""
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2 if pcm.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


__all__ = [
    "EFFECTS",
    "SR",
    "effects_stereo",
    "effects_track",
    "mix",
    "thin",
    "music_bed",
    "read_wav",
    "spatial",
    "voice_envelope",
    "voiced_spans",
    "write_wav",
]
