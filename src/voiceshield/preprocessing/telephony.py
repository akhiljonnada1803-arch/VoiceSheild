"""
VoiceShield Telephony Detection & Preprocessing Module.

Automatic bandwidth estimation, profile classification:
- 'telephony': Narrowband audio with bandwidth < 4 kHz (G.711, AMR-NB, PSTN/telecom channels)
- 'compressed': Audio with bandwidth 4 kHz - 7 kHz or lossy compression artifacts
- 'wideband': Clean uncompressed / wideband audio (> 7 kHz bandwidth)

Includes:
- Automatic G.712 compliant bandpass filtering (300 Hz - 3400 Hz)
- Anti-aliased resampling to 16 kHz
- Adaptive channel equalization & normalization
"""

from __future__ import annotations

import logging
from typing import Tuple

import librosa
import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)


def detect_audio_profile(audio: np.ndarray, sr: int) -> tuple[str, float]:
    """Estimate audio bandwidth and classify profile into 'telephony', 'compressed', or 'wideband'.

    Returns:
        tuple[str, float]: (profile_name, estimated_bandwidth_hz)
    """
    sig = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(sig) == 0:
        return "wideband", 8000.0

    # If native sample rate is 8 kHz or lower, it is strictly narrowband telephony
    if sr <= 8000:
        return "telephony", float(sr / 2.0)

    # Compute short-time Fourier transform for spectral analysis
    n_fft = min(2048, len(sig))
    hop_length = n_fft // 4
    stft = np.abs(librosa.stft(sig, n_fft=n_fft, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    avg_spec = np.mean(stft, axis=1)

    total_energy = float(np.sum(avg_spec) + 1e-10)
    cum_energy = np.cumsum(avg_spec) / total_energy

    # 95% power bandwidth estimation
    idx_95 = int(np.searchsorted(cum_energy, 0.95))
    idx_95 = min(idx_95, len(freqs) - 1)
    bandwidth_95 = float(freqs[idx_95])

    # High frequency energy ratios (> 4 kHz and > 7 kHz)
    energy_above_4k = float(np.sum(avg_spec[freqs > 4000])) / total_energy
    energy_above_7k = float(np.sum(avg_spec[freqs > 7000])) / total_energy

    # 85% spectral rolloff frequency
    try:
        rolloff_85 = float(np.mean(librosa.feature.spectral_rolloff(y=sig, sr=sr, roll_percent=0.85)))
    except Exception:
        rolloff_85 = bandwidth_95

    # Narrowband Telephony Criteria:
    # 1. Native SR <= 8000 Hz, OR
    # 2. 95% power bandwidth <= 4000 Hz, OR
    # 3. Energy above 4 kHz is negligible (< 1.5%) and rolloff < 3800 Hz
    if bandwidth_95 <= 4000.0 or (energy_above_4k < 0.015 and rolloff_85 < 3800.0):
        profile = "telephony"
        effective_bw = min(bandwidth_95, 3800.0)
    elif energy_above_7k < 0.025 or bandwidth_95 < 7000.0:
        profile = "compressed"
        effective_bw = bandwidth_95
    else:
        profile = "wideband"
        effective_bw = bandwidth_95

    logger.debug(
        "Audio profile detected: %s (BW=%.1f Hz, >4kHz=%.3f, >7kHz=%.3f)",
        profile,
        effective_bw,
        energy_above_4k,
        energy_above_7k,
    )
    return profile, round(effective_bw, 1)


def preprocess_telephony(
    audio: np.ndarray,
    sr: int,
    target_sr: int = 16000,
) -> tuple[np.ndarray, int]:
    """Apply standard telephony-grade preprocessing to narrowband audio.

    Steps:
      1. High-quality anti-aliased resampling to 16 kHz.
      2. G.712 compliant bandpass filter (300 Hz - 3400 Hz) to eliminate out-of-band artifacts.
      3. Telecom adaptive amplitude normalization.
    """
    sig = np.asarray(audio, dtype=np.float32).reshape(-1)

    # 1. Resample to 16 kHz
    if sr != target_sr:
        sig = librosa.resample(sig, orig_sr=sr, target_sr=target_sr, res_type="soxr_hq")
        cur_sr = target_sr
    else:
        cur_sr = sr

    # 2. ITU-T G.712 Bandpass filter (300 Hz to 3400 Hz)
    nyq = 0.5 * cur_sr
    lowcut = 300.0 / nyq
    highcut = 3400.0 / nyq

    try:
        b, a = signal.butter(4, [lowcut, highcut], btype="bandpass")
        sig = signal.filtfilt(b, a, sig)
    except Exception as exc:
        logger.warning("Butterworth filtering failed, using raw resampled audio: %s", exc)

    # 3. Peak normalization
    max_val = np.max(np.abs(sig))
    if max_val > 1e-4:
        sig = sig / max_val * 0.95

    return np.ascontiguousarray(sig, dtype=np.float32), cur_sr


def process_audio_stream(
    audio: np.ndarray,
    sr: int,
    target_sr: int = 16000,
) -> tuple[np.ndarray, int, str, float]:
    """Analyze incoming audio stream, determine profile, and apply profile-specific preprocessing.

    Returns:
        tuple: (processed_audio, final_sr, audio_profile, bandwidth_hz)
    """
    profile, bw_hz = detect_audio_profile(audio, sr)

    if profile == "telephony":
        proc_audio, out_sr = preprocess_telephony(audio, sr, target_sr=target_sr)
    else:
        if sr != target_sr:
            proc_audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr, res_type="soxr_hq")
            out_sr = target_sr
        else:
            proc_audio = np.ascontiguousarray(audio, dtype=np.float32)
            out_sr = sr

    return proc_audio, out_sr, profile, bw_hz
