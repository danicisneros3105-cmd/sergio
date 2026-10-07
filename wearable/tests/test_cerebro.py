"""Pruebas del cerebro de las gafas sin hardware (ni cámara, ni audio, ni red).

python -m pytest wearable/tests -q
"""

from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cerebro"))

import cerebro_sergio as cs  # noqa: E402

# --- Palabra clave ----------------------------------------------------------


@pytest.mark.parametrize(
    "texto, esperado, resto",
    [
        ("Sergio, ¿qué es esto?", True, "¿qué es esto?"),
        ("Oye Sergio qué hora es", True, "qué hora es"),
        ("¡Sérgio! Lee el cartel.", True, "Lee el cartel."),
        ("Serjio traduce eso", True, "traduce eso"),
        ("Sergio.", True, ""),
        ("ayer hablé con Sergio de fútbol", False, ""),
        ("el sergio de mi oficina", False, ""),
        ("Disculpa Sergio, ¿dónde estoy?", True, "¿dónde estoy?"),
        ("", False, ""),
    ],
)
def test_detectar_palabra_clave(texto, esperado, resto):
    assert cs.detectar_palabra_clave(texto) == (esperado, resto)


def test_palabra_clave_alias_jarvis():
    assert cs.detectar_palabra_clave("Jarbis, ¿qué ves?", ("sergio", "jarvis")) == (
        True,
        "¿qué ves?",
    )
    assert not cs.es_palabra_clave("sea", ("sergio",))


# --- HUD --------------------------------------------------------------------


def test_envolver_texto_respeta_limites():
    lineas = cs.envolver_texto(
        "Gire a la derecha en la calle Serrano 45 y luego siga recto hasta la plaza", 24, 3
    )
    assert len(lineas) == 3
    assert all(len(linea) <= 24 for linea in lineas)
    assert lineas[-1].endswith("…")
    assert cs.envolver_texto("Supercalifragilisticoespialidoso", 10, 5)[0] == "Supercalif"


# --- Audio puro ----------------------------------------------------------------


def test_remuestreador_por_bloques_igual_que_de_una_vez():
    t = np.arange(24_000) / 24_000
    senal = (np.sin(2 * np.pi * 440 * t) * 12_000).astype(np.int16)
    entero = cs.Remuestreador(24_000, 48_000).procesar(senal)
    r = cs.Remuestreador(24_000, 48_000)
    trozos = np.concatenate([r.procesar(senal[i : i + 997]) for i in range(0, senal.size, 997)])
    n = min(entero.size, trozos.size)
    assert abs(entero.size - trozos.size) <= 2
    assert np.max(np.abs(entero[:n].astype(int) - trozos[:n].astype(int))) <= 1
    assert abs(entero.size - 48_000) <= 2


def test_alineador_pcm_no_parte_muestras():
    muestras = np.arange(-50, 50, dtype=np.int16)
    datos = muestras.astype("<i2").tobytes()
    a = cs.AlineadorPCM()
    salida = np.concatenate([a.procesar(datos[i : i + 7]) for i in range(0, len(datos), 7)])
    assert np.array_equal(salida, muestras)


def test_wav_bytes_cabecera():
    wav = cs.wav_bytes(np.zeros(1600, np.int16), 16_000)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"


# --- Detector de voz ------------------------------------------------------------


def _bloques(segundos: float, amplitud: float, rng):
    n = int(segundos * cs.TASA_MICRO)
    if amplitud == 0:
        senal = rng.normal(0, 30, n)
    else:
        t = np.arange(n) / cs.TASA_MICRO
        senal = np.sin(2 * np.pi * 220 * t) * amplitud + rng.normal(0, 30, n)
    senal = senal.astype(np.int16)
    return [senal[i : i + cs.BLOQUE_MICRO] for i in range(0, n, cs.BLOQUE_MICRO)]


