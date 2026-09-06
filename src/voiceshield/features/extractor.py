"""
Feature extraction for voice deepfake detection.

Produces an 18-dimensional feature vector:
  MFCC1..MFCC13  — mean Mel-frequency cepstral coefficients (dB power scale)
  centroid        — spectral centroid (Hz)
  bandwidth       — spectral bandwidth (Hz)
  rolloff         — 85% spectral rolloff frequency (Hz)
  jitter          — relative average perturbation of F0 periods
  shimmer         — relative amplitude variation between frames

Applies Voice Activity Trimming (VAD) so silence intervals in real voice notes
do not distort acoustic feature distributions.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

FEATURE_COLS: list[str] = [
    "MFCC1",
    "MFCC2",
    "MFCC3",
    "MFCC4",
    "MFCC5",
    "MFCC6",
    "MFCC7",
    "MFCC8",
    "MFCC9",
    "MFCC10",
    "MFCC11",
    "MFCC12",
    "MFCC13",
    "centroid",
    "bandwidth",
    "rolloff",
    "jitter",
    "shimmer",
]


def load_audio(path: str | Path, target_sr: int = 16000) -> tuple[np.ndarray, int]:
    """Load audio file to mono float32 at target_sr.

    Supports WAV, MP3, FLAC, OGG via soundfile / librosa.
    Returns (signal, sample_rate).
    """
    path = Path(path)
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = np.ascontiguousarray(data, dtype=np.float32)
    mx = np.max(np.abs(data))
    if mx > 0:
        data /= mx
    if sr != target_sr:
        data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return data, sr


def extract_features(segment: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Extract 18-dim feature vector matching the SM2026 baseline schema.

    Args:
        segment: Mono float32 audio signal.
        sr: Sample rate (default 16000).

    Returns:
        Array of shape (18,): MFCC1..13, centroid, bandwidth, rolloff, jitter, shimmer.
    """
    segment = np.asarray(segment, dtype=np.float32).reshape(-1)
    mx = np.max(np.abs(segment))
    if mx > 0:
        segment = segment / mx

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        # Voice Activity Trimming: remove leading/trailing silence pauses
        try:
            trimmed, _ = librosa.effects.trim(segment, top_db=25)
            if len(trimmed) >= int(0.2 * sr):
                segment = trimmed
        except Exception:
            pass

        if len(segment) < int(0.1 * sr):
            segment = np.pad(segment, (0, max(0, int(0.5 * sr) - len(segment))))

        # 1. MFCC 1..13 (dB power spectrum)
        mfcc = np.mean(librosa.feature.mfcc(y=segment, sr=sr, n_mfcc=13), axis=1)

        # 2. Spectral Features (centroid, bandwidth, rolloff 85%)
        cent = float(np.mean(librosa.feature.spectral_centroid(y=segment, sr=sr)))
        band = float(np.mean(librosa.feature.spectral_bandwidth(y=segment, sr=sr)))
        roll = float(np.mean(librosa.feature.spectral_rolloff(y=segment, sr=sr, roll_percent=0.85)))

        # 3. Jitter (relative period perturbation)
        pitches, magnitudes = librosa.piptrack(y=segment, sr=sr)
        f0_series: list[float] = []
        for t in range(pitches.shape[1]):
            idx = magnitudes[:, t].argmax()
            pitch = float(pitches[idx, t])
            if pitch > 50.0:
                f0_series.append(pitch)

        if len(f0_series) > 2:
            f0_arr = np.array(f0_series)
            jitter = float(np.mean(np.abs(np.diff(f0_arr))) / (np.mean(f0_arr) + 1e-8))
            jitter = float(np.clip(jitter, 0.0001, 0.1))
        else:
            jitter = 0.0105

        # 4. Shimmer (relative amplitude perturbation)
        frame_len = int(0.025 * sr)
        hop_len = int(0.010 * sr)
        rms = librosa.feature.rms(y=segment, frame_length=frame_len, hop_length=hop_len)[0]
        rms_valid = rms[rms > 1e-4]
        if len(rms_valid) > 2:
            shimmer = float(np.mean(np.abs(np.diff(rms_valid))) / (np.mean(rms_valid) + 1e-8))
            shimmer = float(np.clip(shimmer, 0.0001, 0.1))
        else:
            shimmer = 0.0177

    return np.concatenate([mfcc, [cent, band, roll, jitter, shimmer]])


def extract_from_file(path: str | Path) -> np.ndarray:
    """Load audio file and return 18-dim feature vector."""
    signal, sr = load_audio(path)
    return extract_features(signal, sr)
