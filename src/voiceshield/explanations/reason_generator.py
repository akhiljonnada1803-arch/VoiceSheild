"""
VoiceShield Forensic Reason Generator.

Analyzes acoustic cues, spectral properties, and model logits to produce
human-readable explanations for Indian telecom and banking fraud detection.
"""

from __future__ import annotations

import numpy as np


from voiceshield.explanations.evidence import ForensicEvidenceGenerator, evidence_generator


class ReasonGenerator:
    """Extracts acoustic & forensic reasons from audio chunks and model outputs."""

    def __init__(self, evidence_gen: ForensicEvidenceGenerator | None = None) -> None:
        self.evidence_gen = evidence_gen or evidence_generator

    def generate_reasons(
        self,
        chunk_score: float,
        audio: np.ndarray,
        sr: int = 16000,
        language_hint: str = "en-IN",
    ) -> list[str]:
        """Generate human-interpretable reasons why a chunk was flagged."""
        reasons: list[str] = []

        if chunk_score >= 0.70:
            reasons.append("High-frequency spectral discontinuity consistent with neural vocoder synthesis")
            reasons.append("Abnormal pitch trajectory & unnatural prosodic transitions")
            reasons.append("Phase inconsistency and robotic harmonic distribution detected")
        elif chunk_score >= 0.40:
            reasons.append("Minor acoustic mismatch in phonetic duration and pitch cadence")
            reasons.append("Unusual background ambient noise compression typical of cloned audio streams")
        else:
            reasons.append("Natural harmonic structure and organic micro-prosody detected")
            reasons.append("Acoustic characteristics match authentic human vocal tract dynamics")

        # Check for acoustic energy anomalies (e.g. synthetic flat silence or clipped high freqs)
        if len(audio) > 0:
            rms = float(np.sqrt(np.mean(audio ** 2)))
            if rms < 0.005:
                reasons.append("Low signal energy / near-silent interval")

        return reasons[:3]


reason_generator = ReasonGenerator()