def test_segmentador_encuentra_una_frase_con_pre_roll():
    rng = np.random.default_rng(1)
    seg = cs.SegmentadorVoz()
    t, frases = 0.0, []
    for amp, dur in ((0, 1.0), (4000, 1.2), (0, 1.2)):
        for b in _bloques(dur, amp, rng):
            frases += seg.alimentar(b, t)
            t += b.size / cs.TASA_MICRO
    assert len(frases) == 1
    frase = frases[0]
    assert 1.2 <= frase.duracion <= 1.2 + 0.35 + 0.2  # voz + pre-roll + margen
    assert 0.95 <= frase.t_inicio <= 1.05  # empezó a hablar al segundo 1


def test_segmentador_ignora_golpes_cortos():
    rng = np.random.default_rng(2)
    seg = cs.SegmentadorVoz()
    t, frases = 0.0, []
    for amp, dur in ((0, 1.0), (6000, 0.06), (0, 1.5)):  # roce de 60 ms
        for b in _bloques(dur, amp, rng):
            frases += seg.alimentar(b, t)
            t += b.size / cs.TASA_MICRO
    assert frases == []


# --- Respuesta de la IA ---------------------------------------------------------


def test_parsear_respuesta_json_y_texto_libre():
    r = cs.parsear_respuesta(
        json.dumps({"voz": "Son 12 euros, señor.", "hud": ["12,00 €"], "icono": "info"})
    )
    assert r == cs.Respuesta("Son 12 euros, señor.", ["12,00 €"], "info")
    r = cs.parsear_respuesta('Claro: {"voz": "Hecho.", "hud": "Listo", "icono": "raro"}')
    assert r.voz == "Hecho." and r.hud == ["Listo"] and r.icono == "info"
    r = cs.parsear_respuesta("Solo texto")
    assert r.voz == "Solo texto" and r.hud == []


class _ClienteFalso:
    def __init__(self, rechazar_esquema=False):
        self.llamadas = []
        self.rechazar_esquema = rechazar_esquema
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._crear))

    def _crear(self, **kw):
        self.llamadas.append(kw)
        if self.rechazar_esquema and "response_format" in kw:
            raise RuntimeError("Unsupported parameter: response_format")
        contenido = json.dumps({"voz": "Una taza, señor.", "hud": [], "icono": "ninguno"})
        mensaje = types.SimpleNamespace(content=contenido)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=mensaje)])


def test_cerebro_envia_foto_en_base64_y_esquema():
    cliente = _ClienteFalso()
    cerebro = cs.CerebroIA(cliente, "gpt-4o", "auto", "Dani")
    r = cerebro.responder("¿Qué es esto?", b"\xff\xd8jpeg")
    assert r.voz == "Una taza, señor."
    kw = cliente.llamadas[0]
    assert kw["response_format"]["json_schema"]["strict"] is True
    usuario = kw["messages"][-1]["content"]
    assert usuario[1]["image_url"]["url"].startswith("data:image/jpeg;base64,/9")
    assert "Dani" in kw["messages"][0]["content"]
    # La segunda vuelta lleva el historial en texto, sin reenviar la foto.
    cerebro.responder("¿Y de qué color?", None)
    historial = cliente.llamadas[1]["messages"][1:-1]
    assert [m["role"] for m in historial] == ["user", "assistant"]
    assert all(isinstance(m["content"], str) for m in historial)


def test_cerebro_sin_json_schema_reintenta():
    cliente = _ClienteFalso(rechazar_esquema=True)
    r = cs.CerebroIA(cliente, "modelo-local", "auto", "Dani").responder("hola", None)
    assert r.voz == "Una taza, señor."
    assert "response_format" not in cliente.llamadas[-1]


# --- Voz: si ElevenLabs falla, OpenAI sin cortar nada a medias -------------------


class _ReproductorFalso:
    def __init__(self):
        self.reproducido = b""
        self.parar = types.SimpleNamespace(set=lambda: None)

    def reproducir(self, trozos):
        self.reproducido += b"".join(trozos)
        return True

    def callar(self):
        pass


