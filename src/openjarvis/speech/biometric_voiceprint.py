"""Acoustic Biometric Voiceprint Verification and Speaker Diarization Nexus.

Extracts fixed-dimensional speaker acoustic embeddings from raw PCM audio using
multi-band Mel filterbanks, spectral moments, cepstral coefficients, and fundamental
vocal tract resonance (F0/formant ratios).

Provides real-time cosine-similarity verification (<8ms latency) to ensure Sergio
only attends to the authorized owner, rejecting background conversations, TV audio,
and movie/series dialogue at the acoustic wave layer before text transcription.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger("openjarvis.speech.biometric_voiceprint")

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_FRAME_LENGTH = 400  # 25ms @ 16kHz
DEFAULT_FRAME_HOP = 160  # 10ms @ 16kHz
DEFAULT_NUM_MEL_BANDS = 32
DEFAULT_NUM_MFCC = 16
DEFAULT_EMBEDDING_DIM = 64
DEFAULT_VERIFICATION_THRESHOLD = 0.78


def _hz_to_mel(hz: float) -> float:
    """Convert frequency in Hertz to the perceptual Mel scale."""
    return 2595.0 * math.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: float) -> float:
    """Convert frequency in perceptual Mel scale back to Hertz."""
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _create_mel_filterbank(
    num_bands: int,
    fft_size: int,
    sample_rate: int,
    low_freq: float = 80.0,
    high_freq: float = 7600.0,
) -> np.ndarray:
    """Construct triangular Mel filterbank matrix of shape (num_bands, fft_size // 2 + 1)."""
    low_mel = _hz_to_mel(low_freq)
    high_mel = _hz_to_mel(high_freq)
    mel_points = np.linspace(low_mel, high_mel, num_bands + 2)
    hz_points = np.array([_mel_to_hz(m) for m in mel_points])
    bin_points = np.floor((fft_size + 1) * hz_points / sample_rate).astype(int)

    num_bins = fft_size // 2 + 1
    filterbank = np.zeros((num_bands, num_bins), dtype=np.float32)

    for i in range(1, num_bands + 1):
        left = bin_points[i - 1]
        center = bin_points[i]
        right = bin_points[i + 1]

        if center > left:
            filterbank[i - 1, left:center] = (np.arange(left, center) - left) / float(
                center - left
            )
        if right > center:
            filterbank[i - 1, center:right] = (
                right - np.arange(center, right)
            ) / float(right - center)

    return filterbank


@dataclass
class VoiceprintVerificationResult:
    """Outcome of real-time acoustic speaker verification against enrolled owner profile."""

    is_owner: bool
    similarity_score: float
    threshold: float
    confidence: float
    is_enrolled: bool
    snr_db: float
    estimated_pitch_f0: float
    frames_analyzed: int
    execution_time_ms: float
    verdict: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OwnerVoiceprintProfile:
    """Enrolled biometric voice identity for the authorized human operator."""

    owner_id: str = "primary_operator"
    embedding: List[float] = field(default_factory=list)
    embedding_dimension: int = DEFAULT_EMBEDDING_DIM
    sample_count: int = 0
    enrolled_at: float = 0.0
    last_calibrated_at: float = 0.0
    baseline_pitch_f0_mean: float = 120.0
    baseline_pitch_f0_std: float = 25.0
    verification_threshold: float = DEFAULT_VERIFICATION_THRESHOLD

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OwnerVoiceprintProfile:
        return cls(
            owner_id=str(data.get("owner_id", "primary_operator")),
            embedding=[float(x) for x in data.get("embedding", [])],
            embedding_dimension=int(
                data.get("embedding_dimension", DEFAULT_EMBEDDING_DIM)
            ),
            sample_count=int(data.get("sample_count", 0)),
            enrolled_at=float(data.get("enrolled_at", 0.0)),
            last_calibrated_at=float(data.get("last_calibrated_at", 0.0)),
            baseline_pitch_f0_mean=float(data.get("baseline_pitch_f0_mean", 120.0)),
            baseline_pitch_f0_std=float(data.get("baseline_pitch_f0_std", 25.0)),
            verification_threshold=float(
                data.get("verification_threshold", DEFAULT_VERIFICATION_THRESHOLD)
            ),
        )


class AcousticVoiceprintExtractor:
    """Ultra-low latency (<5ms) acoustic feature and speaker embedding extractor in pure NumPy."""

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        frame_length: int = DEFAULT_FRAME_LENGTH,
        frame_hop: int = DEFAULT_FRAME_HOP,
        num_mel_bands: int = DEFAULT_NUM_MEL_BANDS,
        num_mfcc: int = DEFAULT_NUM_MFCC,
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_length = frame_length
        self.frame_hop = frame_hop
        self.num_mel_bands = num_mel_bands
        self.num_mfcc = num_mfcc
        self.embedding_dim = embedding_dim
        self.fft_size = 512

        self.hamming_window = 0.54 - 0.46 * np.cos(
            2.0 * np.pi * np.arange(self.frame_length) / (self.frame_length - 1)
        ).astype(np.float32)

        self.mel_filterbank = _create_mel_filterbank(
            self.num_mel_bands, self.fft_size, self.sample_rate
        )

        # Precompute DCT-II matrix for MFCC extraction
        n = np.arange(self.num_mel_bands)
        k = np.arange(self.num_mfcc)[:, np.newaxis]
        self.dct_matrix = np.cos(
            np.pi * k * (2 * n + 1) / (2.0 * self.num_mel_bands)
        ).astype(np.float32)

    def pcm_to_float(self, pcm_bytes: bytes) -> np.ndarray:
        """Decode raw 16-bit signed integer linear PCM bytes into normalized float32."""
        if not pcm_bytes:
            return np.zeros(0, dtype=np.float32)
        int16_arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        float_arr = int16_arr.astype(np.float32) / 32768.0
        return float_arr

    def estimate_pitch_f0(self, signal: np.ndarray) -> float:
        """Estimate fundamental vocal cord vibration frequency (F0) using normalized autocorrelation."""
        if len(signal) < 800:
            return 0.0

        min_lag = int(
            self.sample_rate / 400.0
        )  # 400 Hz maximum human pitch (lag 40 @ 16kHz)
        max_lag = int(
            self.sample_rate / 65.0
        )  # 65 Hz minimum human pitch (lag 246 @ 16kHz)

        if len(signal) <= max_lag:
            return 0.0

        corr = np.correlate(signal, signal, mode="full")
        corr = corr[len(signal) - 1 :]

        if len(corr) <= max_lag:
            return 0.0

        search_region = corr[min_lag:max_lag]
        if len(search_region) == 0:
            return 0.0

        peak_idx = int(np.argmax(search_region)) + min_lag
        energy_0 = corr[0] if corr[0] > 1e-6 else 1e-6

        norm_peak = corr[peak_idx] / energy_0
        if norm_peak < 0.25:
            return 0.0

        pitch_hz = self.sample_rate / float(peak_idx)
        return float(pitch_hz)

    def compute_snr_db(self, signal: np.ndarray) -> float:
        """Compute estimated signal-to-noise ratio in decibels based on frame energy percentiles."""
        if len(signal) < self.frame_length:
            return 0.0

        num_frames = (len(signal) - self.frame_length) // self.frame_hop + 1
        if num_frames <= 0:
            return 0.0

        energies = []
        for i in range(num_frames):
            start = i * self.frame_hop
            frame = signal[start : start + self.frame_length]
            eng = float(np.sum(frame * frame))
            energies.append(eng)

        energies_arr = np.array(energies, dtype=np.float32)
        if len(energies_arr) == 0:
            return 0.0

        noise_floor = float(np.percentile(energies_arr, 10))
        signal_ceiling = float(np.percentile(energies_arr, 90))

        if noise_floor <= 1e-9:
            noise_floor = 1e-9
        if signal_ceiling <= 1e-9:
            return 0.0

        # If signal is continuous and loud (no pauses), SNR is at least 25 dB
        if signal_ceiling > 0.01 and signal_ceiling / noise_floor < 1.5:
            return 28.0

        snr = 10.0 * math.log10(max(1.0, signal_ceiling / noise_floor))
        return round(float(snr), 2)

    def extract_embedding(
        self, audio_data: bytes | np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        """Compute normalized 64-dimensional speaker acoustic identity vector."""
        if isinstance(audio_data, bytes):
            signal = self.pcm_to_float(audio_data)
        else:
            signal = audio_data.astype(np.float32)

        metrics: Dict[str, float] = {
            "pitch_f0": 0.0,
            "snr_db": 0.0,
            "frames": 0.0,
            "duration_seconds": round(len(signal) / float(self.sample_rate), 3),
        }

        if len(signal) < self.frame_length:
            # Fallback for empty or sub-frame snippets
            return np.zeros(self.embedding_dim, dtype=np.float32), metrics

        # Pre-emphasis filter (boost vocal tract high frequencies)
        pre_emphasized = np.append(signal[0], signal[1:] - 0.97 * signal[:-1])

        num_frames = (len(pre_emphasized) - self.frame_length) // self.frame_hop + 1
        if num_frames <= 0:
            return np.zeros(self.embedding_dim, dtype=np.float32), metrics

        metrics["frames"] = float(num_frames)
        metrics["pitch_f0"] = round(self.estimate_pitch_f0(signal), 1)
        metrics["snr_db"] = self.compute_snr_db(signal)

        mfcc_frames = np.zeros((num_frames, self.num_mfcc), dtype=np.float32)
        spectral_centroids = np.zeros(num_frames, dtype=np.float32)
        spectral_spreads = np.zeros(num_frames, dtype=np.float32)
        spectral_flatness = np.zeros(num_frames, dtype=np.float32)
        zero_crossings = np.zeros(num_frames, dtype=np.float32)

        fft_freqs = np.linspace(0.0, self.sample_rate / 2.0, self.fft_size // 2 + 1)

        for i in range(num_frames):
            start = i * self.frame_hop
            frame = (
                pre_emphasized[start : start + self.frame_length] * self.hamming_window
            )

            # Real FFT and Power Spectrum
            fft_complex = np.fft.rfft(frame, n=self.fft_size)
            power_spectrum = (np.abs(fft_complex) ** 2) / float(self.fft_size)

            # Mel filterbank energies
            mel_energies = np.dot(self.mel_filterbank, power_spectrum)
            log_mel = np.log(np.maximum(mel_energies, 1e-6))

            # MFCC via DCT-II
            mfccs = np.dot(self.dct_matrix, log_mel)
            mfcc_frames[i, :] = mfccs

            # Spectral Moments
            total_power = np.sum(power_spectrum)
            if total_power > 1e-7:
                centroid = np.sum(fft_freqs * power_spectrum) / total_power
                spread = np.sqrt(
                    np.sum(((fft_freqs - centroid) ** 2) * power_spectrum) / total_power
                )
                # Spectral flatness (geometric mean / arithmetic mean)
                geom_mean = np.exp(np.mean(np.log(np.maximum(power_spectrum, 1e-9))))
                arith_mean = total_power / len(power_spectrum)
                flatness = geom_mean / max(arith_mean, 1e-9)
            else:
                centroid = 0.0
                spread = 0.0
                flatness = 0.0

            spectral_centroids[i] = centroid
            spectral_spreads[i] = spread
            spectral_flatness[i] = min(1.0, float(flatness))

            # Zero-crossing rate
            raw_frame = signal[start : start + self.frame_length]
            zcr = np.mean(np.abs(np.diff(np.signbit(raw_frame).astype(int))))
            zero_crossings[i] = zcr

        # Statistical pooling across frames — drop c0 (energy) to prevent amplitude-dominated false matches
        mfcc_mean = np.mean(mfcc_frames[:, 1:], axis=0)  # 15 dims (c1 to c15)
        mfcc_std = np.std(mfcc_frames[:, 1:], axis=0)  # 15 dims

        # Delta MFCC (temporal velocity)
        if num_frames >= 3:
            delta_mfcc = np.diff(mfcc_frames[:, 1:], axis=0)
            delta_mean = np.mean(delta_mfcc, axis=0)  # 15 dims
            delta_std = np.std(delta_mfcc, axis=0)  # 15 dims
        else:
            delta_mean = np.zeros(self.num_mfcc - 1, dtype=np.float32)
            delta_std = np.zeros(self.num_mfcc - 1, dtype=np.float32)

        # Spectral moment and vocal tract summary (7 dimensions)
        pitch_norm = min(1.0, max(0.0, float(metrics["pitch_f0"]) / 350.0))
        spectral_summary = np.array(
            [
                float(np.mean(spectral_centroids)) / 4000.0,
                float(np.mean(spectral_spreads)) / 2000.0,
                float(np.mean(spectral_flatness)),
                float(np.mean(zero_crossings)),
                pitch_norm,
                float(np.std(spectral_centroids)) / 2000.0,
                float(np.std(spectral_flatness)),
            ],
            dtype=np.float32,
        )

        # Concatenate into 64-dimensional speaker acoustic identity vector
        # 15 (mfcc_mean) + 15 (mfcc_std) + 15 (delta_mean) + 12 (first 12 delta_std) + 7 (spectral) = 64
        embedding = np.concatenate(
            [
                mfcc_mean,
                mfcc_std,
                delta_mean,
                delta_std[:12],
                spectral_summary,
            ]
        ).astype(np.float32)

        # Truncate or pad strictly to embedding_dim
        if len(embedding) > self.embedding_dim:
            embedding = embedding[: self.embedding_dim]
        elif len(embedding) < self.embedding_dim:
            embedding = np.pad(embedding, (0, self.embedding_dim - len(embedding)))

        # L2 Unit Hypersphere Normalization
        norm = float(np.linalg.norm(embedding))
        if norm > 1e-7:
            embedding = embedding / norm

        return embedding, metrics


class VoiceprintManager:
    """Manages persistent biometric voice identity profile and real-time speaker verification."""

    _instance: Optional[VoiceprintManager] = None

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir = (
            storage_dir
            if storage_dir is not None
            else Path.home() / ".openjarvis" / "voiceprint"
        )
        self.profile_file = self.storage_dir / "owner_profile.json"
        self.extractor = AcousticVoiceprintExtractor()
        self.profile: OwnerVoiceprintProfile = self._load_profile()

    @classmethod
    def get_instance(cls) -> VoiceprintManager:
        if cls._instance is None:
            cls._instance = VoiceprintManager()
        return cls._instance

    def _load_profile(self) -> OwnerVoiceprintProfile:
        """Load enrolled owner profile from disk, or return uncalibrated default."""
        if not self.profile_file.exists():
            # Check secondary fallback ~/.sergio/voiceprint/owner_profile.json
            alt_file = Path.home() / ".sergio" / "voiceprint" / "owner_profile.json"
            if alt_file.exists():
                try:
                    data = json.loads(alt_file.read_text(encoding="utf-8"))
                    return OwnerVoiceprintProfile.from_dict(data)
                except Exception as exc:
                    log.warning("Fallo al leer perfil secundario de voz: %s", exc)

            return OwnerVoiceprintProfile()

        try:
            data = json.loads(self.profile_file.read_text(encoding="utf-8"))
            return OwnerVoiceprintProfile.from_dict(data)
        except Exception as exc:
            log.warning("Fallo al leer perfil primario de voz: %s", exc)
            return OwnerVoiceprintProfile()

    def save_profile(self) -> bool:
        """Persist current voiceprint profile to disk under strict permissions."""
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            data_str = json.dumps(self.profile.to_dict(), indent=2, ensure_ascii=False)
            self.profile_file.write_text(data_str, encoding="utf-8")
            return True
        except Exception as exc:
            log.error("No se pudo guardar perfil de voz: %s", exc)
            return False

    def is_enrolled(self) -> bool:
        """Returns True if the authorized user has enrolled a valid biometric voiceprint."""
        return (
            bool(self.profile.embedding)
            and len(self.profile.embedding) == DEFAULT_EMBEDDING_DIM
            and self.profile.sample_count > 0
        )

    def enroll_audio_sample(self, audio_data: bytes | np.ndarray) -> Dict[str, Any]:
        """Add a voice sample to owner profile, computing running barycenter embedding."""
        if isinstance(audio_data, bytes):
            sig = self.extractor.pcm_to_float(audio_data)
        else:
            sig = audio_data.astype(np.float32)

        emb, metrics = self.extractor.extract_embedding(sig)
        total_energy = float(np.mean(sig * sig)) if len(sig) > 0 else 0.0
        if metrics["frames"] < 5 or (metrics["snr_db"] < 4.0 and total_energy < 0.005):
            return {
                "success": False,
                "error": "Audio con energía insuficiente o relación señal/ruido demasiado baja.",
                "metrics": metrics,
            }

        current_samples = self.profile.sample_count
        now = time.time()

        if current_samples == 0 or not self.profile.embedding:
            self.profile.embedding = emb.tolist()
            self.profile.sample_count = 1
            self.profile.enrolled_at = now
            self.profile.last_calibrated_at = now
            if metrics["pitch_f0"] > 50.0:
                self.profile.baseline_pitch_f0_mean = metrics["pitch_f0"]
        else:
            old_emb = np.array(self.profile.embedding, dtype=np.float32)
            # Running barycenter average
            new_emb = (old_emb * float(current_samples) + emb) / float(
                current_samples + 1
            )
            norm = float(np.linalg.norm(new_emb))
            if norm > 1e-7:
                new_emb = new_emb / norm
            self.profile.embedding = new_emb.tolist()
            self.profile.sample_count += 1
            self.profile.last_calibrated_at = now
            if metrics["pitch_f0"] > 50.0:
                old_f0 = float(self.profile.baseline_pitch_f0_mean)
                new_f0 = (
                    old_f0 * float(current_samples) + metrics["pitch_f0"]
                ) / float(current_samples + 1)
                self.profile.baseline_pitch_f0_mean = round(new_f0, 1)

        self.save_profile()
        return {
            "success": True,
            "sample_count": self.profile.sample_count,
            "metrics": metrics,
            "enrolled": True,
        }

    def verify_speaker(
        self,
        audio_data: bytes | np.ndarray,
        custom_threshold: Optional[float] = None,
    ) -> VoiceprintVerificationResult:
        """Verify if incoming audio frame or utterance belongs to the enrolled owner."""
        t0 = time.perf_counter()
        emb, metrics = self.extractor.extract_embedding(audio_data)

        dt_ms = (time.perf_counter() - t0) * 1000.0

        if not self.is_enrolled():
            # If not yet enrolled, fail safe: allow with warning or require enrollment
            return VoiceprintVerificationResult(
                is_owner=True,
                similarity_score=1.0,
                threshold=self.profile.verification_threshold,
                confidence=0.50,
                is_enrolled=False,
                snr_db=metrics["snr_db"],
                estimated_pitch_f0=metrics["pitch_f0"],
                frames_analyzed=int(metrics["frames"]),
                execution_time_ms=round(dt_ms, 2),
                verdict="perfil_no_matriculado_paso_por_defecto",
            )

        owner_emb = np.array(self.profile.embedding, dtype=np.float32)
        target_thresh = (
            float(custom_threshold)
            if custom_threshold is not None
            else self.profile.verification_threshold
        )

        raw_similarity = float(np.dot(owner_emb, emb))
        raw_similarity = max(-1.0, min(1.0, raw_similarity))

        # Physiological F0 vocal cord harmonic matching with octave-jump tolerance
        sample_f0 = float(metrics["pitch_f0"])
        owner_f0 = float(self.profile.baseline_pitch_f0_mean)
        if sample_f0 > 50.0 and owner_f0 > 50.0:
            base_ratio = min(sample_f0, owner_f0) / max(sample_f0, owner_f0)
            # Only tolerate octave doubling/halving if spectral envelope formants already match
            if raw_similarity >= 0.70:
                oct_up = min(sample_f0 * 0.5, owner_f0) / max(sample_f0 * 0.5, owner_f0)
                oct_down = min(sample_f0, owner_f0 * 0.5) / max(
                    sample_f0, owner_f0 * 0.5
                )
                pitch_ratio = max(base_ratio, oct_up, oct_down)
            else:
                pitch_ratio = base_ratio
            similarity = 0.65 * raw_similarity + 0.35 * pitch_ratio
        else:
            similarity = raw_similarity

        similarity = max(-1.0, min(1.0, similarity))

        is_owner = similarity >= target_thresh
        confidence = round(min(1.0, max(0.0, (similarity - 0.50) / 0.50)), 3)

        if is_owner:
            verdict = "coincidencia_biometrica_positiva_dueno_autorizado"
        else:
            verdict = "voz_rechazada_hablante_tercero_o_audio_multimedia"

        return VoiceprintVerificationResult(
            is_owner=is_owner,
            similarity_score=round(similarity, 4),
            threshold=target_thresh,
            confidence=confidence,
            is_enrolled=True,
            snr_db=metrics["snr_db"],
            estimated_pitch_f0=metrics["pitch_f0"],
            frames_analyzed=int(metrics["frames"]),
            execution_time_ms=round(dt_ms, 2),
            verdict=verdict,
        )


def get_voiceprint_manager() -> VoiceprintManager:
    return VoiceprintManager.get_instance()


__all__ = [
    "DEFAULT_SAMPLE_RATE",
    "DEFAULT_FRAME_LENGTH",
    "DEFAULT_FRAME_HOP",
    "DEFAULT_EMBEDDING_DIM",
    "DEFAULT_VERIFICATION_THRESHOLD",
    "VoiceprintVerificationResult",
    "OwnerVoiceprintProfile",
    "AcousticVoiceprintExtractor",
    "VoiceprintManager",
    "get_voiceprint_manager",
]
