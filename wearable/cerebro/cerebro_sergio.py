"""
===============================================================================
 SERGIO WEARABLE · BLOQUE 2 — EL CEREBRO EN LA LAPTOP
===============================================================================
 Centro de operaciones de las gafas. Une, en un solo proceso:

   Gafas (cámara USB o stream del Power-Brain) ──► OpenCV, búfer de 3 s
   Micrófono de las gafas ──► VAD (detector de voz) ──► Whisper ──► "Sergio"
   Fotograma congelado + orden ──► OpenAI GPT-4o Vision ──► respuesta JSON
   Respuesta ──► ElevenLabs (o TTS de OpenAI) ──► audífono invisible
   Respuesta ──► HUD blanco sobre negro absoluto ──► microdisplay waveguide
   Manilla BLE (teclas F13–F18) ──► escuchar, siguiente, silencio, privado

 USO
   pip install -r requirements.txt
   python cerebro_sergio.py --listar                 # ver cámaras, audio y pantallas
   python cerebro_sergio.py --camara 1 --microfono "Gafas" \
          --audifono "Earbud" --monitor 1

 CLAVES (variables de entorno, o en ~/.openjarvis/sergio.env como el resto de
 Sergio, o en un archivo .env junto a este script):
   OPENAI_API_KEY        obligatoria (visión; también Whisper API y TTS de respaldo)
   ELEVENLABS_API_KEY    opcional (voz de Sergio; sin ella se usa el TTS de OpenAI)
   ELEVENLABS_VOICE_ID   opcional (por defecto, la voz J Thomas de Sergio)
   SERGIO_OWNER_NAME     opcional (tu nombre, para la personalidad de Sergio)
   SERGIO_OPENAI_BASE_URL opcional (otro endpoint compatible con OpenAI)

 Todo el código pesado (cv2, sounddevice, openai, tkinter...) se importa solo
 cuando se usa: la lógica pura (VAD, palabra clave, remuestreo, HUD) se puede
 probar sin hardware (ver wearable/tests/test_cerebro.py).
===============================================================================
"""

from __future__ import annotations

import argparse
import base64
import collections
import dataclasses
import io
import json
import logging
import os
import queue
import re
import signal
import sys
import threading
import time
import unicodedata
import wave
from pathlib import Path
from typing import Callable, Iterable, Iterator

import numpy as np

log = logging.getLogger("sergio.gafas")

# =============================================================================
# 1) CONSTANTES DE INGENIERÍA
# =============================================================================

TASA_MICRO = 16_000  # Whisper trabaja a 16 kHz mono
BLOQUE_MICRO = 480  # 30 ms por bloque: resolución del detector de voz
TASA_VOZ = 24_000  # ElevenLabs pcm_24000 y OpenAI "pcm" salen a 24 kHz, int16
MAX_LADO_IMAGEN = 1024  # GPT-4o no gana detalle por encima de ~1024 px por lado
CALIDAD_JPEG = 85
INTERVALO_FOTOGRAMAS = 0.12  # ~8 fotos/s en el búfer circular
SEGUNDOS_BUFER_VIDEO = 3.0
ESPERA_COMANDO = 8.0  # s para hablar tras "Sergio" a secas o un toque
PALABRAS_CLAVE = ("sergio",)
VOZ_ELEVENLABS = "f5gk6ENs9vgDBvfkTj7e"  # J Thomas: la misma voz de Sergio
MODELO_ELEVENLABS = "eleven_flash_v2_5"  # ~100 ms hasta el primer audio
MODELO_VISION = "gpt-4o"
MODELO_TRANSCRIPCION_API = "gpt-4o-mini-transcribe"
MODELO_TTS_OPENAI = "gpt-4o-mini-tts"
VOZ_TTS_OPENAI = "onyx"
ICONOS = ("ninguno", "info", "alerta", "ok", "navegacion", "persona")

# Teclas que envía la manilla (Bloque 3). F13–F18 no existen en un teclado
# normal: nunca chocan con lo que escribes en la laptop.
TECLAS_MANILLA = {
    "f13": "escuchar",  # Clic: toque
    "f16": "describir",  # Clic: mantener
    "f14": "siguiente",  # Siguiente: toque
    "f17": "repetir",  # Siguiente: doble toque
    "f15": "silencio",  # Silencio: toque
    "f18": "privado",  # Silencio: mantener
}

PERSONALIDAD = """\
Eres Sergio, el asistente personal de {owner}, al estilo de JARVIS, y ahora \
vives en sus gafas: ves lo que él ve (la foto adjunta es SU punto de vista, \
tomada en el instante en que te llamó) y le hablas al oído por un audífono \
invisible. Hablas siempre en español. A tu dueño le dices «señor»: respeto \
elegante con un brillo de ironía. Tranquilo, sin prisa, pocas palabras bien \
elegidas, humor seco en media frase y solo cuando no estorba; si el momento es \
serio, cero humor y toda la ayuda.

Reglas de las gafas:
- Te escucha en la calle: la respuesta hablada ("voz") va directa al grano, \
1 o 2 frases, máximo 45 palabras. Nada de listas ni markdown en la voz.
- Si te pregunta por algo visual, mira la foto con atención: lee textos, \
precios, carteles y matrículas exactamente como aparecen. Si no se ve bien, \
dilo con sencillez («No alcanzo a leerlo, señor; acérquese un poco»). Nunca \
inventes lo que no ves.
- "hud" son 0 a 3 líneas que flotan en su ojo derecho. Úsalas SOLO si aportan: \
cifras, nombres, direcciones, horas, traducciones cortas o una alerta. Máximo \
24 caracteres por línea. Si la voz basta, deja la lista vacía.
- "icono": alerta (peligro o urgencia), ok (hecho/confirmado), navegacion \
(direcciones), persona (alguien), info (dato), ninguno.
- No identifiques a desconocidos por su cara ni especules sobre datos \
sensibles de otras personas.
"""

ESQUEMA_RESPUESTA = {
    "type": "object",
    "properties": {
        "voz": {
            "type": "string",
            "description": "Lo que Sergio dice al oído: 1-2 frases en español.",
        },
        "hud": {
            "type": "array",
            "items": {"type": "string"},
            "description": "0-3 líneas cortas (<=24 caracteres) para el HUD.",
        },
        "icono": {"type": "string", "enum": list(ICONOS)},
    },
    "required": ["voz", "hud", "icono"],
    "additionalProperties": False,
}


# =============================================================================
# 2) CONFIGURACIÓN
# =============================================================================


def cargar_archivo_env(ruta: Path) -> None:
    """Carga CLAVE=valor de un archivo .env sin pisar variables ya definidas."""
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip().removeprefix("export ").strip()
        valor = valor.strip().strip('"').strip("'")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


@dataclasses.dataclass
class Config:
    camara: int | str = 1
    resolucion: tuple[int, int] = (1280, 720)
    rotacion: int = 0
    microfono: str | None = None
    audifono: str | None = None
    monitor: int | None = None
    sin_hud: bool = False
    transcripcion: str = "auto"  # auto | local | api
    modelo_whisper: str = "base"
    voz: str = "auto"  # auto | elevenlabs | openai
    modelo_vision: str = MODELO_VISION
    detalle_imagen: str = "auto"  # low | high | auto
    palabras_clave: tuple[str, ...] = PALABRAS_CLAVE
    espacio_escucha: bool = False  # la barra espaciadora también activa
    owner: str = "su dueño"


# =============================================================================
# 3) TEXTO: normalización y detección de la palabra clave
# =============================================================================


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos: "¡Sérgio!" -> "sergio"."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9ñ ]+", " ", texto).strip()


def distancia_edicion(a: str, b: str) -> int:
    """Distancia de Levenshtein (para "Serjio", "Sergi", "Jarbis"...)."""
    if a == b:
        return 0
    previa = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            actual.append(min(previa[j] + 1, actual[j - 1] + 1, previa[j - 1] + (ca != cb)))
        previa = actual
    return previa[-1]


def es_palabra_clave(palabra: str, palabras: Iterable[str]) -> bool:
    palabra = normalizar(palabra).replace(" ", "")
    for clave in palabras:
        clave = normalizar(clave)
        if palabra == clave:
            return True
        # Una letra de margen solo en nombres largos: "serjio" sí, "sea" no.
        if len(clave) >= 5 and len(palabra) >= 4 and distancia_edicion(palabra, clave) <= 1:
            return True
    return False