def test_voz_cae_a_openai_si_elevenlabs_falla(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    rep = _ReproductorFalso()
    voz = cs.Voz("auto", None, rep)
    assert voz.modo == "elevenlabs"

    def falla(_texto):
        raise RuntimeError("401")
        yield b""  # pragma: no cover

    monkeypatch.setattr(voz, "_elevenlabs", falla)
    monkeypatch.setattr(voz, "_openai", lambda _t: iter([b"\x01\x00", b"\x02\x00"]))
    assert voz.decir("Hola, señor.")
    assert rep.reproducido == b"\x01\x00\x02\x00"


# --- Flujo completo con hardware simulado ---------------------------------------


class _CamaraFalsa:
    def __init__(self):
        self.pedidos = []

    def fotograma_en(self, t, antes=0.5, despues=0.35):
        self.pedidos.append(t)
        return cs.Fotograma(t=t, jpeg=b"foto", nitidez=100.0)


class _Registro:
    def __init__(self):
        self.eventos = []

    def __getattr__(self, nombre):
        return lambda *a, **k: self.eventos.append((nombre, a))


def _sergio_simulado(transcripciones):
    s = object.__new__(cs.SergioGafas)
    s.cfg = cs.Config()
    s.camara = _CamaraFalsa()
    textos = iter(transcripciones)
    s.transcriptor = types.SimpleNamespace(transcribir=lambda audio: next(textos))
    s.ordenes = []
    s.cerebro = types.SimpleNamespace(
        responder=lambda orden, jpeg: (
            s.ordenes.append((orden, jpeg)) or cs.Respuesta("Hecho, señor.", ["OK"], "ok")
        )
    )
    s.voz = _Registro()
    s.hud = _Registro()
    s.esperando_hasta = 0.0
    s.foto_congelada = None
    s.ultima_respuesta = None
    s.reiniciar_oido = cs.threading.Event()
    return s


def _frase(segundos=1.0, t=10.0):
    return cs.Frase(np.zeros(int(segundos * cs.TASA_MICRO), np.int16), t, t + segundos)


def test_flujo_orden_en_la_misma_frase_congela_la_foto_del_inicio():
    s = _sergio_simulado(["Sergio, ¿qué pone en ese cartel?"])
    s._atender_frase(_frase(t=42.0))
    assert s.ordenes == [("¿qué pone en ese cartel?", b"foto")]
    assert s.camara.pedidos == [pytest.approx(42.3)]
    assert ("decir", ("Hecho, señor.",)) in s.voz.eventos
    assert ("mostrar", (["OK"], "ok")) in s.hud.eventos


def test_flujo_nombre_solo_y_luego_la_orden():
    s = _sergio_simulado(["Sergio.", "¿Cuánto cuesta esto?"])
    s._atender_frase(_frase(t=5.0))
    assert s.ordenes == [] and s.esperando_hasta > time.monotonic()
    assert ("pitido", (880, 1)) in s.voz.eventos
    s._atender_frase(_frase(t=7.0))
    assert s.ordenes == [("¿Cuánto cuesta esto?", b"foto")]
    assert s.esperando_hasta == 0.0


def test_flujo_ignora_conversaciones_ajenas():
    s = _sergio_simulado(["mañana vemos a Sergio en la cena"])
    s._atender_frase(_frase(t=1.0))
    assert s.ordenes == [] and s.voz.eventos == []


def test_frase_larga_solo_transcribe_entera_si_empieza_por_sergio():
    llamadas = []
    s = _sergio_simulado([])

    def transcribir(audio):
        llamadas.append(audio.size)
        return "y entonces le dije que no" if len(llamadas) == 1 else ""

    s.transcriptor = types.SimpleNamespace(transcribir=transcribir)
    s._atender_frase(_frase(segundos=8.0))
    assert llamadas == [int(2.5 * cs.TASA_MICRO)]  # solo la cabeza
