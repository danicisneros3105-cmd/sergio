"""kokoro-onnx backend: Sergio's local Spanish voice without PyTorch."""

from openjarvis.speech import _tts_discovery
from openjarvis.speech.kokoro_onnx_tts import KokoroOnnxTTSBackend


class _FakeKokoro:
    voices = {"em_alex": 1, "af_heart": 1}

    def create(self, text, voice, speed, lang):
        import numpy as np

        self.args = (voice, lang)
        return np.zeros(2400, dtype="float32"), 24000


def test_synthesize_spanish_wav_and_unknown_voice_falls_back():
    backend = KokoroOnnxTTSBackend()
    backend._kokoro = fake = _FakeKokoro()
    result = backend.synthesize("hola", voice_id="bm_george", output_format="mp3")
    assert fake.args == ("em_alex", "es")
    assert result.format == "wav" and result.audio[:4] == b"RIFF"
    assert abs(result.duration_seconds - 0.1) < 1e-6


def test_discovery_order_and_default_voice():
    assert "kokoro_onnx" in _tts_discovery.TTS_BACKEND_ORDER
    assert _tts_discovery.default_voice_for("kokoro_onnx") == "em_alex"
