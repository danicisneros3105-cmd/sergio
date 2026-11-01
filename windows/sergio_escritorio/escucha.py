"""Escucha clara: lo que el señor dice, limpio, y para quién es.

The owner (1 Nov 2026): «agrega una herramienta para que tu voz sea clara e
identifique si le hablan a Sergio o el usuario está conversando o viendo un
video (copia Wispr Flow para eso)».

Small pieces, all local and instant (no model call):

* ``clear_wav`` — the microphone, cleaner before speech-to-text: rumble and
  thumps cut (high-pass), the room's hiss gated out under the speech, and the
  level brought up to a steady peak. Whisper and Gemini hear words, not fans.
* ``clean`` — dictation the way a good dictation app writes it: fillers out
  («eh», «este…», «mmm»), stutters out («el el»), spoken self-corrections
  resolved («a las cinco, no, mejor a las seis» → «a las seis»), spoken
  punctuation in dictation («coma», «punto», «nueva línea»), capitals and a
  full stop. Sergio's own take on it; nothing is copied from any app.
* ``dictation`` — «dicta: …» / «escribe esto …» gives the clean text to type
  where the cursor is.
* ``addressee`` — who the words are for: ``"sergio"``, ``"persona"`` (a
  side chat, a phone call), ``"video"`` (a video, the TV, a song) or
  ``"duda"``. Inside the follow-up window a short question or an order is for
  Sergio; chatter with someone, third-person talk about him, a long monologue,
  YouTube phrases or sound playing on the PC are not.
* ``media_playing`` — is the PC playing sound right now (Windows Core Audio
  peak meter through comtypes, which pywinauto already brings)? ``None``
  where it cannot tell.
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
import wave
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(text.split())


# -- the microphone, clearer ------------------------------------------------------------


def clear_wav(wav: bytes) -> bytes:
    """A cleaner copy of a 16-bit mono WAV (the original if anything is odd)."""
    try:
        with wave.open(io.BytesIO(wav), "rb") as src:
            if src.getnchannels() != 1 or src.getsampwidth() != 2:
                return wav
            rate = src.getframerate()
            pcm = np.frombuffer(src.readframes(src.getnframes()), dtype=np.int16)
        if pcm.size < rate // 10:
            return wav
        x = pcm.astype(np.float32) / 32768.0
        if float(np.max(np.abs(x))) < 0.003:
            return wav  # silence: nothing to clean, nothing to bring up
        x = _high_pass(x, rate, 85.0)
        x = _gate(x, rate)
        peak = float(np.max(np.abs(x))) or 1.0
        if peak < 0.7:  # quiet speaker: bring it up, never above -3 dBFS
            x = x * min(8.0, 0.7 / peak)
        out = np.clip(x * 32767.0, -32768, 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as dst:
            dst.setnchannels(1)
            dst.setsampwidth(2)
            dst.setframerate(rate)
            dst.writeframes(out.tobytes())
        return buf.getvalue()
    except Exception:  # noqa: BLE001 — never lose what he said
        log.debug("clear_wav failed", exc_info=True)
        return wav


def _high_pass(x: np.ndarray, rate: int, cutoff: float) -> np.ndarray:
    """High-pass (the signal minus its moving average, all in numpy):
    desk thumps, rumble and DC go; the voice stays."""
    n = max(3, int(rate / cutoff))
    kernel = np.ones(n, dtype=np.float32) / n
    return (x - np.convolve(x, kernel, mode="same")).astype(np.float32)


def _gate(x: np.ndarray, rate: int) -> np.ndarray:
    """Soft noise gate: frames near the room's floor are turned down, speech
    stays. The floor is the quietest tenth of the recording."""
    frame = max(1, rate // 50)  # 20 ms
    n = x.size // frame
    if n < 5:
        return x
    rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    floor = float(np.percentile(rms, 10))
    gain = np.clip((rms - floor * 1.8) / (floor * 2.0 + 1e-6), 0.12, 1.0)
    out = x.copy()
    out[: n * frame] *= np.repeat(gain, frame).astype(np.float32)
    return out


# -- dictation, the way a person would write it ---------------------------------------

_FILLERS = re.compile(
    r"(?<!\w)(?:e+h+|e+m+|m+h*m+|a+h+|u+m+|uh+|este+(?=\s*[,.]|\s*\.\.\.)|"
    r"o sea(?=\s*,)|bueno(?=\s*,\s)|pues(?=\s*,)|like(?=\s*,)|you know(?=\s*,))(?!\w)[,.]*",
    re.I,
)
# «X, no, mejor Y» · «X, digo, Y» · «X, perdón, Y» · «X, quiero decir Y» · «X, I mean Y»
_CORRECTION = re.compile(
    r"([^,.;]*?)\s*,?\s*(?:no,?\s*(?:mejor|espera)|no\s*no|digo|perd[oó]n|"
    r"quiero decir|mejor dicho|corrijo|i mean|sorry|no wait|actually)\s*,?\s+(.+)",
    re.I,
)
_SPOKEN_PUNCT = (
    (r"\s*\b(?:nueva l[ií]nea|new line)\b\s*", "\n"),
    (r"\s*\b(?:nuevo p[aá]rrafo|new paragraph)\b\s*", "\n\n"),
    (r"\s*\b(?:punto y coma|semicolon)\b", ";"),
    (r"\s*\b(?:dos puntos|colon)\b", ":"),
    (r"\s*\b(?:signo de interrogaci[oó]n|question mark)\b", "?"),
    (r"\s*\b(?:signo de exclamaci[oó]n|exclamation mark)\b", "!"),
    (r"\s*\b(?:coma|comma)\b", ","),
    (r"\s*\b(?:punto final|punto|period|full stop)\b", "."),
)


def clean(text: str, *, dictation: bool = False) -> str:
    """Spoken words written cleanly. With *dictation*, spoken punctuation
    («coma», «punto», «nueva línea») becomes the real marks."""
    t = " ".join((text or "").split())
    if not t:
        return ""
    t = _FILLERS.sub(" ", t)
    t = re.sub(r"\b(\w+)(?:\s+\1\b)+", r"\1", t, flags=re.I)  # «el el» → «el»
    m = _CORRECTION.search(t)
    if m and m.group(2).strip():
        t = _replace_tail(m.group(1).strip(), m.group(2).strip())
    if dictation:
        for pattern, mark in _SPOKEN_PUNCT:
            t = re.sub(pattern, mark, t, flags=re.I)
    t = re.sub(r"[ \t]+([,.;:?!])", r"\1", t)
    t = re.sub(r"([,.;:?!])(?=[^\s,.;:?!])", r"\1 ", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip(" ,")
    if not t:
        return ""
    if not dictation:
        return t  # an order keeps his words as he said them
    t = t[0].upper() + t[1:]
    t = re.sub(r"([.?!][ \t]+|\n)(\w)", lambda g: g.group(1) + g.group(2).upper(), t)
    if t[-1] not in ".?!:\n":
        t += "."
    return t


def _replace_tail(before: str, after: str) -> str:
    """«quedamos a las cinco» + «a las seis» → «quedamos a las seis»: the
    correction replaces the last words it repeats the start of."""
    bw, aw = before.split(), after.split()
    first = _plain(aw[0]) if aw else ""
    for i in range(len(bw) - 1, -1, -1):
        if _plain(bw[i]) == first:
            return " ".join(bw[:i] + aw)
    keep = max(0, len(bw) - len(aw))  # nothing repeated: swap the last words
    return " ".join(bw[:keep] + aw) if keep else after


DICTATE = re.compile(
    r"^(?:sergio[, ]+)?(?:dicta|dictado|escribe esto|escribe lo siguiente|"
    r"type this|dictate)\s*[:,]?\s+(.+)$",
    re.I | re.S,
)


def dictation(text: str) -> Optional[str]:
    """The text to type when he dictates («dicta: …», «escribe esto …»)."""
    m = DICTATE.match((text or "").strip())
    if not m:
        return None
    return clean(m.group(1), dictation=True) or None


# -- who the words are for -----------------------------------------------------------------

_OTHER = re.compile(
    r"\b(no te hablo|no era para ti|no es para ti|hablo con otra persona|estoy hablando por telefono|"
    r"no te estoy hablando|estoy en llamada|estoy al telefono|ahorita te llamo|te paso con|"
    r"oye mama|oye papa|mi amor|carino|pasame (el|la|los|las)|alcanzame|vamos a comer|"
    r"que vas a querer|entonces le dije|fijate que|sabes que paso|te cuento que|me dijo que|"
    r"no manches|en serio te dijo|not talking to you|i'm on the phone)\b"
)
_MEDIA = re.compile(
    r"\b(suscribete|suscribanse|dale like|activa la campanita|bienvenidos a (mi|el|al) canal|"
    r"en este video|en el video de hoy|patrocinad|link en la descripcion|capitulo anterior|"
    r"proximo capitulo|temporada|episodio|subscribe|like and subscribe|in this video|"
    r"sponsored by|welcome back to)\b|[\[(](musica|music|aplausos|applause|risas|laughter)[\])]|♪"
)
_ORDER = re.compile(
    r"\b(busca|buscame|encuentra|abre|cierra|pon|ponme|reproduce|pausa|sube|baja|cambia|"
    r"dime|cuentame|explicame|leeme|resume|muestrame|haz|hazme|crea|escribe|dicta|manda|"
    r"envia|reserva|compra|pide|pideme|llama|agenda|recuerdame|apaga|enciende|prende|"
    r"necesito|quiero que|puedes|podrias|ayudame|que hora|cuanto|cuando|donde|como|"
    r"por que|que es|quien|cual|search|open|play|tell me|show me|can you|what|how|why)\b"
)


def addressee(
    text: str,
    *,
    name: str = "Sergio",
    in_conversation: bool = False,
    media_playing: Optional[bool] = None,
) -> str:
    """``"sergio"``, ``"persona"``, ``"video"`` or ``"duda"``."""
    norm = _plain(text)
    if not norm:
        return "duda"
    me = re.escape(_plain(name))
    if re.search(rf"\b{me}\s+(dijo|dice|es|era|hizo|estaba|me dijo|said|is)\b", norm):
        return "persona"  # talking ABOUT Sergio to someone
    if re.search(rf"\b{me}\b", norm):
        return "sergio"
    if _OTHER.search(norm):
        return "persona"
    if _MEDIA.search(norm):
        return "video"
    words = norm.split()
    if len(words) >= 35:
        return "video"  # a long unbroken monologue: a video or a talk
    if media_playing and not _ORDER.search(norm):
        return "video"  # the PC is playing sound and this is not an order
    if in_conversation:
        if _ORDER.search(norm) or len(words) <= 12:
            return "sergio"
        return "duda"
    return "sergio" if _ORDER.search(norm) and len(words) <= 20 else "duda"


# -- is the PC playing sound? --------------------------------------------------------------


def media_playing(threshold: float = 0.02) -> Optional[bool]:
    """True when the speakers are playing something right now (Windows)."""
    try:
        from ctypes import POINTER, c_float, c_uint, c_void_p

        import comtypes  # type: ignore[import-not-found]
        from comtypes import CLSCTX_ALL, COMMETHOD, GUID, HRESULT, IUnknown

        class IAudioMeterInformation(IUnknown):
            _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
            _methods_ = [
                COMMETHOD([], HRESULT, "GetPeakValue", (["out"], POINTER(c_float), "peak")),
            ]

        class IMMDevice(IUnknown):
            _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
            _methods_ = [
                COMMETHOD(
                    [], HRESULT, "Activate",
                    (["in"], POINTER(GUID), "iid"), (["in"], c_uint, "ctx"),
                    (["in"], c_void_p, "params"), (["out"], POINTER(POINTER(IUnknown)), "out"),
                ),  # fmt: skip
            ]

        class IMMDeviceEnumerator(IUnknown):
            _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
            _methods_ = [
                COMMETHOD([], HRESULT, "EnumAudioEndpoints"),
                COMMETHOD(
                    [], HRESULT, "GetDefaultAudioEndpoint",
                    (["in"], c_uint, "flow"), (["in"], c_uint, "role"),
                    (["out"], POINTER(POINTER(IMMDevice)), "device"),
                ),  # fmt: skip
            ]

        comtypes.CoInitialize()
        enum = comtypes.CoCreateInstance(
            GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"),
            IMMDeviceEnumerator,
            CLSCTX_ALL,
        )
        device = enum.GetDefaultAudioEndpoint(0, 1)  # eRender, eMultimedia
        meter = device.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
        peak = meter.QueryInterface(IAudioMeterInformation).GetPeakValue()
        return float(peak) > threshold
    except Exception:  # noqa: BLE001 — not Windows, no comtypes: cannot tell
        return None


__all__ = ["addressee", "clean", "clear_wav", "dictation", "media_playing"]
