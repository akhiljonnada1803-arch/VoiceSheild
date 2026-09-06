"""Pydantic models for VoiceShield API request and response payloads."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ModelType(StrEnum):
    classical = "classical"
    dsfnet = "dsfnet"
    dsfnet_v2 = "dsfnet_v2"
    aasist = "aasist"
    wav2vec2 = "wav2vec2"
    wavlm_base_plus = "wavlm_base_plus"
    wavlm_large = "wavlm_large"
    wav2vec2_large = "wav2vec2_large"
    xls_r = "xls_r"
    xls_r_aasist = "xls_r_aasist"
    wav2vec2_spoof = "wav2vec2_spoof"


class ForensicEvidenceItem(BaseModel):
    type: str = Field(..., description="Forensic evidence category")
    severity: str = Field(..., description="Severity level: 'LOW', 'MEDIUM', or 'HIGH'")
    explanation: str = Field(..., description="Feature-grounded empirical explanation")


class AttributionSegment(BaseModel):
    start_s: float = Field(..., description="Segment start time in seconds")
    end_s: float = Field(..., description="Segment end time in seconds")
    importance: float = Field(..., ge=0.0, le=1.0, description="Normalised importance score")


class ExplanationResult(BaseModel):
    method: str = Field(..., description="Attribution method used")
    baseline: str
    target_class: int
    frame_duration_ms: int
    attribution_frames: list[float] = Field(
        ..., description="Per-frame importance (10ms bins, normalised 0–1)"
    )
    top_segments: list[AttributionSegment] = Field(..., description="Top suspicious time windows")
    narrative: str | None = Field(
        None,
        description="Forensic summary of the verdict",
    )


class DetectionResult(BaseModel):
    label: str = Field(..., description="'Likely Human', 'Suspicious', or 'Likely Synthetic'")
    verdict: str = Field(..., description="'Likely Human', 'Suspicious', or 'Likely Synthetic'")
    risk_level: str = Field(default="Likely Human", description="'Likely Human', 'Suspicious', or 'Likely Synthetic'")
    risk_score: float = Field(default=0.0, description="Continuous risk score [0.0 - 100.0]")
    audio_profile: str = Field(default="wideband", description="'wideband', 'telephony', or 'compressed'")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Calibrated confidence [0.0 - 1.0]")
    raw_score: float = Field(default=0.0, description="Raw synthetic probability score [0.0 - 1.0]")
    probability_real: float = Field(default=0.0, description="Probability that the audio is genuine human speech [0.0 - 1.0]")
    probability_fake: float = Field(default=0.0, description="Probability that the audio is synthetic / AI voice [0.0 - 1.0]")
    final_score: float | None = Field(default=None, description="Ensemble fusion risk score [0.0 - 100.0]")
    artifact_score: float | None = Field(default=None, description="Acoustic artifact score [0.0 - 100.0]")
    metadata_score: float | None = Field(default=None, description="Audio metadata risk score [0.0 - 100.0]")
    evidence: list[ForensicEvidenceItem] = Field(default_factory=list, description="Structured forensic evidence items")
    engine_breakdown: dict[str, Any] | None = Field(default=None, description="Per-engine diagnostic breakdown")
    model: str | ModelType
    latency_ms: float
    audio_hash: str = Field(..., description="SHA-256 of uploaded audio")
    windows_analyzed: int = Field(1)
    seconds_analyzed: float | None = None
    explanation: ExplanationResult | None = None
    error: str | None = None



# ── Call Protection Schemas ──────────────────────────────────────────────────


class CallStartRequest(BaseModel):
    caller_number: str = Field(default="+91 98765 43210", description="Caller phone number or VoIP ID")
    call_type: str = Field(default="inbound", description="inbound | outbound | voip")
    environment: str = Field(default="android_recording", description="android_recording | speaker_mic | voip_stream | demo")
    language_hint: str = Field(default="en-IN", description="en-IN | hi-IN | te-IN | ta-IN | multi")
    chunk_duration_s: float = Field(default=3.0, ge=1.0, le=10.0, description="Chunk size in seconds (3-5s recommended)")


class CallStartResponse(BaseModel):
    session_id: str
    status: str = "active"
    caller_number: str
    call_type: str
    environment: str
    started_at: float


class CallChunkResponse(BaseModel):
    session_id: str
    chunk_index: int
    duration_s: float
    chunk_score: float = Field(..., description="Synthetic probability for this chunk [0.0 - 1.0]")
    chunk_label: str = Field(..., description="'Likely Human' | 'Suspicious' | 'Likely Synthetic'")
    model_used: str
    audio_profile: str = Field(default="wideband", description="'wideband', 'telephony', or 'compressed'")
    current_risk_score: float = Field(..., description="Aggregated call risk score [0.0 - 100.0%]")
    risk_level: str = Field(..., description="'Likely Human' | 'Suspicious' | 'Likely Synthetic'")
    peak_risk_score: float
    reasons: list[str] = Field(default_factory=list, description="Acoustic and forensic reasons")
    evidence: list[ForensicEvidenceItem] = Field(default_factory=list, description="Structured forensic evidence items")
    alerts: list[dict[str, Any]] = Field(default_factory=list, description="Context-aware advisories")
    latency_ms: float





class CallEndRequest(BaseModel):
    reason: str = Field(default="user_hung_up", description="user_hung_up | call_completed | threat_blocked")


class CallEndResponse(BaseModel):
    session_id: str
    status: str = "ended"
    caller_number: str
    total_chunks: int
    total_duration_s: float
    peak_risk_score: float
    final_risk_score: float
    final_risk_level: str
    summary_verdict: str
    alerts_triggered_count: int


class CallStatusResponse(BaseModel):
    session_id: str
    is_active: bool
    caller_number: str
    call_type: str
    environment: str
    total_chunks: int
    total_duration_s: float
    current_risk_score: float
    peak_risk_score: float
    risk_level: str
    recent_reasons: list[str] = Field(default_factory=list)
    recent_alerts: list[dict[str, Any]] = Field(default_factory=list)
    risk_history: list[dict[str, Any]] = Field(default_factory=list)


class CallRiskResponse(BaseModel):
    session_id: str
    current_risk: float
    peak_risk: float
    risk_level: str
    total_chunks: int
    risk_progression: list[dict[str, Any]] = Field(default_factory=list)


class CallExplanationsResponse(BaseModel):
    session_id: str
    total_chunks_analyzed: int
    acoustic_reasons: list[str]
    timeline: list[dict[str, Any]]


# ── Auth & Ops Schemas ───────────────────────────────────────────────────────


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105


class HealthResponse(BaseModel):
    status: str
    version: str
    models_loaded: dict[str, bool]


class StreamDetectionEvent(BaseModel):
    """Real-time streaming detection event."""

    timestamp_ms: float
    window_id: int
    label: str
    confidence: float
    model: str | None = None
    final: bool = False
    risk_score: float | None = None
    risk_level: str | None = None
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    evidence: list[ForensicEvidenceItem] = Field(default_factory=list)

