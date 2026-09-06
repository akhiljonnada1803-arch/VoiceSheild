"""
Call session and chunk management for real-time call protection.

Handles active call sessions, audio buffer accumulation, 3-5s chunk slicing,
and session lifecycle for Android/VoIP environments.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CallChunk:
    chunk_index: int
    audio_data: np.ndarray  # mono float32 16kHz
    timestamp: float
    duration_s: float
    score: float | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class CallSession:
    session_id: str
    caller_number: str
    call_type: str  # inbound, outbound, voip
    environment: str  # android_recording, speaker_mic, voip_stream, demo
    language_hint: str  # en-IN, hi-IN, te-IN, ta-IN, multi
    chunk_duration_s: float
    created_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    is_active: bool = True
    chunks: list[CallChunk] = field(default_factory=list)
    risk_history: list[dict[str, Any]] = field(default_factory=list)
    alerts_triggered: list[dict[str, Any]] = field(default_factory=list)
    peak_risk: float = 0.0
    current_risk: float = 0.0

    @property
    def total_duration_s(self) -> float:
        return sum(c.duration_s for c in self.chunks)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


class ChunkManager:
    """In-memory manager for active call sessions and streaming chunks."""

    def __init__(self, default_chunk_duration_s: float = 3.0) -> None:
        self.default_chunk_duration_s = default_chunk_duration_s
        self._sessions: dict[str, CallSession] = {}

    def start_session(
        self,
        caller_number: str = "Unknown Caller",
        call_type: str = "inbound",
        environment: str = "android_recording",
        language_hint: str = "en-IN",
        chunk_duration_s: float | None = None,
    ) -> CallSession:
        session_id = f"call_{uuid.uuid4().hex[:10]}"
        dur = chunk_duration_s or self.default_chunk_duration_s
        session = CallSession(
            session_id=session_id,
            caller_number=caller_number,
            call_type=call_type,
            environment=environment,
            language_hint=language_hint,
            chunk_duration_s=dur,
        )
        self._sessions[session_id] = session
        logger.info("Started call session %s for caller %s (%s)", session_id, caller_number, environment)
        return session

    def get_session(self, session_id: str) -> CallSession | None:
        return self._sessions.get(session_id)

    def add_chunk(
        self,
        session_id: str,
        audio: np.ndarray,
        sr: int = 16000,
        chunk_index: int | None = None,
    ) -> CallChunk | None:
        session = self.get_session(session_id)
        if session is None or not session.is_active:
            logger.warning("Attempted to add chunk to inactive or nonexistent session %s", session_id)
            return None

        # Ensure float32 1D
        audio_flat = np.asarray(audio, dtype=np.float32).reshape(-1)
        duration_s = len(audio_flat) / float(sr) if sr > 0 else 0.0
        idx = chunk_index if chunk_index is not None else len(session.chunks) + 1

        chunk = CallChunk(
            chunk_index=idx,
            audio_data=audio_flat,
            timestamp=time.time(),
            duration_s=round(duration_s, 2),
        )
        session.chunks.append(chunk)
        return chunk

    def end_session(self, session_id: str) -> CallSession | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        session.is_active = False
        session.ended_at = time.time()
        logger.info("Ended call session %s (chunks=%d, peak_risk=%.1f%%)", session_id, len(session.chunks), session.peak_risk)
        return session

    def cleanup_old_sessions(self, max_age_s: float = 3600.0) -> int:
        now = time.time()
        stale = [sid for sid, s in self._sessions.items() if (now - s.created_at) > max_age_s]
        for sid in stale:
            del self._sessions[sid]
        return len(stale)


chunk_manager = ChunkManager()
