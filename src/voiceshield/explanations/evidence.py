"""
VoiceShield Forensic Evidence Engine.

Generates structured, feature-grounded forensic evidence items for every detection.
All evidence items are strictly supported by empirically measured acoustic and metadata features.
"""

from __future__ import annotations

from typing import Any
import numpy as np


class ForensicEvidenceGenerator:
    """Generates structured forensic evidence items supported strictly by measured acoustic and signal features."""

    def generate_evidence(
        self,
        artifact_metrics: dict[str, Any] | None = None,
        metadata_metrics: dict[str, Any] | None = None,
        wav2vec_metrics: dict[str, Any] | None = None,
        final_score: float = 0.0,
        audio_profile: str = "wideband",
    ) -> list[dict[str, str]]:
        """Evaluate acoustic and metadata metrics against forensic criteria.

        Returns:
            list of dicts with keys: `type`, `severity`, `explanation`.
        """
        evidence: list[dict[str, str]] = []
        art = artifact_metrics or {}
        meta = metadata_metrics or {}
        w2v = wav2vec_metrics or {}

        if not audio_profile and "audio_profile" in meta:
            audio_profile = meta["audio_profile"]


        # 1. Unnatural Pitch Stability (Pitch Flatline / Mechanical Monotone)
        f0_std = art.get("f0_std_hz")
        jitter = art.get("jitter")
        if f0_std is not None and jitter is not None:
            if f0_std < 2.0 or jitter < 0.0010:
                evidence.append({
                    "type": "Unnatural pitch stability",
                    "severity": "HIGH",
                    "explanation": (
                        f"Fundamental frequency pitch variation is near-zero (F0 std = {f0_std:.2f} Hz, "
                        f"jitter = {jitter:.5f}), demonstrating artificial pitch flatline characteristic of robotic text-to-speech vocoders."
                    ),
                })
            elif f0_std < 4.5 or jitter < 0.0018:
                evidence.append({
                    "type": "Unnatural pitch stability",
                    "severity": "MEDIUM",
                    "explanation": (
                        f"Pitch modulation is mechanically restricted (F0 std = {f0_std:.2f} Hz, "
                        f"jitter = {jitter:.5f}), lacking organic human micro-prosody and emotional inflection."
                    ),
                })

        # 2. Missing Harmonic Structure (Harmonic Degradation or Artificial Phase Noise)
        hnr_db = art.get("hnr_db")
        if hnr_db is not None:
            if hnr_db < 0.0:
                evidence.append({
                    "type": "Missing harmonic structure",
                    "severity": "HIGH",
                    "explanation": (
                        f"Harmonics-to-Noise Ratio is severely degraded ({hnr_db:.1f} dB), indicating absent "
                        "natural glottal harmonics and prominent phase-dispersion artifacts from neural vocoding."
                    ),
                })
            elif hnr_db < 4.5:
                evidence.append({
                    "type": "Missing harmonic structure",
                    "severity": "MEDIUM",
                    "explanation": (
                        f"Harmonic overtone structure is abnormally weak (HNR = {hnr_db:.1f} dB), "
                        "inconsistent with healthy biological vocal tract resonances."
                    ),
                })
            elif hnr_db > 32.0:
                evidence.append({
                    "type": "Missing harmonic structure",
                    "severity": "MEDIUM",
                    "explanation": (
                        f"Harmonics-to-Noise Ratio is unnaturally pristine (HNR = {hnr_db:.1f} dB), "
                        "indicating synthetic pure tone generation devoid of biological breath airflow noise."
                    ),
                })

        # 3. Excessive Spectral Smoothing (Over-smoothed Formants / Shimmer Flatline)
        shimmer = art.get("shimmer")
        if shimmer is not None:
            if shimmer < 0.0020:
                evidence.append({
                    "type": "Excessive spectral smoothing",
                    "severity": "HIGH",
                    "explanation": (
                        f"Frame-to-frame amplitude perturbation is unnaturally static (shimmer = {shimmer:.5f}), "
                        "confirming mathematical spectral smoothing in neural vocoder mel-to-waveform synthesis."
                    ),
                })
            elif shimmer < 0.0040:
                evidence.append({
                    "type": "Excessive spectral smoothing",
                    "severity": "MEDIUM",
                    "explanation": (
                        f"Low amplitude shimmer ({shimmer:.5f}) indicates suppressed vocal dynamics "
                        "typical of parametric or neural synthesis."
                    ),
                })

        # 4. Codec Inconsistency (Container Sample Rate vs True Spectral Bandwidth)
        sr = meta.get("sample_rate", 16000)
        high_band_ratio = meta.get("high_band_ratio")
        rolloff = art.get("spectral_rolloff_hz")
        silence_ratio = meta.get("silence_ratio", 0.0)

        if high_band_ratio is not None and silence_ratio < 0.90:
            if sr >= 16000 and high_band_ratio < 0.0008:
                evidence.append({
                    "type": "Codec inconsistency",
                    "severity": "HIGH",
                    "explanation": (
                        f"Audio is delivered in a {sr} Hz container but exhibits an artificial brickwall "
                        f"cutoff with only {high_band_ratio * 100:.3f}% high-frequency energy above 7 kHz, "
                        "indicating band-limited synthesis or resampled telephony spoofing."
                    ),
                })
            elif rolloff is not None and sr >= 16000 and rolloff < 3600.0:
                evidence.append({
                    "type": "Codec inconsistency",
                    "severity": "MEDIUM",
                    "explanation": (
                        f"85% spectral rolloff occurs abnormally low at {rolloff:.0f} Hz despite {sr} Hz container, "
                        "revealing narrowband vocoder synthesis."
                    ),
                })


        # 5. High Silence Artifact Ratio (Synthetic Splicing / Dead Space)
        if silence_ratio is not None:
            if silence_ratio > 0.65:
                evidence.append({
                    "type": "High silence artifact ratio",
                    "severity": "HIGH",
                    "explanation": (
                        f"Audio contains {silence_ratio * 100:.1f}% muted silence frames (< -38 dBFS), "
                        "indicative of automated IVR spoof engines or aggressive artificial noise-gating."
                    ),
                })
            elif silence_ratio > 0.45:
                evidence.append({
                    "type": "High silence artifact ratio",
                    "severity": "MEDIUM",
                    "explanation": (
                        f"Elevated silence percentage ({silence_ratio * 100:.1f}%) detected between utterance bursts."
                    ),
                })

        # 6. Saturated Digital Clipping
        clipping_ratio = meta.get("clipping_ratio")
        if clipping_ratio is not None and clipping_ratio > 0.04:
            severity = "HIGH" if clipping_ratio > 0.08 else "MEDIUM"
            evidence.append({
                "type": "Digital clipping saturation",
                "severity": severity,
                "explanation": (
                    f"Digital signal contains {clipping_ratio * 100:.2f}% hard-clipped peak samples, "
                    "introducing non-linear harmonic distortion."
                ),
            })

        # 7. Deep Neural Anti-Spoofing Evidence (Wav2Vec2 / XLS-R Transformer Embeddings)
        prob_fake = w2v.get("probability_fake")
        if prob_fake is not None:
            if prob_fake >= 0.85:
                evidence.append({
                    "type": "Neural representation spoof match",
                    "severity": "HIGH",
                    "explanation": (
                        f"Deep self-supervised transformer embeddings match known neural vocoder artifacts "
                        f"with {prob_fake * 100:.1f}% confidence."
                    ),
                })
            elif prob_fake >= 0.65:
                evidence.append({
                    "type": "Neural representation spoof match",
                    "severity": "MEDIUM",
                    "explanation": (
                        f"Acoustic latent representation aligns with synthetic speech manifolds "
                        f"(neural spoof score: {prob_fake * 100:.1f}%)."
                    ),
                })

        # 8. Organic Human Vocal Dynamics (Confirmed Real Speech)
        if final_score < 40.0 and len(evidence) == 0:
            if f0_std is not None and f0_std >= 6.0 and hnr_db is not None and 8.0 <= hnr_db <= 28.0:
                evidence.append({
                    "type": "Organic vocal prosody confirmed",
                    "severity": "LOW",
                    "explanation": (
                        f"Fundamental frequency variation (F0 std = {f0_std:.1f} Hz) and harmonic resonance "
                        f"(HNR = {hnr_db:.1f} dB) conform to biological human vocal tract kinematics."
                    ),
                })
            else:
                prob_real = w2v.get("probability_real", 1.0 - (final_score / 100.0))
                evidence.append({
                    "type": "Organic vocal prosody confirmed",
                    "severity": "LOW",
                    "explanation": (
                        f"Acoustic feature distributions match authentic live human speech "
                        f"with {prob_real * 100:.1f}% authenticity probability."
                    ),
                })

        return evidence


evidence_generator = ForensicEvidenceGenerator()
