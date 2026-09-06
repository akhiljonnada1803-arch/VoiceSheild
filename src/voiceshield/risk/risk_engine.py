"""
VoiceShield Risk Engine.

Aggregates per-chunk synthetic voice scores into a continuous call risk score (0-100%).
Features:
- Exponential moving average with anomaly boost
- Hysteresis & threshold categorization:
  0-9:   Human          (prob_real > 90%)
  10-14: Possible AI    (prob_real 86-90%)
  15-100: AI            (prob_real < 86%)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LIKELY_HUMAN     = "Human"        # score < 10  (prob_real > 90%)
    POSSIBLE_AI      = "Possible AI"  # score 10-14 (prob_real 86-90%)
    LIKELY_SYNTHETIC = "AI"           # score >= 14 (prob_real < 86%)

    # Legacy aliases for backward compatibility
    SAFE        = "Human"
    SUSPICIOUS  = "Possible AI"
    HIGH_RISK   = "AI"


@dataclass
class RiskEvaluation:
    current_risk: float        # 0.0 to 100.0
    risk_level: RiskLevel
    chunk_score: float         # 0.0 to 1.0 (prob of synthetic)
    peak_risk: float           # Max risk recorded in call
    confidence: float          # 0.0 to 1.0 confidence in verdict
    is_anomaly: bool           # Sudden spike detected


class RiskEngine:
    """Aggregates chunk predictions into a stable, responsive call risk score."""

    def __init__(self, smoothing_alpha: float = 0.45, boost_factor: float = 1.25) -> None:
        self.alpha = smoothing_alpha
        self.boost_factor = boost_factor

    def compute_risk(
        self,
        new_chunk_score: float,
        previous_risk: float = 0.0,
        chunk_history: list[float] | None = None,
    ) -> RiskEvaluation:
        """Calculate updated call risk given a new chunk fake-probability [0, 1].

        Returns RiskEvaluation with 0-100% score, 3-tier risk category, and calibrated confidence.
        """
        raw_pct = new_chunk_score * 100.0

        if previous_risk <= 0.0 and (not chunk_history or len(chunk_history) <= 1):
            current_risk = raw_pct
        else:
            # Exponential weighted smoothing with rapid rise on high scores
            if raw_pct > previous_risk:
                # Rise fast when high fake probability detected
                effective_alpha = min(0.85, self.alpha * self.boost_factor)
            else:
                # Decay slowly to prevent spoofers from hiding behind short pauses
                effective_alpha = max(0.20, self.alpha * 0.6)

            current_risk = (effective_alpha * raw_pct) + ((1.0 - effective_alpha) * previous_risk)

        # High confidence spike logic
        is_anomaly = (new_chunk_score >= 0.85) and (previous_risk < 50.0)
        if is_anomaly:
            current_risk = max(current_risk, 75.0)

        current_risk = round(max(0.0, min(100.0, current_risk)), 1)

        # 3-Tier Categorization:
        # 0-9:   Human       (prob_real > 90%)
        # 10-14: Possible AI (prob_real 86-90%)
        # 15+:   AI          (prob_real < 86%)
        if current_risk >= 14.0:
            level = RiskLevel.LIKELY_SYNTHETIC
            confidence = round(current_risk / 100.0, 4)
        elif current_risk >= 10.0:
            level = RiskLevel.POSSIBLE_AI
            confidence = round(max(current_risk, 100.0 - current_risk) / 100.0, 4)
        else:
            level = RiskLevel.LIKELY_HUMAN
            confidence = round((100.0 - current_risk) / 100.0, 4)

        return RiskEvaluation(
            current_risk=current_risk,
            risk_level=level,
            chunk_score=round(new_chunk_score, 4),
            peak_risk=current_risk,
            confidence=confidence,
            is_anomaly=is_anomaly,
        )



risk_engine = RiskEngine()