MULETILLAS = {
    "oye",
    "oiga",
    "hey",
    "ey",
    "hola",
    "ok",
    "okay",
    "vale",
    "eh",
    "ah",
    "y",
    "disculpa",
    "perdona",
    "bueno",
    "mira",
}


def detectar_palabra_clave(
    texto: str, palabras: Iterable[str] = PALABRAS_CLAVE, max_posicion: int = 1
) -> tuple[bool, str]:
    """¿La frase empieza por "Sergio"? Devuelve (sí/no, resto de la orden).

    Solo cuenta si el nombre abre la frase (como mucho tras muletillas como
    "oye" o "disculpa"): así "ayer hablé con Sergio" o "el Sergio de la
    oficina" no despiertan al asistente. El resto se devuelve
    con su puntuación original, que ayuda al modelo a entender la pregunta.
    """
    palabras = tuple(palabras)
    tokens = list(re.finditer(r"\S+", texto))
    contadas = 0
    for token in tokens:
        crudo = token.group(0)
        if es_palabra_clave(crudo, palabras):
            resto = texto[token.end() :].lstrip(" ,.:;!?-—…")
            return True, resto.strip()
        limpio = normalizar(crudo)
        if not limpio:
            continue  # signo suelto
        if limpio in MULETILLAS:
            continue
        contadas += 1
        if contadas >= max_posicion:
            break
    return False, ""


def envolver_texto(texto: str, max_caracteres: int = 24, max_lineas: int = 3) -> list[str]:
    """Parte un texto en líneas cortas para el HUD (corta con "…" si sobra)."""
    lineas: list[str] = []
    for parrafo in str(texto).splitlines() or [""]:
        actual = ""
        for palabra in parrafo.split():
            while len(palabra) > max_caracteres:  # palabras larguísimas
                if actual:
                    lineas.append(actual)
                    actual = ""
                lineas.append(palabra[:max_caracteres])
                palabra = palabra[max_caracteres:]
            candidata = f"{actual} {palabra}".strip()
            if len(candidata) <= max_caracteres:
                actual = candidata
            else:
                lineas.append(actual)
                actual = palabra
        if actual:
            lineas.append(actual)
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        ultima = lineas[-1]
        lineas[-1] = (ultima[: max_caracteres - 1].rstrip() + "…") if ultima else "…"
    return lineas


# =============================================================================
# 4) AUDIO: utilidades puras (WAV, remuestreo, alineación de PCM)
# =============================================================================


