"""faster-whisper falls back to the CPU when CUDA libraries are missing (WSL)."""

from types import SimpleNamespace

from openjarvis.speech import faster_whisper as fw


class FakeModel:
    created = []

    def __init__(self, size, device, compute_type):
        FakeModel.created.append((device, compute_type))
        self.device = device

    def transcribe(self, path, **kw):
        if self.device != "cpu":
            raise RuntimeError(
                "Library libcublas.so.12 is not found or cannot be loaded"
            )
        seg = SimpleNamespace(text=" hola ", start=0.0, end=1.0)
        return iter([seg]), SimpleNamespace(
            language="es", language_probability=0.9, duration=1.0
        )


def test_cublas_missing_switches_to_cpu_and_retries(monkeypatch):
    FakeModel.created = []
    monkeypatch.setattr(fw, "WhisperModel", FakeModel)
    backend = fw.FasterWhisperBackend(device="cuda", compute_type="float16")
    monkeypatch.setattr(backend, "_resolve_compute_type", lambda: backend._compute_type)
    result = backend.transcribe(b"RIFF....", language="es")
    assert result.text == "hola"
    assert FakeModel.created == [("cuda", "float16"), ("cpu", "int8")]
    backend.transcribe(b"RIFF....")  # stays on CPU, no reload
    assert len(FakeModel.created) == 2


def test_other_errors_are_not_hidden(monkeypatch):
    class Broken(FakeModel):
        def transcribe(self, path, **kw):
            raise ValueError("bad audio")

    monkeypatch.setattr(fw, "WhisperModel", Broken)
    backend = fw.FasterWhisperBackend(device="cuda")
    monkeypatch.setattr(backend, "_resolve_compute_type", lambda: "float16")
    try:
        backend.transcribe(b"x")
    except ValueError as exc:
        assert "bad audio" in str(exc)
    else:
        raise AssertionError("expected ValueError")
