"""Microphone recording with silence detection and audio playback helpers.

Robustness notes (why conversations used to fail):
- The old fixed RMS threshold (500) never matched every microphone: quiet
  mics never crossed it (Sergio "did not respond"), noisy rooms never fell
  below it (recording never stopped).  The threshold is now calibrated from
  a short ambient-noise sample on every recording.
- The old 5 s startup window gave up before people finished thinking.  It
  is now 12 s by default.
- ``play_wav_interruptible`` adds barge-in: if the user starts speaking
  while Sergio talks, playback stops — the first step towards a real
  phone-call feel.
"""

from __future__ import annotations

import io
import statistics
import wave

_SAMPLE_RATE = 16000
_CHANNELS = 1
_CHUNK = 1024
_SILENCE_THRESHOLD = 500  # fallback RMS when calibration is not possible
_SILENCE_SECONDS = 1.2  # seconds of silence before auto-stop
_STARTUP_SILENCE_SECONDS = 12.0  # give up early if speech never begins
_MAX_RECORD_SECONDS = 60  # safety ceiling
_CALIBRATION_SECONDS = 0.6  # ambient-noise sample before recording


def _rms(data: bytes) -> float:
    """Compute RMS amplitude of 16-bit PCM bytes."""
    import struct

    n = len(data) // 2
    if n == 0:
        return 0.0
    shorts = struct.unpack(f"{n}h", data[: n * 2])
    return (sum(s * s for s in shorts) / n) ** 0.5


def _calibrate_threshold(
    stream: object,
    *,
    seconds: float = _CALIBRATION_SECONDS,
    sample_rate: int = _SAMPLE_RATE,
) -> int:
    """Measure the ambient noise floor and derive a speech threshold.

    Returns 3x the median noise RMS, clamped to a sane range so a slamming
    door during calibration cannot make the mic deaf, and a silent room
    cannot make it hyper-sensitive.
    """
    chunks = max(1, int(seconds * sample_rate / _CHUNK))
    levels: list[float] = []
    for _ in range(chunks):
        raw, _ = stream.read(_CHUNK)  # type: ignore[attr-defined]
        levels.append(_rms(bytes(raw)))
    floor = statistics.median(levels) if levels else 0.0
    return int(min(3000.0, max(250.0, floor * 3.0)))


def record_until_silence(
    *,
    sample_rate: int = _SAMPLE_RATE,
    silence_threshold: int | None = None,
    silence_seconds: float = _SILENCE_SECONDS,
    startup_silence_seconds: float = _STARTUP_SILENCE_SECONDS,
    max_seconds: float = _MAX_RECORD_SECONDS,
    calibrate: bool = True,
) -> bytes:
    """Record from the default microphone until silence is detected.

    Returns raw WAV bytes (16-bit mono).
    Raises RuntimeError if sounddevice is not installed.

    When ``silence_threshold`` is None (the default) and ``calibrate`` is
    true, the threshold adapts to the room's noise floor on every call.
    """
    try:
        import sounddevice as sd
    except ImportError:
        raise RuntimeError(
            "sounddevice is required for voice input. "
            "Install with: pip install sounddevice"
        )

    chunks_per_second = sample_rate / _CHUNK
    silence_chunks = int(silence_seconds * chunks_per_second)
    startup_silence_chunks = max(1, int(startup_silence_seconds * chunks_per_second))
    max_chunks = int(max_seconds * chunks_per_second)

    frames: list[bytes] = []
    silence_count = 0
    has_speech = False

    with sd.RawInputStream(
        samplerate=sample_rate,
        channels=_CHANNELS,
        dtype="int16",
        blocksize=_CHUNK,
    ) as stream:
        if silence_threshold is None:
            silence_threshold = (
                _calibrate_threshold(stream, sample_rate=sample_rate)
                if calibrate
                else _SILENCE_THRESHOLD
            )
        for _ in range(max_chunks):
            raw, _ = stream.read(_CHUNK)
            data = bytes(raw)
            frames.append(data)

            amplitude = _rms(data)
            if amplitude > silence_threshold:
                has_speech = True
                silence_count = 0
            elif not has_speech and len(frames) >= startup_silence_chunks:
                break
            elif has_speech:
                silence_count += 1
                if silence_count >= silence_chunks:
                    break

    return _frames_to_wav(frames, sample_rate)


def _frames_to_wav(frames: list[bytes], sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))
    return buf.getvalue()


def _decode_audio(audio: bytes, fallback_rate: int) -> tuple[object, int]:
    import numpy as np
    import soundfile as sf

    buf = io.BytesIO(audio)
    try:
        data, sr = sf.read(buf, dtype="float32")
        return data, sr
    except Exception:
        import struct

        n = len(audio) // 2
        data = (
            np.array(struct.unpack(f"{n}h", audio[: n * 2]), dtype="float32") / 32768.0
        )
        return data, fallback_rate


def play_wav(audio: bytes, sample_rate: int = 24000) -> None:
    """Play raw WAV bytes through the default output device.

    If the bytes are a valid WAV file, sample rate is read from the header;
    otherwise ``sample_rate`` is used as a fallback.
    """
    try:
        import sounddevice as sd
    except ImportError:
        raise RuntimeError(
            "sounddevice, numpy, and soundfile are required for voice output. "
            "Install with: pip install sounddevice numpy soundfile"
        )
    data, sr = _decode_audio(audio, sample_rate)
    sd.play(data, sr)
    sd.wait()


def play_wav_interruptible(
    audio: bytes,
    sample_rate: int = 24000,
    *,
    interrupt_threshold: int | None = None,
    trigger_seconds: float = 0.25,
) -> bool:
    """Play audio, stopping early if the user starts speaking (barge-in).

    Returns True when playback was interrupted by speech, False when it
    finished normally.  Falls back to plain blocking playback when a
    simultaneous mic stream is not possible (some audio devices are not
    full-duplex).
    """
    try:
        import sounddevice as sd
    except ImportError:
        raise RuntimeError(
            "sounddevice, numpy, and soundfile are required for voice output. "
            "Install with: pip install sounddevice numpy soundfile"
        )

    data, sr = _decode_audio(audio, sample_rate)
    try:
        mic = sd.RawInputStream(
            samplerate=_SAMPLE_RATE, channels=_CHANNELS, dtype="int16",
            blocksize=_CHUNK,
        )
    except Exception:  # noqa: BLE001 — device not full-duplex
        sd.play(data, sr)
        sd.wait()
        return False

    with mic:
        if interrupt_threshold is None:
            try:
                interrupt_threshold = _calibrate_threshold(mic)
            except Exception:  # noqa: BLE001
                interrupt_threshold = _SILENCE_THRESHOLD
        trigger_chunks = max(1, int(trigger_seconds * _SAMPLE_RATE / _CHUNK))
        sd.play(data, sr)
        hot = 0
        while sd.get_stream().active:
            try:
                raw, _ = mic.read(_CHUNK)
            except Exception:  # noqa: BLE001 — keep playing if mic read fails
                sd.wait()
                return False
            if _rms(bytes(raw)) > interrupt_threshold:
                hot += 1
                if hot >= trigger_chunks:
                    sd.stop()
                    return True
            else:
                hot = 0
    return False


__all__ = [
    "play_wav",
    "play_wav_interruptible",
    "record_until_silence",
]