def wav_bytes(audio: np.ndarray, tasa: int) -> bytes:
    """int16 mono -> archivo WAV en memoria (para la API de transcripción)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tasa)
        w.writeframes(np.asarray(audio, dtype=np.int16).tobytes())
    return buf.getvalue()


class Remuestreador:
    """Remuestreo lineal en streaming, sin saltos entre bloques.

    Guarda la última muestra del bloque anterior y la posición fraccionaria de
    la siguiente muestra de salida, de modo que trocear la señal no introduce
    clics. Suficiente para voz (el contenido útil está por debajo de 8 kHz).
    """

    def __init__(self, origen: int, destino: int) -> None:
        self.origen = int(origen)
        self.destino = int(destino)
        self.paso = self.origen / self.destino
        self.pos = 0.0
        self.previa: float | None = None

    def procesar(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x)
        if self.origen == self.destino or x.size == 0:
            return x.astype(np.int16, copy=False)
        datos = x.astype(np.float32)
        buf = datos if self.previa is None else np.concatenate(([self.previa], datos))
        n = buf.size
        if n < 2:
            self.previa = float(buf[-1])
            return np.zeros(0, dtype=np.int16)
        posiciones = np.arange(self.pos, n - 1, self.paso)
        salida = np.interp(posiciones, np.arange(n), buf)
        siguiente = (posiciones[-1] + self.paso) if posiciones.size else self.pos
        self.pos = siguiente - (n - 1)  # relativo al próximo búfer (empieza en buf[-1])
        self.previa = float(buf[-1])
        return np.clip(np.round(salida), -32768, 32767).astype(np.int16)


class AlineadorPCM:
    """Las APIs de voz entregan bytes en trozos arbitrarios; una muestra int16
    puede quedar partida entre dos trozos. Esto guarda el byte sobrante."""

    def __init__(self) -> None:
        self.resto = b""

    def procesar(self, trozo: bytes) -> np.ndarray:
        datos = self.resto + trozo
        corte = len(datos) - (len(datos) % 2)
        self.resto = datos[corte:]
        return np.frombuffer(datos[:corte], dtype="<i2").astype(np.int16)


def tono(frecuencia: float = 880.0, duracion: float = 0.09, volumen: float = 0.25) -> bytes:
    """Pitido corto con fundido (confirma que Sergio escucha), PCM 24 kHz."""
    t = np.arange(int(TASA_VOZ * duracion)) / TASA_VOZ
    envolvente = np.minimum(1.0, np.minimum(t, t[::-1]) / 0.01)
    onda = np.sin(2 * np.pi * frecuencia * t) * envolvente * volumen
    return (onda * 32767).astype("<i2").tobytes()


# =============================================================================
# 5) DETECTOR DE VOZ (VAD) por energía con suelo de ruido adaptativo
# =============================================================================


@dataclasses.dataclass
class Frase:
    audio: np.ndarray  # int16, 16 kHz
    t_inicio: float  # time.monotonic() del inicio de la voz
    t_fin: float

    @property
    def duracion(self) -> float:
        return self.audio.size / TASA_MICRO


class SegmentadorVoz:
    """Convierte bloques de micrófono en frases completas.

    * En silencio aprende el ruido de fondo (media móvil del RMS).
    * La voz empieza cuando el RMS supera ``factor_inicio`` veces ese ruido
      durante ``bloques_inicio`` bloques seguidos (evita roces y golpes).
    * Termina tras ``silencio_fin`` segundos por debajo de ``factor_fin``.
    * Se conservan ``pre_roll`` segundos previos para no cortar la "S" de Sergio.
    """

    def __init__(
        self,
        tasa: int = TASA_MICRO,
        umbral_minimo: float = 300.0,
        factor_inicio: float = 3.0,
        factor_fin: float = 1.8,
        bloques_inicio: int = 3,
        silencio_fin: float = 0.75,
        pre_roll: float = 0.35,
        duracion_minima: float = 0.35,
        duracion_maxima: float = 15.0,
    ) -> None:
        self.tasa = tasa
        self.umbral_minimo = umbral_minimo
        self.factor_inicio = factor_inicio
        self.factor_fin = factor_fin
        self.bloques_inicio = bloques_inicio
        self.silencio_fin = silencio_fin
        self.pre_roll = pre_roll
        self.duracion_minima = duracion_minima
        self.duracion_maxima = duracion_maxima
        self.ruido = umbral_minimo / factor_inicio
        self.reiniciar()

    def reiniciar(self) -> None:
        self.hablando = False
        self.previos: collections.deque[tuple[np.ndarray, float]] = collections.deque()
        self.candidatos: list[tuple[np.ndarray, float]] = []
        self.bloques: list[np.ndarray] = []
        self.t_inicio = 0.0
        self.silencio = 0.0
        self.muestras = 0

    @staticmethod
    def rms(bloque: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(bloque.astype(np.float32))))) if bloque.size else 0.0

    def alimentar(self, bloque: np.ndarray, t_bloque: float) -> list[Frase]:
        """Procesa un bloque (int16) capturado en ``t_bloque``; devuelve frases cerradas."""
        frases: list[Frase] = []
        energia = self.rms(bloque)
        duracion = bloque.size / self.tasa
        umbral_inicio = max(self.umbral_minimo, self.ruido * self.factor_inicio)
        umbral_fin = max(self.umbral_minimo * 0.6, self.ruido * self.factor_fin)

        if not self.hablando:
            if energia >= umbral_inicio:
                self.candidatos.append((bloque, t_bloque))
                if len(self.candidatos) >= self.bloques_inicio:
                    self._empezar()
            else:
                # Ruido de fondo: aprender despacio y guardar como pre-roll.
                for viejo in self.candidatos:
                    self._guardar_previo(*viejo)
                self.candidatos.clear()
                self.ruido = max(20.0, 0.97 * self.ruido + 0.03 * energia)
                self._guardar_previo(bloque, t_bloque)
            return frases

        self.bloques.append(bloque)
        self.muestras += bloque.size
        self.silencio = self.silencio + duracion if energia < umbral_fin else 0.0
        largo = self.muestras / self.tasa
        if self.silencio >= self.silencio_fin or largo >= self.duracion_maxima:
            frase = self._cerrar(t_bloque + duracion)
            if frase is not None:
                frases.append(frase)
        return frases

    def _guardar_previo(self, bloque: np.ndarray, t: float) -> None:
        self.previos.append((bloque, t))
        total = sum(b.size for b, _ in self.previos)
        while self.previos and total - self.previos[0][0].size >= self.pre_roll * self.tasa:
            total -= self.previos.popleft()[0].size

    def _empezar(self) -> None:
        self.hablando = True
        self.t_inicio = self.candidatos[0][1]
        self.bloques = [b for b, _ in self.previos] + [b for b, _ in self.candidatos]
        self.muestras = sum(b.size for b in self.bloques)
        self.previos.clear()
        self.candidatos.clear()
        self.silencio = 0.0

    def _cerrar(self, t_fin: float) -> Frase | None:
        audio = np.concatenate(self.bloques) if self.bloques else np.zeros(0, np.int16)
        # Quitar el silencio final (salvo un margen de 0.15 s).
        sobrante = int(max(0.0, self.silencio - 0.15) * self.tasa)
        if sobrante:
            audio = audio[: max(0, audio.size - sobrante)]
        t_inicio = self.t_inicio
        self.reiniciar()
        if audio.size / self.tasa < self.duracion_minima:
            return None
        return Frase(audio=audio.astype(np.int16), t_inicio=t_inicio, t_fin=t_fin)


# =============================================================================
# 6) DISPOSITIVOS DE AUDIO (búsqueda por nombre)
# =============================================================================


def buscar_dispositivo(nombre: str | int | None, tipo: str) -> int | None:
    """Índice de sounddevice cuyo nombre contiene ``nombre`` (sin mayúsculas).

    ``tipo`` es "entrada" o "salida". None = dispositivo por defecto del sistema.
    """
    if nombre is None or nombre == "":
        return None
    if isinstance(nombre, int) or str(nombre).isdigit():
        return int(nombre)
    import sounddevice as sd

    canal = "max_input_channels" if tipo == "entrada" else "max_output_channels"
    buscado = normalizar(str(nombre))
    for indice, info in enumerate(sd.query_devices()):
        if info[canal] > 0 and buscado in normalizar(info["name"]):
            return indice
    raise RuntimeError(f"No encuentro el dispositivo de {tipo} «{nombre}». Usa --listar.")


# =============================================================================
# 7) CÁMARA DE LAS GAFAS con búfer circular y "congelado" del fotograma
# =============================================================================


@dataclasses.dataclass
class Fotograma:
    t: float  # time.monotonic() de la captura
    jpeg: bytes
    nitidez: float  # varianza del laplaciano: más alto = menos movido


class CamaraGafas(threading.Thread):
    """Lee la cámara sin parar y guarda ~3 s de fotos JPEG con su nitidez.

    Al oír "Sergio" se elige la foto MÁS NÍTIDA tomada justo cuando empezaste
    a hablar: con la cabeza en movimiento, la última foto suele salir movida.
    ``fuente`` puede ser un índice (cámara USB) o una URL rtsp/http (stream del
    Power-Brain por Wi-Fi).
    """

    def __init__(self, fuente: int | str, resolucion=(1280, 720), rotacion: int = 0) -> None:
        super().__init__(name="camara-gafas", daemon=True)
        self.fuente = fuente
        self.resolucion = resolucion
        self.rotacion = rotacion
        self.bufer: collections.deque[Fotograma] = collections.deque(
            maxlen=int(SEGUNDOS_BUFER_VIDEO / INTERVALO_FOTOGRAMAS) + 2
        )
        self.cerrojo = threading.Lock()
        self.parar = threading.Event()
        self.pausada = threading.Event()  # modo privado: no guarda nada
        self.conectada = threading.Event()

    def _abrir(self):
        import cv2

        if isinstance(self.fuente, int):
            if sys.platform.startswith("win"):
                cap = cv2.VideoCapture(self.fuente, cv2.CAP_DSHOW)  # abre en <1 s
            elif sys.platform == "darwin":
                cap = cv2.VideoCapture(self.fuente, cv2.CAP_AVFOUNDATION)
            else:
                cap = cv2.VideoCapture(self.fuente, cv2.CAP_V4L2)
            # MJPG: 720p a 30 fps sin saturar el USB 2.0 del cable de las gafas.
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolucion[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolucion[1])
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # siempre la imagen más reciente
        else:
            cap = cv2.VideoCapture(self.fuente, cv2.CAP_FFMPEG)
        return cap

    def _procesar(self, imagen) -> Fotograma | None:
        import cv2

        if self.rotacion == 90:
            imagen = cv2.rotate(imagen, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotacion == 180:
            imagen = cv2.rotate(imagen, cv2.ROTATE_180)
        elif self.rotacion == 270:
            imagen = cv2.rotate(imagen, cv2.ROTATE_90_COUNTERCLOCKWISE)
        alto, ancho = imagen.shape[:2]
        escala = MAX_LADO_IMAGEN / max(alto, ancho)
        if escala < 1.0:
            imagen = cv2.resize(
                imagen, (int(ancho * escala), int(alto * escala)), interpolation=cv2.INTER_AREA
            )
        gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        pequena = cv2.resize(gris, (320, int(320 * gris.shape[0] / gris.shape[1])))
        nitidez = float(cv2.Laplacian(pequena, cv2.CV_64F).var())
        ok, jpeg = cv2.imencode(".jpg", imagen, [int(cv2.IMWRITE_JPEG_QUALITY), CALIDAD_JPEG])
        if not ok:
            return None
        return Fotograma(t=time.monotonic(), jpeg=jpeg.tobytes(), nitidez=nitidez)

    def run(self) -> None:
        espera = 1.0
        while not self.parar.is_set():
            cap = self._abrir()
            if not cap.isOpened():
                log.warning("Cámara %r no disponible; reintento en %.0f s", self.fuente, espera)
                self.parar.wait(espera)
                espera = min(espera * 2, 15.0)
                continue
            log.info("Cámara de las gafas conectada (%r)", self.fuente)
            self.conectada.set()
            espera, fallos, ultima = 1.0, 0, 0.0
            while not self.parar.is_set():
                ok, imagen = cap.read()  # leer siempre vacía el búfer del driver
                if not ok or imagen is None:
                    fallos += 1
                    if fallos > 30:
                        log.warning("La cámara dejó de enviar imagen; reconectando")
                        break
                    time.sleep(0.02)
                    continue
                fallos = 0
                ahora = time.monotonic()
                if self.pausada.is_set() or ahora - ultima < INTERVALO_FOTOGRAMAS:
                    continue
                ultima = ahora
                fotograma = self._procesar(imagen)
                if fotograma is not None:
                    with self.cerrojo:
                        self.bufer.append(fotograma)
            self.conectada.clear()
            cap.release()

    def fotograma_en(self, t: float, antes: float = 0.5, despues: float = 0.35) -> Fotograma | None:
        """La foto más nítida en [t-antes, t+despues]; si no hay, la más cercana."""
        with self.cerrojo:
            fotos = list(self.bufer)
        if not fotos:
            return None
        ventana = [f for f in fotos if t - antes <= f.t <= t + despues]
        if ventana:
            return max(ventana, key=lambda f: f.nitidez)
        return min(fotos, key=lambda f: abs(f.t - t))

    def vaciar(self) -> None:
        with self.cerrojo:
            self.bufer.clear()


# =============================================================================
# 8) MICRÓFONO DE LAS GAFAS
# =============================================================================


class Microfono:
    """Captura continua a 16 kHz mono (remuestrea si el driver no lo admite)."""

    def __init__(self, dispositivo: str | None) -> None:
        self.indice = buscar_dispositivo(dispositivo, "entrada")
        self.cola: queue.Queue[tuple[np.ndarray, float]] = queue.Queue(maxsize=400)
        self.stream = None
        self.remuestreador: Remuestreador | None = None
        self.pendiente = np.zeros(0, dtype=np.int16)

    def iniciar(self) -> None:
        import sounddevice as sd

        try:
            sd.check_input_settings(
                device=self.indice, samplerate=TASA_MICRO, channels=1, dtype="int16"
            )
            tasa = TASA_MICRO
        except Exception:  # noqa: BLE001 — p. ej. WASAPI solo acepta 48 kHz
            info = sd.query_devices(self.indice, "input")
            tasa = int(info["default_samplerate"])
            self.remuestreador = Remuestreador(tasa, TASA_MICRO)
        bloque = int(BLOQUE_MICRO * tasa / TASA_MICRO)
        self.stream = sd.InputStream(
            device=self.indice,
            samplerate=tasa,
            channels=1,
            dtype="int16",
            blocksize=bloque,
            callback=self._callback,
        )
        self.stream.start()
        log.info(
            "Micrófono abierto: %s a %d Hz", sd.query_devices(self.indice, "input")["name"], tasa
        )

    def _callback(self, datos, frames, tiempo, estado) -> None:  # hilo de audio
        if estado:
            log.debug("Micrófono: %s", estado)
        t = time.monotonic() - frames / (self.stream.samplerate if self.stream else TASA_MICRO)
        muestras = datos[:, 0].copy()
        if self.remuestreador is not None:
            muestras = self.remuestreador.procesar(muestras)
        # Reagrupar en bloques exactos de 30 ms para el detector de voz.
        self.pendiente = np.concatenate((self.pendiente, muestras))
        while self.pendiente.size >= BLOQUE_MICRO:
            bloque, self.pendiente = self.pendiente[:BLOQUE_MICRO], self.pendiente[BLOQUE_MICRO:]
            try:
                self.cola.put_nowait((bloque, t))
            except queue.Full:  # el proceso va atrasado: se descarta lo más viejo
                try:
                    self.cola.get_nowait()
                except queue.Empty:
                    pass
            t += BLOQUE_MICRO / TASA_MICRO

    def cerrar(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()


# =============================================================================
# 9) TRANSCRIPCIÓN: Whisper local (faster-whisper) o API de OpenAI
# =============================================================================


class Transcriptor:
    def __init__(self, modo: str, modelo_local: str, cliente_openai) -> None:
        self.cliente = cliente_openai
        self.modelo_local = modelo_local
        self.whisper = None
        if modo in ("auto", "local"):
            try:
                from faster_whisper import WhisperModel  # noqa: F401

                self.modo = "local"
            except ImportError:
                if modo == "local":
                    raise
                log.info("faster-whisper no está instalado: uso la API de OpenAI para transcribir")
                self.modo = "api"
        else:
            self.modo = "api"

    def preparar(self) -> None:
        """Carga el modelo local al arrancar (no al primer "Sergio")."""
        if self.modo == "local" and self.whisper is None:
            from faster_whisper import WhisperModel

            log.info("Cargando Whisper local «%s»…", self.modelo_local)
            self.whisper = WhisperModel(self.modelo_local, device="auto", compute_type="int8")

    def transcribir(self, audio: np.ndarray) -> str:
        if audio.size < TASA_MICRO * 0.2:
            return ""
        if self.modo == "local":
            self.preparar()
            segmentos, _ = self.whisper.transcribe(
                audio.astype(np.float32) / 32768.0,
                language="es",
                beam_size=1,
                initial_prompt="Sergio.",  # sesga el reconocimiento hacia el nombre
                condition_on_previous_text=False,
                vad_filter=False,  # ya lo hizo nuestro detector
            )
            return " ".join(s.text.strip() for s in segmentos).strip()
        respuesta = self.cliente.audio.transcriptions.create(
            model=MODELO_TRANSCRIPCION_API,
            file=("voz.wav", wav_bytes(audio, TASA_MICRO), "audio/wav"),
            language="es",
            prompt="Sergio.",
        )
        return (getattr(respuesta, "text", "") or "").strip()


# =============================================================================
# 10) CEREBRO: GPT-4o Vision con respuesta estructurada (voz + HUD + icono)
# =============================================================================


@dataclasses.dataclass
class Respuesta:
    voz: str
    hud: list[str]
    icono: str = "ninguno"


def parsear_respuesta(texto: str) -> Respuesta:
    """JSON del modelo -> Respuesta. Tolera texto alrededor o JSON ausente."""
    texto = (texto or "").strip()
    datos = None
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        encontrado = re.search(r"\{.*\}", texto, re.DOTALL)
        if encontrado:
            try:
                datos = json.loads(encontrado.group(0))
            except json.JSONDecodeError:
                datos = None
    if not isinstance(datos, dict):
        return Respuesta(voz=texto or "No tengo respuesta, señor.", hud=[], icono="ninguno")
    voz = str(datos.get("voz") or "").strip()
    hud_crudo = datos.get("hud") or []
    if isinstance(hud_crudo, str):
        hud_crudo = [hud_crudo]
    hud: list[str] = []
    for linea in hud_crudo:
        hud.extend(envolver_texto(str(linea), 24, 3))
    hud = [h for h in hud if h.strip()][:3]
    icono = str(datos.get("icono") or "ninguno").strip().lower()
    if icono not in ICONOS:
        icono = "info" if hud else "ninguno"
    return Respuesta(voz=voz or " ".join(hud), hud=hud, icono=icono)


class CerebroIA:
    def __init__(self, cliente_openai, modelo: str, detalle: str, owner: str) -> None:
        self.cliente = cliente_openai
        self.modelo = modelo
        self.detalle = detalle
        self.sistema = PERSONALIDAD.format(owner=owner)
        self.historial: collections.deque[dict] = collections.deque(maxlen=12)
        self.ultimo_uso = 0.0
        self.esquema_estricto = True

    def responder(self, orden: str, jpeg: bytes | None) -> Respuesta:
        # Una pausa larga = conversación nueva (menos tokens, menos confusión).
        if time.monotonic() - self.ultimo_uso > 600:
            self.historial.clear()
        contenido: list[dict] = [{"type": "text", "text": orden}]
        if jpeg:
            b64 = base64.b64encode(jpeg).decode("ascii")
            contenido.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": self.detalle},
                }
            )
        mensajes = [{"role": "system", "content": self.sistema}, *self.historial]
        mensajes.append({"role": "user", "content": contenido})
        texto = self._llamar(mensajes)
        respuesta = parsear_respuesta(texto)
        # El historial guarda solo texto: las fotos viejas no se reenvían.
        nota = " [con la foto de lo que veía]" if jpeg else ""
        self.historial.append({"role": "user", "content": orden + nota})
        self.historial.append({"role": "assistant", "content": respuesta.voz})
        self.ultimo_uso = time.monotonic()
        return respuesta

    def _llamar(self, mensajes: list[dict]) -> str:
        argumentos = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": 0.4,
            "max_completion_tokens": 400,
        }
        if self.esquema_estricto:
            argumentos["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "respuesta_sergio",
                    "strict": True,
                    "schema": ESQUEMA_RESPUESTA,
                },
            }
        try:
            completado = self.cliente.chat.completions.create(**argumentos)
        except Exception as error:  # noqa: BLE001
            # Modelos/servidores compatibles que no aceptan json_schema: se pide
            # el JSON en el propio mensaje y se parsea de forma tolerante.
            if not self.esquema_estricto or "response_format" not in str(error):
                raise
            log.info("El modelo no admite json_schema; sigo con JSON en el prompt")
            self.esquema_estricto = False
            argumentos.pop("response_format")
            argumentos["messages"] = [
                {
                    "role": "system",
                    "content": self.sistema
                    + '\nResponde SOLO con JSON: {"voz": "...", "hud": ["..."], "icono": "..."}',
                },
                *mensajes[1:],
            ]
            completado = self.cliente.chat.completions.create(**argumentos)
        return completado.choices[0].message.content or ""


# =============================================================================
# 11) VOZ: ElevenLabs (voz de Sergio) o TTS de OpenAI -> audífono invisible
# =============================================================================


class ReproductorAudifono:
    """Reproduce PCM 24 kHz en el audífono elegido, interrumpible en < 60 ms."""

    def __init__(self, dispositivo: str | None) -> None:
        import sounddevice as sd

        self.indice = buscar_dispositivo(dispositivo, "salida")
        info = sd.query_devices(self.indice, "output")
        self.nombre = info["name"]
        self.canales = max(1, min(2, int(info["max_output_channels"])))
        try:
            sd.check_output_settings(
                device=self.indice, samplerate=TASA_VOZ, channels=self.canales, dtype="int16"
            )
            self.tasa = TASA_VOZ
        except Exception:  # noqa: BLE001
            self.tasa = int(info["default_samplerate"])
        self.parar = threading.Event()
        self.hablando = threading.Event()
        self.fin_ultima = 0.0
        log.info("Audífono: %s (%d Hz, %d canal/es)", self.nombre, self.tasa, self.canales)

    def reproducir(self, trozos: Iterable[bytes]) -> bool:
        """Reproduce trozos PCM int16 24 kHz. Devuelve False si se interrumpió."""
        import sounddevice as sd

        self.parar.clear()
        self.hablando.set()
        alineador = AlineadorPCM()
        remuestreo = Remuestreador(TASA_VOZ, self.tasa)
        paso = int(self.tasa * 0.05)  # escribir de 50 en 50 ms para poder cortar
        completo = True
        try:
            with sd.OutputStream(
                device=self.indice, samplerate=self.tasa, channels=self.canales, dtype="int16"
            ) as stream:
                for trozo in trozos:
                    muestras = remuestreo.procesar(alineador.procesar(trozo))
                    for i in range(0, muestras.size, paso):
                        if self.parar.is_set():
                            stream.abort()
                            completo = False
                            return False
                        parte = muestras[i : i + paso]
                        stream.write(np.repeat(parte[:, None], self.canales, axis=1))
                    if self.parar.is_set():
                        stream.abort()
                        completo = False
                        return False
            return True
        finally:
            if isinstance(trozos, Iterator) and hasattr(trozos, "close"):
                trozos.close()  # cierra la descarga HTTP si se cortó a medias
            self.hablando.clear()
            self.fin_ultima = time.monotonic()
            if not completo:
                log.info("Voz interrumpida")

    def callar(self) -> None:
        self.parar.set()


class Voz:
    def __init__(self, modo: str, cliente_openai, reproductor: ReproductorAudifono) -> None:
        self.cliente = cliente_openai
        self.reproductor = reproductor
        self.clave_eleven = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        self.voz_eleven = os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or VOZ_ELEVENLABS
        if modo == "elevenlabs" and not self.clave_eleven:
            raise RuntimeError("Falta ELEVENLABS_API_KEY para --voz elevenlabs")
        self.modo = (
            "elevenlabs" if modo in ("auto", "elevenlabs") and self.clave_eleven else "openai"
        )
        log.info("Voz de Sergio: %s", self.modo)

    def _elevenlabs(self, texto: str) -> Iterator[bytes]:
        import httpx

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voz_eleven}/stream"
        cuerpo = {
            "text": texto[:2500],
            "model_id": MODELO_ELEVENLABS,
            "language_code": "es",
            "voice_settings": {
                "stability": 0.42,
                "similarity_boost": 0.85,
                "style": 0.15,
                "use_speaker_boost": True,
                "speed": 0.97,
            },
        }
        with httpx.Client(timeout=httpx.Timeout(30, connect=5)) as http:
            with http.stream(
                "POST",
                url,
                params={"output_format": f"pcm_{TASA_VOZ}", "optimize_streaming_latency": "3"},
                json=cuerpo,
                headers={"xi-api-key": self.clave_eleven},
            ) as resp:
                if resp.status_code != 200:
                    detalle = resp.read().decode("utf-8", "replace")[:200]
                    raise RuntimeError(f"ElevenLabs {resp.status_code}: {detalle}")
                yield from resp.iter_bytes(4096)

    def _openai(self, texto: str) -> Iterator[bytes]:
        with self.cliente.audio.speech.with_streaming_response.create(
            model=MODELO_TTS_OPENAI,
            voice=VOZ_TTS_OPENAI,
            input=texto[:4000],
            instructions=(
                "Voz masculina grave y cálida, en español, tranquila y sin prisa; "
                "elegancia de mayordomo británico con media sonrisa. Volumen íntimo, "
                "como hablando al oído."
            ),
            response_format="pcm",
        ) as resp:
            yield from resp.iter_bytes(4096)

    def decir(self, texto: str) -> bool:
        texto = (texto or "").strip()
        if not texto:
            return True
        if self.modo == "elevenlabs":
            primero, fuente = self._primer_trozo(self._elevenlabs(texto))
            if fuente is not None:
                return self.reproductor.reproducir(self._encadenar(primero, fuente))
            log.warning("ElevenLabs falló; uso el TTS de OpenAI")
        return self.reproductor.reproducir(self._openai(texto))

    @staticmethod
    def _primer_trozo(fuente: Iterator[bytes]) -> tuple[bytes, Iterator[bytes] | None]:
        """Pide el primer trozo antes de abrir el audio: si la API falla, se
        cambia de proveedor sin haber reproducido nada a medias."""
        try:
            return next(fuente), fuente
        except StopIteration:
            return b"", None
        except Exception as error:  # noqa: BLE001
            log.warning("Voz: %s", error)
            return b"", None

    @staticmethod
    def _encadenar(primero: bytes, resto: Iterator[bytes]) -> Iterator[bytes]:
        try:
            yield primero
            yield from resto
        finally:
            resto.close()

    def pitido(self, frecuencia: float = 880.0, veces: int = 1) -> None:
        silencio = bytes(int(TASA_VOZ * 0.06) * 2)
        audio = (tono(frecuencia) + silencio) * veces
        self.reproductor.reproducir([audio])

    def callar(self) -> None:
        self.reproductor.callar()


# =============================================================================
# 12) HUD: blanco puro sobre negro absoluto (el negro es transparente en la
#     waveguide). Tkinter vive en el hilo principal; los demás hilos le hablan
#     por una cola.
# =============================================================================


class HUDNulo:
    """Sustituto sin pantalla (--sin-hud): mismas llamadas, no hace nada."""

    def mostrar(
        self, lineas: list[str], icono: str = "ninguno", segundos: float | None = None
    ) -> None:
        if lineas:
            log.info("HUD: %s", " | ".join(lineas))

    def estado(self, estado: str) -> None:
        pass

    def limpiar(self) -> None:
        pass

    def ejecutar(self, parar: threading.Event) -> None:
        while not parar.wait(0.25):
            pass


class HUDWaveguide:
    BLANCO = "#FFFFFF"
    NEGRO = "#000000"

    def __init__(self, monitor: int | None) -> None:
        self.cola: queue.Queue[tuple] = queue.Queue()
        self.monitor = monitor

    # --- API para los otros hilos ---------------------------------------
    def mostrar(
        self, lineas: list[str], icono: str = "ninguno", segundos: float | None = None
    ) -> None:
        self.cola.put(("mostrar", list(lineas), icono, segundos))

    def estado(self, estado: str) -> None:
        """ "escuchando", "pensando", "privado" o "" (nada)."""
        self.cola.put(("estado", estado))

    def limpiar(self) -> None:
        self.cola.put(("limpiar",))

    # --- Geometría de la pantalla secundaria -----------------------------
    def _geometria(self, raiz) -> tuple[int, int, int, int, bool]:
        try:
            from screeninfo import get_monitors

            monitores = get_monitors()
        except Exception:  # noqa: BLE001 — screeninfo no instalado o sin X
            monitores = []
        if self.monitor is not None and 0 <= self.monitor < len(monitores):
            m = monitores[self.monitor]
            return m.x, m.y, m.width, m.height, True
        # Con una sola pantalla, esa es la de la laptop: nunca se tapa entera.
        secundarios = [m for m in monitores if not getattr(m, "is_primary", False)]
        if len(monitores) > 1 and secundarios:
            m = secundarios[-1]
            return m.x, m.y, m.width, m.height, True
        # Sin microdisplay conectado: ventana de simulación en la laptop.
        log.warning("No hay pantalla secundaria: HUD en ventana de simulación 640×400")
        return 60, 60, 640, 400, False

    # --- Bucle de Tk (hilo principal) ------------------------------------
    def ejecutar(self, parar: threading.Event) -> None:
        import tkinter as tk

        self.tk = tk
        raiz = tk.Tk()
        x, y, ancho, alto, pantalla_completa = self._geometria(raiz)
        raiz.title("HUD Sergio")
        raiz.configure(bg=self.NEGRO, cursor="none")
        if pantalla_completa:
            raiz.overrideredirect(True)  # sin bordes ni barra de título
            raiz.attributes("-topmost", True)
        raiz.geometry(f"{ancho}x{alto}+{x}+{y}")
        self.raiz, self.ancho, self.alto = raiz, ancho, alto
        self.lienzo = tk.Canvas(
            raiz, width=ancho, height=alto, bg=self.NEGRO, highlightthickness=0, bd=0
        )
        self.lienzo.pack(fill="both", expand=True)
        # Tamaños en PÍXELES (negativos en Tk): en puntos dependerían de los
        # DPI que declare el microdisplay y el texto se saldría de la pantalla.
        self.tam_fuente = max(14, int(alto / 9))
        self.familia = self._familia_fuente()
        self.estado_actual = ""
        self.ocultar_en = 0.0
        self.fase = 0
        raiz.bind("<Escape>", lambda _e: parar.set())

        def tic() -> None:
            if parar.is_set():
                raiz.destroy()
                return
            self._atender_cola()
            if self.ocultar_en and time.monotonic() >= self.ocultar_en:
                self.ocultar_en = 0.0
                self.lienzo.delete("mensaje")
            self.fase = (self.fase + 1) % 30
            self._dibujar_estado()
            raiz.after(33, tic)  # ~30 fps; también deja a Python atender Ctrl+C

        raiz.after(33, tic)
        raiz.mainloop()

    def _atender_cola(self) -> None:
        while True:
            try:
                orden = self.cola.get_nowait()
            except queue.Empty:
                return
            if orden[0] == "mostrar":
                _, lineas, icono, segundos = orden
                self._dibujar_mensaje(lineas, icono)
                palabras = sum(len(linea.split()) for linea in lineas)
                duracion = segundos if segundos is not None else max(5.0, 1.2 * palabras)
                self.ocultar_en = (
                    time.monotonic() + duracion if lineas or icono != "ninguno" else 0.0
                )
            elif orden[0] == "estado":
                self.estado_actual = orden[1]
            elif orden[0] == "limpiar":
                self.lienzo.delete("mensaje")
                self.estado_actual = ""
                self.ocultar_en = 0.0

    def _familia_fuente(self) -> str:
        """Sans-serif nítida y con "€", "ñ" y tildes en cada sistema."""
        from tkinter import font as tkfont

        disponibles = set(tkfont.families(self.raiz))
        for familia in (
            "Segoe UI Semibold",
            "Segoe UI",
            "Helvetica Neue",
            "SF Pro Text",
            "Inter",
            "DejaVu Sans",
            "Liberation Sans",
            "Arial",
            "Helvetica",
        ):
            if familia in disponibles:
                return familia
        return "TkDefaultFont"

    def _dibujar_mensaje(self, lineas: list[str], icono: str) -> None:
        from tkinter import font as tkfont

        c = self.lienzo
        c.delete("mensaje")
        if not lineas and icono == "ninguno":
            return
        margen = int(min(self.ancho, self.alto) * 0.08)
        # Encoger la letra hasta que la línea más larga quepa con el icono.
        px = self.tam_fuente
        while True:
            fuente = tkfont.Font(root=self.raiz, family=self.familia, size=-px, weight="bold")
            lado_icono = int(px * 1.6) if icono != "ninguno" else 0
            hueco = int(px * 0.6) if icono != "ninguno" else 0
            disponible = self.ancho - 2 * margen - lado_icono - hueco
            mas_ancha = max((fuente.measure(linea) for linea in lineas), default=0)
            if mas_ancha <= disponible or px <= 12:
                break
            px = max(12, int(px * disponible / max(1, mas_ancha)) - 1)
        alto_linea = int(px * 1.3)
        alto_bloque = max(lado_icono, alto_linea * max(1, len(lineas)))
        y0 = (self.alto - alto_bloque) // 2
        x_texto = margen
        if icono != "ninguno":
            self._dibujar_icono(icono, margen, y0 + (alto_bloque - lado_icono) // 2, lado_icono)
            x_texto = margen + lado_icono + hueco
        self.fuente_actual = fuente  # Tk necesita que el objeto Font siga vivo
        for i, linea in enumerate(lineas):
            c.create_text(
                x_texto,
                y0 + i * alto_linea + alto_linea // 2,
                text=linea,
                fill=self.BLANCO,
                font=fuente,
                anchor="w",
                tags="mensaje",
            )

    def _dibujar_icono(self, icono: str, x: int, y: int, lado: int) -> None:
        """Iconos vectoriales en blanco (nítidos a cualquier resolución)."""
        c, b = self.lienzo, self.BLANCO
        g = max(2, lado // 12)  # grosor del trazo
        cx, cy, r = x + lado / 2, y + lado / 2, lado / 2 - g
        t = "mensaje"
        if icono == "alerta":
            c.create_polygon(
                cx,
                y + g,
                x + lado - g,
                y + lado - g,
                x + g,
                y + lado - g,
                outline=b,
                fill="",
                width=g,
                tags=t,
            )
            c.create_line(cx, y + lado * 0.38, cx, y + lado * 0.66, fill=b, width=g, tags=t)
            c.create_oval(
                cx - g, y + lado * 0.76 - g, cx + g, y + lado * 0.76 + g, fill=b, outline=b, tags=t
            )
        elif icono == "ok":
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=b, width=g, tags=t)
            c.create_line(
                x + lado * 0.28,
                cy,
                x + lado * 0.45,
                y + lado * 0.68,
                x + lado * 0.74,
                y + lado * 0.34,
                fill=b,
                width=g,
                tags=t,
            )
        elif icono == "info":
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=b, width=g, tags=t)
            c.create_line(cx, cy - r * 0.1, cx, cy + r * 0.55, fill=b, width=g, tags=t)
            c.create_oval(
                cx - g, cy - r * 0.5 - g, cx + g, cy - r * 0.5 + g, fill=b, outline=b, tags=t
            )
        elif icono == "navegacion":
            c.create_line(
                x + g,
                cy,
                x + lado - 2 * g,
                cy,
                fill=b,
                width=g,
                arrow="last",
                arrowshape=(lado * 0.4, lado * 0.45, lado * 0.2),
                tags=t,
            )
        elif icono == "persona":
            c.create_oval(
                cx - r * 0.38, y + g, cx + r * 0.38, y + g + r * 0.76, outline=b, width=g, tags=t
            )
            c.create_arc(
                x + g,
                y + lado * 0.5,
                x + lado - g,
                y + lado * 1.4,
                start=0,
                extent=180,
                style="arc",
                outline=b,
                width=g,
                tags=t,
            )

    def _dibujar_estado(self) -> None:
        """Indicador mínimo en la esquina: anillo (escucho), puntos (pienso)."""
        c = self.lienzo
        c.delete("estado")
        r = max(5, self.tam_fuente // 4)
        x, y = self.ancho - 4 * r, 4 * r
        if self.estado_actual == "escuchando":
            pulso = r + (self.fase % 15) / 15 * r * 0.6
            c.create_oval(
                x - pulso,
                y - pulso,
                x + pulso,
                y + pulso,
                outline=self.BLANCO,
                width=2,
                tags="estado",
            )
        elif self.estado_actual == "pensando":
            for i in range(3):
                if (self.fase // 10) % 3 >= i:
                    xi = x - (2 - i) * 3 * r // 2
                    c.create_oval(
                        xi - r // 2,
                        y - r // 2,
                        xi + r // 2,
                        y + r // 2,
                        fill=self.BLANCO,
                        outline="",
                        tags="estado",
                    )
        elif self.estado_actual == "privado":
            c.create_line(x - r, y - r, x + r, y + r, fill=self.BLANCO, width=2, tags="estado")
            c.create_oval(x - r, y - r, x + r, y + r, outline=self.BLANCO, width=2, tags="estado")


# =============================================================================
# 13) MANILLA: teclas F13–F18 que envía el Bloque 3 por BLE HID
# =============================================================================


class AtajosManilla:
    def __init__(self, acciones: dict[str, Callable[[], None]], espacio_escucha: bool) -> None:
        self.acciones = acciones
        self.mapa = dict(TECLAS_MANILLA)
        if espacio_escucha:
            self.mapa["space"] = "escuchar"
        self.ultima: dict[str, float] = {}
        self.oyente = None

    def iniciar(self) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            log.warning("pynput no está instalado: la manilla no tendrá efecto")
            return

        def al_pulsar(tecla) -> None:
            nombre = getattr(tecla, "name", None) or getattr(tecla, "char", None)
            if nombre is None and getattr(tecla, "vk", None) is not None:
                # Windows entrega F13–F24 como códigos virtuales 0x7C–0x87.
                vk = tecla.vk
                nombre = f"f{vk - 0x7C + 13}" if 0x7C <= vk <= 0x87 else None
            accion = self.mapa.get(str(nombre).lower()) if nombre else None
            if accion is None:
                return
            ahora = time.monotonic()
            if ahora - self.ultima.get(accion, 0.0) < 0.25:  # autorepetición
                return
            self.ultima[accion] = ahora
            funcion = self.acciones.get(accion)
            if funcion is not None:
                log.info("Manilla: %s", accion)
                threading.Thread(target=funcion, name=f"manilla-{accion}", daemon=True).start()

        self.oyente = keyboard.Listener(on_press=al_pulsar)
        self.oyente.daemon = True
        self.oyente.start()

    def detener(self) -> None:
        if self.oyente is not None:
            self.oyente.stop()


# =============================================================================
# 14) ORQUESTADOR: Sergio en las gafas
# =============================================================================


class SergioGafas:
    def __init__(self, cfg: Config) -> None:
        from openai import OpenAI

        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit(
                "Falta OPENAI_API_KEY (variable de entorno o ~/.openjarvis/sergio.env)"
            )
        base_url = os.environ.get("SERGIO_OPENAI_BASE_URL") or None
        self.cfg = cfg
        self.cliente = OpenAI(base_url=base_url, max_retries=2, timeout=45.0)
        self.parar = threading.Event()
        self.camara = CamaraGafas(cfg.camara, cfg.resolucion, cfg.rotacion)
        self.microfono = Microfono(cfg.microfono)
        self.segmentador = SegmentadorVoz()
        self.transcriptor = Transcriptor(cfg.transcripcion, cfg.modelo_whisper, self.cliente)
        self.cerebro = CerebroIA(self.cliente, cfg.modelo_vision, cfg.detalle_imagen, cfg.owner)
        self.voz = Voz(cfg.voz, self.cliente, ReproductorAudifono(cfg.audifono))
        self.hud = HUDNulo() if cfg.sin_hud else HUDWaveguide(cfg.monitor)
        self.tareas: queue.Queue[tuple] = queue.Queue()
        self.reiniciar_oido = threading.Event()
        self.esperando_hasta = 0.0
        self.foto_congelada: Fotograma | None = None
        self.privado = False
        self.ultima_respuesta: Respuesta | None = None
        self.manilla = AtajosManilla(
            {
                "escuchar": self.accion_escuchar,
                "describir": self.accion_describir,
                "siguiente": self.accion_siguiente,
                "repetir": self.accion_repetir,
                "silencio": self.accion_silencio,
                "privado": self.accion_privado,
            },
            cfg.espacio_escucha,
        )

    # --- Arranque y parada ------------------------------------------------
    def ejecutar(self) -> None:
        self.transcriptor.preparar()
        self.camara.start()
        self.microfono.iniciar()
        self.manilla.iniciar()
        threading.Thread(target=self._bucle_audio, name="oido", daemon=True).start()
        threading.Thread(target=self._bucle_tareas, name="cerebro", daemon=True).start()
        nombres = " / ".join(p.capitalize() for p in self.cfg.palabras_clave)
        log.info("Sergio listo en las gafas. Di «%s, …» o toca la manilla.", nombres)
        signal.signal(signal.SIGINT, lambda *_: self.parar.set())
        try:
            self.hud.ejecutar(self.parar)  # bloquea el hilo principal (Tk)
        finally:
            self.parar.set()
            self.voz.callar()
            self.camara.parar.set()
            self.microfono.cerrar()
            self.manilla.detener()
            log.info("Sergio se despide.")

    # --- Hilo del oído: micrófono -> detector de voz -> cola de tareas -----
    def _bucle_audio(self) -> None:
        while not self.parar.is_set():
            try:
                bloque, t = self.microfono.cola.get(timeout=0.2)
            except queue.Empty:
                continue
            # Medio dúplex: mientras Sergio habla (y 0.3 s después) no se
            # escucha, para que su propia voz no se convierta en una orden.
            ocupado = self.voz.reproductor.hablando.is_set() or (
                time.monotonic() - self.voz.reproductor.fin_ultima < 0.3
            )
            if self.reiniciar_oido.is_set():
                self.reiniciar_oido.clear()
                self.segmentador.reiniciar()
            if self.privado or ocupado:
                self.segmentador.reiniciar()
                continue
            for frase in self.segmentador.alimentar(bloque, t):
                self.tareas.put(("frase", frase))

    # --- Hilo del cerebro: todo se atiende en orden, una cosa cada vez ------
    def _bucle_tareas(self) -> None:
        while not self.parar.is_set():
            try:
                tarea = self.tareas.get(timeout=0.2)
            except queue.Empty:
                if self.esperando_hasta and time.monotonic() > self.esperando_hasta:
                    self.esperando_hasta = 0.0
                    self.foto_congelada = None
                    self.hud.estado("")
                continue
            try:
                if tarea[0] == "frase":
                    self._atender_frase(tarea[1])
                elif tarea[0] == "orden":
                    self._ejecutar_orden(tarea[1], tarea[2])
                elif tarea[0] == "escuchar":
                    self._armar_escucha(tarea[1])
                elif tarea[0] == "decir":
                    self.voz.decir(tarea[1])
            except Exception as error:  # noqa: BLE001 — Sergio nunca se cae
                log.exception("Error atendiendo %s: %s", tarea[0], error)
                self.hud.estado("")
                self.hud.mostrar(["Sin conexión"], "alerta", 4)
                try:
                    self.voz.pitido(330, 2)
                except Exception:  # noqa: BLE001
                    pass

    def _atender_frase(self, frase: Frase) -> None:
        ahora = time.monotonic()
        if self.esperando_hasta and ahora <= self.esperando_hasta:
            # Tras "Sergio" a secas o un toque: esta frase entera es la orden.
            texto = self.transcriptor.transcribir(frase.audio)
            if not texto:
                return
            hay, resto = detectar_palabra_clave(texto, self.cfg.palabras_clave)
            if hay and len(normalizar(resto)) >= 2:
                texto = resto  # "Sergio, ..." otra vez: sobra el nombre
            foto = self.foto_congelada
            self.esperando_hasta, self.foto_congelada = 0.0, None
            self._ejecutar_orden(texto, foto)
            return

        # Primero solo los 2.5 s iniciales: si no empieza por "Sergio", se
        # descarta sin gastar CPU (o dinero) en transcribir la frase entera.
        cabeza = frase.audio[: int(2.5 * TASA_MICRO)]
        texto = self.transcriptor.transcribir(cabeza)
        hay, resto = detectar_palabra_clave(texto, self.cfg.palabras_clave)
        if not hay:
            if texto:
                log.debug("Ignorado (no me llamaban): %s", texto)
            return
        if frase.audio.size > cabeza.size:
            texto = self.transcriptor.transcribir(frase.audio)
            hay_completa, resto_completo = detectar_palabra_clave(texto, self.cfg.palabras_clave)
            if hay_completa:
                resto = resto_completo
        # Congelar la imagen del instante en que dijo "Sergio".
        foto = self.camara.fotograma_en(frase.t_inicio + 0.3)
        log.info("Palabra clave detectada: «%s»", texto)
        if len(normalizar(resto)) >= 2:
            self._ejecutar_orden(resto, foto)
        else:
            self._armar_escucha(foto)

    def _armar_escucha(self, foto: Fotograma | None) -> None:
        self.foto_congelada = foto
        self.esperando_hasta = time.monotonic() + ESPERA_COMANDO
        self.reiniciar_oido.set()  # lo aplica el hilo del oído (sin carreras)
        self.hud.estado("escuchando")
        self.voz.pitido(880, 1)

    def _ejecutar_orden(self, orden: str, foto: Fotograma | None) -> None:
        orden = orden.strip()
        clave = normalizar(orden)
        log.info("Orden: «%s»%s", orden, " + foto" if foto else "")
        # Órdenes locales: instantáneas, sin pasar por la nube.
        if clave in {"silencio", "callate", "para", "basta", "calla"}:
            self.accion_silencio()
            return
        if clave in {"repite", "repitelo", "otra vez", "que dijiste"}:
            self.accion_repetir_directo()
            return
        self.hud.estado("pensando")
        respuesta = self.cerebro.responder(orden, foto.jpeg if foto else None)
        self.ultima_respuesta = respuesta
        self.hud.estado("")
        self.hud.mostrar(respuesta.hud, respuesta.icono)
        log.info("Sergio: %s", respuesta.voz)
        self.voz.decir(respuesta.voz)

    # --- Acciones de la manilla (hilo de pynput -> cola o efecto inmediato) -
    def accion_escuchar(self) -> None:
        if self.privado:
            return
        self.voz.callar()
        # La foto se congela YA (el instante del toque); el pitido y la espera
        # los arma el hilo del cerebro, el único que usa el audífono.
        foto = self.camara.fotograma_en(time.monotonic(), antes=0.6, despues=0.0)
        self.tareas.put(("escuchar", foto))

    def accion_describir(self) -> None:
        if self.privado:
            return
        self.voz.callar()
        foto = self.camara.fotograma_en(time.monotonic(), antes=0.6, despues=0.0)
        self.tareas.put(("orden", "¿Qué tengo delante? Dime lo más útil en una frase.", foto))

    def accion_siguiente(self) -> None:
        self.voz.callar()
        self.tareas.put(("orden", "Continúa: el siguiente paso o el siguiente dato.", None))

    def accion_repetir(self) -> None:
        self.voz.callar()
        self.accion_repetir_directo()

    def accion_repetir_directo(self) -> None:
        if self.ultima_respuesta is None:
            return
        self.hud.mostrar(self.ultima_respuesta.hud, self.ultima_respuesta.icono)
        self.tareas.put(("decir", self.ultima_respuesta.voz))

    def accion_silencio(self) -> None:
        self.voz.callar()
        self.esperando_hasta, self.foto_congelada = 0.0, None
        self.hud.limpiar()

    def accion_privado(self) -> None:
        self.privado = not self.privado
        self.voz.callar()
        if self.privado:
            self.camara.pausada.set()
            self.camara.vaciar()  # nada de lo visto queda en memoria
            self.hud.limpiar()
            self.hud.estado("privado")
            self.tareas.put(("decir", "Modo privado. No veo ni escucho, señor."))
        else:
            self.camara.pausada.clear()
            self.hud.estado("")
            self.tareas.put(("decir", "De vuelta, señor."))


# =============================================================================
# 15) DIAGNÓSTICO: listar cámaras, audio y pantallas
# =============================================================================


def listar_dispositivos() -> None:
    print("\n== Audio (índice: nombre [entradas/salidas]) ==")
    try:
        import sounddevice as sd

        for i, info in enumerate(sd.query_devices()):
            print(
                f"  {i:3d}: {info['name']}  "
                f"[{info['max_input_channels']} in / {info['max_output_channels']} out]"
            )
    except Exception as error:  # noqa: BLE001
        print(f"  (sounddevice no disponible: {error})")
    print("\n== Cámaras (índices 0–5) ==")
    try:
        import cv2

        for i in range(6):
            cap = (
                cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if sys.platform.startswith("win")
                else cv2.VideoCapture(i)
            )
            if cap.isOpened():
                ok, img = cap.read()
                tam = f"{img.shape[1]}×{img.shape[0]}" if ok and img is not None else "sin imagen"
                print(f"  {i}: disponible ({tam})")
            cap.release()
    except Exception as error:  # noqa: BLE001
        print(f"  (OpenCV no disponible: {error})")
    print("\n== Pantallas ==")
    try:
        from screeninfo import get_monitors

        for i, m in enumerate(get_monitors()):
            principal = " (principal)" if getattr(m, "is_primary", False) else ""
            print(f"  {i}: {m.width}×{m.height} en ({m.x},{m.y}){principal} {m.name or ''}")
    except Exception as error:  # noqa: BLE001
        print(f"  (screeninfo no disponible: {error})")
    print()


# =============================================================================
# 16) LÍNEA DE COMANDOS
# =============================================================================


def leer_argumentos(argv: list[str] | None = None) -> tuple[Config, argparse.Namespace]:
    p = argparse.ArgumentParser(description="Sergio en las gafas: visión, voz y HUD.")
    p.add_argument("--listar", action="store_true", help="lista cámaras, audio y pantallas y sale")
    p.add_argument("--camara", default="1", help="índice de la cámara de las gafas o URL rtsp/http")
    p.add_argument("--resolucion", default="1280x720", help="ancho×alto de captura")
    p.add_argument(
        "--rotar", type=int, default=0, choices=(0, 90, 180, 270), help="rotación de la cámara"
    )
    p.add_argument("--microfono", default=None, help="nombre (o índice) del micrófono de las gafas")
    p.add_argument("--audifono", default=None, help="nombre (o índice) del audífono invisible")
    p.add_argument(
        "--monitor", type=int, default=None, help="índice del microdisplay (ver --listar)"
    )
    p.add_argument("--sin-hud", action="store_true", help="no abrir el HUD")
    p.add_argument("--transcripcion", default="auto", choices=("auto", "local", "api"))
    p.add_argument("--whisper", default="base", help="modelo local: tiny, base, small, medium…")
    p.add_argument("--voz", default="auto", choices=("auto", "elevenlabs", "openai"))
    p.add_argument("--modelo", default=os.environ.get("SERGIO_MODELO_VISION", MODELO_VISION))
    p.add_argument(
        "--detalle", default="auto", choices=("low", "high", "auto"), help="detalle de imagen"
    )
    p.add_argument(
        "--palabras",
        default=os.environ.get("SERGIO_PALABRAS_CLAVE", ",".join(PALABRAS_CLAVE)),
        help="palabras clave separadas por comas (p. ej. sergio,jarvis)",
    )
    p.add_argument(
        "--espacio", action="store_true", help="la barra espaciadora también activa la escucha"
    )
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    try:
        ancho, alto = (int(v) for v in a.resolucion.lower().replace("×", "x").split("x"))
    except ValueError:
        p.error("--resolucion debe ser ANCHOxALTO, p. ej. 1280x720")
    camara: int | str = int(a.camara) if str(a.camara).isdigit() else a.camara
    palabras = tuple(w.strip() for w in a.palabras.split(",") if w.strip()) or PALABRAS_CLAVE
    cfg = Config(
        camara=camara,
        resolucion=(ancho, alto),
        rotacion=a.rotar,
        microfono=a.microfono,
        audifono=a.audifono,
        monitor=a.monitor,
        sin_hud=a.sin_hud,
        transcripcion=a.transcripcion,
        modelo_whisper=a.whisper,
        voz=a.voz,
        modelo_vision=a.modelo,
        detalle_imagen=a.detalle,
        palabras_clave=palabras,
        espacio_escucha=a.espacio,
        owner=os.environ.get("SERGIO_OWNER_NAME", "").strip() or "su dueño",
    )
    return cfg, a


def main(argv: list[str] | None = None) -> None:
    cargar_archivo_env(Path(__file__).with_name(".env"))
    cargar_archivo_env(Path.home() / ".openjarvis" / "sergio.env")
    cfg, args = leer_argumentos(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.listar:
        listar_dispositivos()
        return
    SergioGafas(cfg).ejecutar()


if __name__ == "__main__":
    main()
