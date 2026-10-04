"""Tests for the STT hallucination filter."""

from openjarvis.speech.hallucinations import is_hallucination


class TestHallucinations:
    def test_classic_whisper_phrases_spanish(self):
        assert is_hallucination("Gracias por ver el vídeo.")
        assert is_hallucination("¡Suscríbete!")
        assert is_hallucination("Subtítulos realizados por Juan Pérez")
        assert is_hallucination("[Música]")

    def test_classic_whisper_phrases_english(self):
        assert is_hallucination("Thank you for watching.")
        assert is_hallucination("Please subscribe!")
        assert is_hallucination("Subtitles by Amara.org")

    def test_empty_and_noise(self):
        assert is_hallucination("")
        assert is_hallucination(None)
        assert is_hallucination("...")
        assert is_hallucination("eh")
        assert is_hallucination("no no no no no no no")

    def test_real_speech_passes(self):
        assert not is_hallucination("Sergio, cambia el fondo de pantalla")
        assert not is_hallucination("¿Qué hora es?")
        assert not is_hallucination("gracias, eso era todo")  # real thanks
        assert not is_hallucination("ponme música de Queen")

    def test_accents_and_case_insensitive(self):
        assert is_hallucination("GRACIAS POR VER EL VIDEO")
        assert is_hallucination("grácias pór vér")
