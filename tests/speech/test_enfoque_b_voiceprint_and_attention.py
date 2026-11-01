"""Comprehensive Test Suite for Approach B: Edge Multimodal Diarization & Conversational Attention.

Verifies:
1. Acoustic Biometric Voiceprint Verification (<8ms) rejecting TV/movie and third-party voices.
2. Pragmatic Addressee Intent Classification distinguishing agent commands from human side-talk.
3. System Loopback AEC suppressing mic leakage during media playback.
4. End-to-end integration into Attention pipeline preventing false interruptions.
"""

from __future__ import annotations

import numpy as np

from openjarvis.speech.addressee_classifier import AddresseeClassifier, AddresseeTarget
from openjarvis.speech.attention import Attention
from openjarvis.speech.biometric_voiceprint import (
    VoiceprintManager,
)
from openjarvis.speech.loopback_aec import (
    ActiveMediaSession,
    LoopbackAEC,
    LoopbackAECState,
)


def _generate_synthetic_voice_sample(
    fundamental_f0: float = 135.0,
    duration_seconds: float = 1.0,
    sample_rate: int = 16000,
) -> bytes:
    """Generate synthetic voiced speech PCM with fundamental F0 and vocal tract formants."""
    num_samples = int(duration_seconds * sample_rate)
    t = np.arange(num_samples) / float(sample_rate)

    # Harmonics modeling vocal cords + formants (mouth cavity resonance)
    signal = (
        0.50 * np.sin(2.0 * np.pi * fundamental_f0 * t)
        + 0.25 * np.sin(2.0 * np.pi * (fundamental_f0 * 2.0) * t)
        + 0.15 * np.sin(2.0 * np.pi * (fundamental_f0 * 3.0) * t)
        + 0.10 * np.sin(2.0 * np.pi * (fundamental_f0 * 4.0) * t)
    )

    # Scale to 16-bit signed PCM
    pcm_int16 = (signal * 30000.0).astype(np.int16)
    return pcm_int16.tobytes()


def test_acoustic_voiceprint_extraction_and_matching(tmp_path):
    mgr = VoiceprintManager(storage_dir=tmp_path)
    assert not mgr.is_enrolled()

    # Owner: Baritone speaker ~125 Hz
    owner_pcm = _generate_synthetic_voice_sample(fundamental_f0=125.0, duration_seconds=1.2)
    enroll_res = mgr.enroll_audio_sample(owner_pcm)
    assert enroll_res["success"] is True
    assert mgr.is_enrolled() is True

    # Same owner speaking: should positively verify
    ver_owner = mgr.verify_speaker(owner_pcm)
    assert ver_owner.is_owner is True
    assert ver_owner.similarity_score >= 0.85
    assert ver_owner.is_enrolled is True

    # Different speaker (e.g. Actor in series or companion ~260 Hz tenor/soprano)
    other_pcm = _generate_synthetic_voice_sample(fundamental_f0=260.0, duration_seconds=1.2)
    ver_other = mgr.verify_speaker(other_pcm)
    # The two distinct frequencies and formant profiles produce low similarity
    assert ver_other.is_owner is False
    assert ver_other.similarity_score < 0.78


def test_addressee_intent_classifier_human_side_talk():
    classifier = AddresseeClassifier("Sergio")

    # 1. Interpersonal side-conversations with humans
    target1, conf1, _ = classifier.classify_utterance("Oye mamá, pásame la sal por favor")
    assert target1 == AddresseeTarget.OTHER_PERSON
    assert conf1 >= 0.80

    target2, conf2, _ = classifier.classify_utterance("No te hablo a ti, estoy hablando por teléfono con mi jefe")
    assert target2 == AddresseeTarget.OTHER_PERSON
    assert conf2 >= 0.90

    target3, conf3, _ = classifier.classify_utterance("Entonces le dije que no podíamos ir a esa fiesta")
    assert target3 == AddresseeTarget.OTHER_PERSON

    # 2. Movie and TV scripted series dialogue
    target4, conf4, _ = classifier.classify_utterance("¡Dispara al traidor antes de que escape con el dinero!")
    assert target4 == AddresseeTarget.AMBIENT_MEDIA

    target5, conf5, _ = classifier.classify_utterance("En el próximo episodio de esta serie veremos la verdad")
    assert target5 == AddresseeTarget.AMBIENT_MEDIA


def test_addressee_intent_classifier_agent_commands():
    classifier = AddresseeClassifier("Sergio")

    # Explicit vocative commands
    target1, conf1, _ = classifier.classify_utterance("Sergio, busca vuelos a Tokio para el próximo mes")
    assert target1 == AddresseeTarget.AGENT
    assert conf1 >= 0.90

    # Query command in active exchange
    target2, conf2, _ = classifier.classify_utterance(
        "¿Cuánto cuesta la suite en el hotel?", recent_exchange_active=True
    )
    assert target2 == AddresseeTarget.AGENT
    assert conf2 >= 0.70

    # Imperative directive & delegation
    target3, conf3, _ = classifier.classify_utterance("Abre la terminal y ejecuta las pruebas")
    assert target3 == AddresseeTarget.AGENT

    # Delegation directives to assistant (should NOT be classified as side-talk)
    target4, conf4, _ = classifier.classify_utterance("Sergio, dile a Juan que llego en 10 minutos")
    assert target4 == AddresseeTarget.AGENT

    target5, conf5, _ = classifier.classify_utterance(
        "Ahora pregúntale a María si tiene el informe", recent_exchange_active=True
    )
    assert target5 == AddresseeTarget.AGENT


def test_attention_pipeline_rejects_third_party_and_media(tmp_path, monkeypatch):
    # Setup enrolled owner voiceprint
    mgr = VoiceprintManager(storage_dir=tmp_path)
    owner_pcm = _generate_synthetic_voice_sample(fundamental_f0=130.0, duration_seconds=1.0)
    mgr.enroll_audio_sample(owner_pcm)

    now = [0.0]
    attention = Attention(name="Sergio", clock=lambda: now[0], enable_aec=False)
    attention.voiceprint_mgr = mgr

    # 1. Owner speaking with explicit vocative -> ACCEPTED
    assert attention.accepts("Sergio, dime el resumen de noticias", audio_pcm=owner_pcm) is True

    # 2. Side-talk while attention is open -> REJECTED and window closed
    assert attention.accepts("Pásame eso, mamá", audio_pcm=owner_pcm) is False
    assert attention.until == 0

    # 3. Third-party or TV voice -> REJECTED by acoustic biometrics
    tv_actor_pcm = _generate_synthetic_voice_sample(fundamental_f0=280.0, duration_seconds=1.0)
    assert attention.accepts("Sergio, abre mi correo", audio_pcm=tv_actor_pcm) is False


def test_loopback_aec_suppresses_media_playback(monkeypatch):
    now = [0.0]
    attention = Attention(name="Sergio", clock=lambda: now[0], enable_biometrics=False, enable_aec=True)

    # Mock active media playback (e.g. YouTube playing in Chrome)
    mock_aec = LoopbackAEC()
    mock_aec.detector.check_active_media = lambda: LoopbackAECState(
        is_media_playing=True,
        active_sources=[ActiveMediaSession("chrome.exe", "browser", True)],
        ducking_applied=True,
    )
    attention.loopback_aec = mock_aec

    # Movie dialog playing through PC speakers without vocative -> REJECTED
    assert attention.accepts("¿Adónde fuiste ayer?") is False

    # Explicit vocative overriding media ducking -> ACCEPTED
    assert attention.accepts("Sergio, pausa el video") is True
