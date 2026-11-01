"""Escucha clara (1 nov. 2026): dictado limpio, a quién se habla, micrófono más
claro, y el pliegue Duo más lento."""

from __future__ import annotations

import io
import wave

import numpy as np


def test_dictation_writes_like_a_person():
    from sergio_escritorio.escucha import clean, dictation

    assert (
        clean("eh, quedamos a las cinco, no, mejor a las seis") == "quedamos a las seis"
    )
    assert clean("el el perro come") == "el perro come"
    assert dictation(
        "dicta: hola Juan coma te escribo para confirmar punto nueva línea saludos"
    ) == ("Hola Juan, te escribo para confirmar.\nSaludos.")
    # «escribe un correo…» is an order for Sergio, not text to type
    assert dictation("escribe un correo a Juan") is None


def test_who_the_words_are_for():
    from sergio_escritorio.escucha import addressee

    assert addressee("Sergio, qué hora es") == "sergio"
    assert addressee("oye mamá pásame la sal", in_conversation=True) == "persona"
    assert addressee("Sergio dijo que vendría", in_conversation=True) == "persona"
    assert (
        addressee("bienvenidos a mi canal, hoy veremos", in_conversation=True)
        == "video"
    )
    assert addressee("¿y mañana?", in_conversation=True) == "sergio"
    # the PC is playing sound and it is not an order: a video
    assert (
        addressee(
            "y entonces la casa era grande", in_conversation=True, media_playing=True
        )
        == "video"
    )
    assert (
        addressee("pon la siguiente", in_conversation=True, media_playing=True)
        == "sergio"
    )


def test_the_follow_up_window_drops_chatter_and_videos(monkeypatch):
    from sergio_escritorio import escucha
    from sergio_escritorio.voice import Assistant

    monkeypatch.setattr(escucha, "media_playing", lambda: None)
    assert Assistant._for_sergio(None, "¿y el clima de mañana?") is True
    assert (
        Assistant._for_sergio(None, "no te hablo a ti, hablo con otra persona") is False
    )


def _wav(samples: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(samples.astype(np.int16).tobytes())
    return buf.getvalue()


def test_the_microphone_is_cleaner_and_never_lost():
    from sergio_escritorio.escucha import clear_wav

    t = np.arange(16000) / 16000
    voice = 3000 * np.sin(2 * np.pi * 220 * t) * (t > 0.5)  # speech in the second half
    hiss = np.random.default_rng(1).normal(0, 150, t.size)
    out = clear_wav(_wav(voice + hiss))
    with wave.open(io.BytesIO(out)) as w:
        got = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
    quiet_before = np.sqrt(np.mean(hiss[:7000] ** 2))
    quiet_after = np.sqrt(np.mean(got[:7000] ** 2))
    assert quiet_after < quiet_before  # the hiss went down where nobody spoke
    assert clear_wav(b"not a wav") == b"not a wav"


def test_the_duo_fold_is_slow_enough_to_see():
    from sergio_escritorio import duo_veil

    assert duo_veil.FRAMES * duo_veil.FRAME_S >= 0.55
    assert duo_veil.VEIL_OUT >= 0.9
