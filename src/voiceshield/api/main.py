"""
VoiceShield FastAPI Application.

Real-time voice-clone impersonation detection for phone calls and VoIP calls,
tailored for Indian users, telecom protection, and banking fraud prevention.

Endpoints:
    POST /token                   — JWT token issuance
    POST /call/start              — Start a new call protection session
    POST /call/chunk              — Process a 3-5s audio chunk for live risk scoring
    POST /call/end                — Finalize a call session and generate summary
    GET  /call/status/{session_id} — Get current status, metrics, and alerts
    GET  /call/risk/{session_id}   — Get real-time risk trajectory
    GET  /call/explanations/{session_id} — Get acoustic forensic explanations
    WS   /call/ws/{session_id}    — Real-time streaming WebSocket for call chunks
    POST /detect                  — Upload audio file for one-off deepfake detection
    POST /explain                 — Explain deepfake detection attribution
    GET  /models                  — List available local AI detection models
    GET  /health                  — System healthcheck

Security: JWT auth, slowapi rate limiting, PDPL auto-delete.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.concurrency import run_in_threadpool

from voiceshield.alerts.alert_engine import AlertEngine
from voiceshield.api.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    check_production_security,
    create_access_token,
    get_current_claims,
    get_current_user,
    role_for,
    verify_token,
)
from voiceshield.api.middleware import (
    PDPLTimingMiddleware,
    limiter,
    make_temp_audio_file,
    pdpl_auto_delete,
)
from voiceshield.api.schemas import (
    CallChunkResponse,
    CallEndRequest,
    CallEndResponse,
    CallExplanationsResponse,
    CallRiskResponse,
    CallStartRequest,
    CallStartResponse,
    CallStatusResponse,
    DetectionResult,
    ExplanationResult,
    HealthResponse,
    ModelType,
    StreamDetectionEvent,
    TokenResponse,
)
from voiceshield.call_processing.chunk_manager import chunk_manager
from voiceshield.explanations.reason_generator import reason_generator
from voiceshield.explanations.evidence import evidence_generator
from voiceshield.models.ensemble import ensemble_detector
from voiceshield.models.registry import registry
from voiceshield.preprocessing.telephony import detect_audio_profile
from voiceshield.risk.risk_engine import RiskEngine, RiskLevel



__version__ = "2.0.0"

logger = logging.getLogger(__name__)

risk_engine = RiskEngine()
alert_engine = AlertEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_production_security()
    try:
        import torch

        torch.set_num_threads(int(os.environ.get("VG_TORCH_THREADS", os.cpu_count() or 4)))
    except Exception:
        logger.warning("Could not set torch thread count", exc_info=True)

    # Check for available detectors on startup
    available_models = [k for k, v in registry.status().items() if v.get("available")]
    logger.info("VoiceShield initialized with active detectors: %s", available_models)
    active_key, _ = registry.find_available_detector()
    if active_key == "wav2vec2_spoof":
        print("\n" + "=" * 60)
        print("ACTIVE MODEL: wav2vec2_spoof")
        print("SOURCE: HuggingFace")
        print("STATUS: Loaded")
        print("=" * 60 + "\n")
        logger.info("ACTIVE MODEL: wav2vec2_spoof | SOURCE: HuggingFace | STATUS: Loaded")
    _sweep_media_dir()
    yield


def _sweep_media_dir() -> None:
    now = time.time()
    for f in MEDIA_DIR.glob("*"):
        try:
            if f.is_file() and now - f.stat().st_mtime > MEDIA_TTL_S:
                f.unlink(missing_ok=True)
        except OSError:
            logger.warning("media sweep: could not remove %s", f, exc_info=True)


# ── Application ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="VoiceShield API",
    version=__version__,
    description="Real-time call protection and voice-clone impersonation detection platform",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

_DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://localhost:8080",
]
_domain = os.environ.get("VOICEGUARD_DOMAIN", "").strip()
_domain_origins = [f"https://{_domain}", f"https://www.{_domain}"] if _domain else []
_single_origin = os.environ.get("FRONTEND_ORIGIN", "")
_extra_origins = os.environ.get("FRONTEND_ORIGINS", "")
ALLOWED_ORIGINS = list(
    dict.fromkeys(
        _DEFAULT_ORIGINS
        + _domain_origins
        + ([_single_origin] if _single_origin else [])
        + [o.strip() for o in _extra_origins.split(",") if o.strip()]
    )
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_DIR = Path(os.environ.get("VG_MEDIA_DIR", "/tmp/voiceshield_media"))  # noqa: S108
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_TTL_S = int(os.environ.get("VG_MEDIA_TTL_S", "900"))
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

# ── Helpers ────────────────────────────────────────────────────────────────────

ACCEPTED_CONTENT_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/flac",
    "audio/ogg",
    "application/ogg",
}
ACCEPTED_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".oga"}
CONTENT_TYPE_SUFFIXES = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
    "application/ogg": ".ogg",
}
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
_UPLOAD_CHUNK = 1024 * 1024  # 1MB
MAX_AUDIO_SECONDS = float(os.environ.get("VG_MAX_AUDIO_SECONDS", "600"))
_WIN = 48000  # 3s @ 16kHz
_SCORE_MAX_S = 60.0


def _sniff_is_audio(head: bytes) -> bool:
    if len(head) < 12:
        return False
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return True
    if head[:4] == b"fLaC":
        return True
    if head[:4] == b"OggS":
        return True
    if head[:3] == b"ID3":
        return True
    return head[0] == 0xFF and (head[1] & 0xE0) == 0xE0


async def save_upload(upload: UploadFile) -> tuple[str, str]:
    suffix = (Path(upload.filename or "audio.wav").suffix or ".wav").lower()
    ctype = (upload.content_type or "").split(";")[0].strip().lower()
    if suffix not in ACCEPTED_SUFFIXES:
        suffix = CONTENT_TYPE_SUFFIXES.get(ctype, suffix)
    if ctype not in ACCEPTED_CONTENT_TYPES and suffix not in ACCEPTED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported media type — upload WAV, MP3, FLAC, or OGG audio.",
        )

    fd, path = make_temp_audio_file(suffix=suffix)
    sha256 = hashlib.sha256()
    total = 0
    sniffed = False
    try:
        with open(path, "wb") as out:
            while chunk := await upload.read(_UPLOAD_CHUNK):
                if not sniffed:
                    if not _sniff_is_audio(chunk[:12]):
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="File content is not WAV, MP3, FLAC, or OGG audio.",
                        )
                    sniffed = True
                total += len(chunk)
                if total > MAX_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB limit",
                    )
                sha256.update(chunk)
                out.write(chunk)
        if not sniffed:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Empty upload — send WAV, MP3, FLAC, or OGG audio.",
            )
    except HTTPException:
        Path(path).unlink(missing_ok=True)
        raise
    except OSError as exc:
        Path(path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to save upload") from exc

    PDPLTimingMiddleware.register(path)
    return path, sha256.hexdigest()


def _read_audio(path: str) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return np.ascontiguousarray(data, dtype=np.float32), sr


def _detect_classical_array(audio: np.ndarray, sr: int) -> tuple[str, float, float, float, float]:
    from voiceshield.features.extractor import extract_features

    detector = registry.load("classical")
    if detector is None:
        raise RuntimeError("Classical model checkpoint not found.")
    features = extract_features(audio, sr)
    label, confidence, prob_real, prob_fake, raw_score = detector.predict_features(features)
    return label, confidence, prob_real, prob_fake, raw_score


def _detect_audio_payload(
    audio: np.ndarray, sr: int, model_key: str = "xls_r_aasist"
) -> dict[str, Any]:
    """Score a raw audio buffer with an available local detector and return full payload."""
    active_key, active_model = registry.find_available_detector(model_key)
    if active_model is None:
        raise RuntimeError(f"No available detector found for model '{model_key}'.")

    logger.info("Model selected: %s", active_key)

    if active_key == "classical":
        label, confidence, prob_real, prob_fake, raw_score = _detect_classical_array(audio, sr)
        audio_profile, _ = detect_audio_profile(audio, sr)
        final_score = round(prob_fake * 100.0, 2)
        evidence_items = evidence_generator.generate_evidence(
            wav2vec_metrics={"probability_real": prob_real, "probability_fake": prob_fake},
            final_score=final_score,
            audio_profile=audio_profile,
        )
        print(f"\n--- [VOICESHIELD INFERENCE] ---")
        print(f"raw_score:        {raw_score:.6f}")
        print(f"probability_real: {prob_real:.6f}")
        print(f"probability_fake: {prob_fake:.6f}")
        print(f"predicted_label:  {label}")
        print(f"--------------------------------\n")
        logger.info("raw_score: %.6f | probability_real: %.6f | probability_fake: %.6f | predicted_label: %s", raw_score, prob_real, prob_fake, label)
        return {
            "label": label,
            "verdict": label,
            "risk_level": label,
            "risk_score": final_score,
            "final_score": final_score,
            "confidence": round(confidence, 4),
            "prob_real": round(prob_real, 4),
            "prob_fake": round(prob_fake, 4),
            "raw_score": round(raw_score, 4),
            "used_model": "classical",
            "artifact_score": None,
            "metadata_score": None,
            "evidence": evidence_items,
            "engine_breakdown": None,
            "audio_profile": audio_profile,
        }

    if active_key == "wav2vec2_spoof":
        from voiceshield.models.ensemble import ensemble_detector

        ens_out = ensemble_detector.predict(audio, sr)
        label = ens_out["label"]
        confidence = ens_out["confidence"]
        prob_real = ens_out["probability_real"]
        prob_fake = ens_out["probability_fake"]
        raw_score = ens_out["raw_score"]
        final_score = ens_out["final_score"]

        print(f"\n--- [VOICESHIELD MULTI-ENGINE ENSEMBLE INFERENCE] ---")
        print(f"final_score:      {final_score:.2f} / 100")
        print(f"wav2vec_score:    {ens_out['engine_breakdown']['wav2vec2_spoof']['wav2vec_score']:.2f}")
        print(f"artifact_score:   {ens_out['artifact_score']:.2f}")
        print(f"metadata_score:   {ens_out['metadata_score']:.2f}")
        print(f"probability_real: {prob_real:.6f}")
        print(f"probability_fake: {prob_fake:.6f}")
        print(f"verdict:          {label}")
        print(f"------------------------------------------------------\n")
        logger.info(
            "Ensemble result: final_score=%.2f | artifact=%.2f | metadata=%.2f | verdict=%s",
            final_score,
            ens_out["artifact_score"],
            ens_out["metadata_score"],
            label,
        )
        return {
            "label": label,
            "verdict": ens_out["verdict"],
            "risk_level": ens_out["risk_level"],
            "risk_score": ens_out["risk_score"],
            "final_score": final_score,
            "confidence": round(confidence, 4),
            "prob_real": round(prob_real, 4),
            "prob_fake": round(prob_fake, 4),
            "raw_score": round(raw_score, 4),
            "used_model": "ensemble(wav2vec2+artifacts+metadata)",
            "artifact_score": ens_out["artifact_score"],
            "metadata_score": ens_out["metadata_score"],
            "evidence": ens_out.get("evidence", []),
            "engine_breakdown": ens_out["engine_breakdown"],
            "audio_profile": ens_out.get("audio_profile", "wideband"),
        }

    import torch
    import torchaudio

    wav = torch.as_tensor(np.asarray(audio, dtype=np.float32)).reshape(1, -1)
    if sr != 16000:
        wav = torchaudio.functional.resample(wav, sr, 16000)

    w = wav[..., : int(_SCORE_MAX_S * 16000)].squeeze(0)
    if w.shape[-1] < _WIN:
        w = torch.nn.functional.pad(w, (0, _WIN - w.shape[-1]))

    inp = w.unsqueeze(0)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        p = next(active_model.parameters(), None)
        if p is not None and p.device.type != dev:
            active_model.to(dev)
    except Exception:
        dev = "cpu"

    inp = inp.to(dev)
    with torch.no_grad():
        fake_prob = float(torch.softmax(active_model(inp), dim=-1)[0, 1])

    prob_fake = float(fake_prob)
    prob_real = float(1.0 - fake_prob)
    risk_score = round(prob_fake * 100.0, 2)
    final_score = risk_score
    if risk_score >= 14.0:
        label = "AI"
        confidence = prob_fake
    elif risk_score >= 10.0:
        label = "Possible AI"
        confidence = max(prob_fake, prob_real)
    else:
        label = "Human"
        confidence = prob_real
    raw_score = prob_fake

    print(f"\n--- [VOICESHIELD INFERENCE] ---")
    print(f"raw_score:        {raw_score:.6f}")
    print(f"probability_real: {prob_real:.6f}")
    print(f"probability_fake: {prob_fake:.6f}")
    print(f"predicted_label:  {label}")
    print(f"--------------------------------\n")
    logger.info("raw_score: %.6f | probability_real: %.6f | probability_fake: %.6f | predicted_label: %s", raw_score, prob_real, prob_fake, label)

    audio_profile, _ = detect_audio_profile(audio, sr)
    evidence_items = evidence_generator.generate_evidence(
        wav2vec_metrics={"probability_real": prob_real, "probability_fake": prob_fake},
        final_score=final_score,
        audio_profile=audio_profile,
    )

    return {
        "label": label,
        "verdict": label,
        "risk_level": label,
        "risk_score": risk_score,
        "final_score": final_score,
        "confidence": round(confidence, 4),
        "prob_real": round(prob_real, 4),
        "prob_fake": round(prob_fake, 4),
        "raw_score": round(raw_score, 4),
        "used_model": active_key,
        "artifact_score": None,
        "metadata_score": None,
        "evidence": evidence_items,
        "engine_breakdown": None,
        "audio_profile": audio_profile,
    }


def _detect_ssl_array(
    audio: np.ndarray, sr: int, model_key: str = "xls_r_aasist"
) -> tuple[str, float, float, float, float, str]:
    """Score a raw audio buffer with an available local detector. Returns (label, confidence, prob_real, prob_fake, raw_score, used_model)."""
    payload = _detect_audio_payload(audio, sr, model_key)
    return (
        payload["label"],
        payload["confidence"],
        payload["prob_real"],
        payload["prob_fake"],
        payload["raw_score"],
        payload["used_model"],
    )



# ── Auth Endpoints ─────────────────────────────────────────────────────────────


@app.post("/token", response_model=TokenResponse, tags=["auth"])
@limiter.limit("10/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Authenticate with username and password, returns a JWT token."""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user.get("role", "analyst")},
        expires_delta=access_token_expires,
    )
    return TokenResponse(access_token=access_token, token_type="bearer")


# ── Call Protection Endpoints ──────────────────────────────────────────────────


@app.post("/call/start", response_model=CallStartResponse, tags=["call-protection"])
async def start_call_session(
    body: CallStartRequest,
    _user: str = Depends(get_current_user),
):
    """Initialize a new live call protection session."""
    session = chunk_manager.start_session(
        caller_number=body.caller_number,
        call_type=body.call_type,
        environment=body.environment,
        language_hint=body.language_hint,
        chunk_duration_s=body.chunk_duration_s,
    )
    return CallStartResponse(
        session_id=session.session_id,
        status="active",
        caller_number=session.caller_number,
        call_type=session.call_type,
        environment=session.environment,
        started_at=session.created_at,
    )


@app.post("/call/chunk", response_model=CallChunkResponse, tags=["call-protection"])
async def process_call_chunk(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    file: UploadFile = File(...),
    _user: str = Depends(get_current_user),
):
    """Ingest a 3-5s audio chunk for an active call session, update risk and evaluate alerts."""
    session = chunk_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call session '{session_id}' not found.",
        )
    if not session.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Call session '{session_id}' has already ended.",
        )

    t0 = time.perf_counter()
    path, _ = await save_upload(file)
    background_tasks.add_task(pdpl_auto_delete, path)

    audio, sr = await run_in_threadpool(_read_audio, path)
    chunk = chunk_manager.add_chunk(session_id, audio, sr=sr)
    if not chunk:
        raise HTTPException(status_code=500, detail="Failed to add chunk to session")

    # Run AI Detection on chunk
    label, confidence, prob_real, prob_fake, raw_score, used_model = await run_in_threadpool(_detect_ssl_array, audio, sr)
    chunk_fake_prob = prob_fake
    chunk.score = chunk_fake_prob

    # Risk Engine Evaluation
    history_scores = [c.score for c in session.chunks if c.score is not None]
    risk_eval = risk_engine.compute_risk(
        new_chunk_score=chunk_fake_prob,
        previous_risk=session.current_risk,
        chunk_history=history_scores,
    )

    session.current_risk = risk_eval.current_risk
    session.peak_risk = max(session.peak_risk, risk_eval.current_risk)

    # Forensic Reasons & Context Alerts
    reasons = reason_generator.generate_reasons(
        chunk_score=chunk_fake_prob,
        audio=audio,
        sr=sr,
        language_hint=session.language_hint,
    )
    chunk.reasons = reasons

    evidence_items = evidence_generator.generate_evidence(
        wav2vec_metrics={"probability_real": prob_real, "probability_fake": prob_fake},
        final_score=round(chunk_fake_prob * 100.0, 2),
    )

    alerts = alert_engine.evaluate_alerts(
        session_id=session_id,
        risk_score=session.current_risk,
        risk_level=risk_eval.risk_level,
        caller_number=session.caller_number,
        call_type=session.call_type,
    )

    session.risk_history.append({
        "chunk_index": chunk.chunk_index,
        "timestamp": time.time(),
        "chunk_score": round(chunk_fake_prob, 4),
        "risk_score": round(session.current_risk, 2),
        "risk_level": risk_eval.risk_level.value,
        "is_anomaly": risk_eval.is_anomaly,
    })
    if alerts:
        session.alerts_triggered.extend(alerts)

    latency_ms = (time.perf_counter() - t0) * 1000
    audio_profile, _ = detect_audio_profile(audio, sr)

    return CallChunkResponse(
        session_id=session_id,
        chunk_index=chunk.chunk_index,
        duration_s=chunk.duration_s,
        chunk_score=round(chunk_fake_prob, 4),
        chunk_label=label,
        model_used=used_model,
        audio_profile=audio_profile,
        current_risk_score=round(session.current_risk, 2),
        risk_level=risk_eval.risk_level.value,
        peak_risk_score=round(session.peak_risk, 2),
        reasons=reasons,
        evidence=evidence_items,
        alerts=alerts,
        latency_ms=round(latency_ms, 2),
    )




@app.post("/call/end", response_model=CallEndResponse, tags=["call-protection"])
async def end_call_session(
    body: CallEndRequest,
    session_id: str = Query(...),
    _user: str = Depends(get_current_user),
):
    """End a call protection session and get the finalized security verdict."""
    session = chunk_manager.end_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call session '{session_id}' not found.",
        )

    risk_level = (
        RiskLevel.LIKELY_SYNTHETIC if session.peak_risk >= 14.0
        else (RiskLevel.POSSIBLE_AI if session.peak_risk >= 10.0 else RiskLevel.LIKELY_HUMAN)
    )

    summary = (
        "High-confidence synthetic voice impersonation attack detected during call."
        if risk_level == RiskLevel.LIKELY_SYNTHETIC
        else (
            "Possible AI-generated speech detected. Manual review advised."
            if risk_level == RiskLevel.POSSIBLE_AI
            else "Call verified authentic. No synthetic voice cloning detected."
        )
    )

    return CallEndResponse(
        session_id=session.session_id,
        status="ended",
        caller_number=session.caller_number,
        total_chunks=len(session.chunks),
        total_duration_s=round(session.total_duration_s, 2),
        peak_risk_score=round(session.peak_risk, 2),
        final_risk_score=round(session.current_risk, 2),
        final_risk_level=risk_level.value,
        summary_verdict=summary,
        alerts_triggered_count=len(session.alerts_triggered),
    )


@app.get("/call/status/{session_id}", response_model=CallStatusResponse, tags=["call-protection"])
async def get_call_status(
    session_id: str,
    _user: str = Depends(get_current_user),
):
    """Retrieve full metrics, risk trajectory, and active alerts for a call."""
    session = chunk_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call session '{session_id}' not found.",
        )

    recent_reasons = []
    if session.chunks:
        recent_reasons = session.chunks[-1].reasons

    risk_level = (
        RiskLevel.LIKELY_SYNTHETIC if session.current_risk >= 14.0
        else (RiskLevel.POSSIBLE_AI if session.current_risk >= 10.0 else RiskLevel.LIKELY_HUMAN)
    )

    return CallStatusResponse(
        session_id=session.session_id,
        is_active=session.is_active,
        caller_number=session.caller_number,
        call_type=session.call_type,
        environment=session.environment,
        total_chunks=len(session.chunks),
        total_duration_s=round(session.total_duration_s, 2),
        current_risk_score=round(session.current_risk, 2),
        peak_risk_score=round(session.peak_risk, 2),
        risk_level=risk_level.value,
        recent_reasons=recent_reasons,
        recent_alerts=session.alerts_triggered[-3:] if session.alerts_triggered else [],
        risk_history=session.risk_history,
    )


@app.get("/call/risk/{session_id}", response_model=CallRiskResponse, tags=["call-protection"])
async def get_call_risk(
    session_id: str,
    _user: str = Depends(get_current_user),
):
    """Retrieve time-series risk progression for a call session."""
    session = chunk_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call session '{session_id}' not found.",
        )
    risk_level = (
        RiskLevel.HIGH_RISK if session.current_risk >= 70.0
        else (RiskLevel.SUSPICIOUS if session.current_risk >= 40.0 else RiskLevel.SAFE)
    )
    return CallRiskResponse(
        session_id=session.session_id,
        current_risk=round(session.current_risk, 2),
        peak_risk=round(session.peak_risk, 2),
        risk_level=risk_level.value,
        total_chunks=len(session.chunks),
        risk_progression=session.risk_history,
    )


@app.get("/call/explanations/{session_id}", response_model=CallExplanationsResponse, tags=["call-protection"])
async def get_call_explanations(
    session_id: str,
    _user: str = Depends(get_current_user),
):
    """Retrieve cumulative acoustic explanations and anomaly timeline."""
    session = chunk_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call session '{session_id}' not found.",
        )

    all_reasons = []
    timeline = []
    for c in session.chunks:
        for r in c.reasons:
            if r not in all_reasons:
                all_reasons.append(r)
        timeline.append({
            "chunk_index": c.chunk_index,
            "timestamp": c.timestamp,
            "duration_s": c.duration_s,
            "score": c.score,
            "reasons": c.reasons,
        })

    return CallExplanationsResponse(
        session_id=session.session_id,
        total_chunks_analyzed=len(session.chunks),
        acoustic_reasons=all_reasons,
        timeline=timeline,
    )


# ── WebSocket Streaming Endpoint ───────────────────────────────────────────────


@app.websocket("/call/ws/{session_id}")
async def call_websocket_stream(websocket: WebSocket, session_id: str, token: str = ""):
    """Stream live PCM audio from phone/VoIP calls, return instant risk updates."""
    await websocket.accept()
    if token:
        try:
            verify_token(token)
        except Exception:
            await websocket.close(code=1008)
            return

    session = chunk_manager.get_session(session_id)
    if not session:
        # Auto-create if not started via REST
        session = chunk_manager.start_session(caller_number="Streaming Call")

    buffer = bytearray()
    chunk_bytes = int(session.chunk_duration_s * 16000 * 2)  # 16kHz 16-bit PCM

    try:
        await websocket.send_json({"type": "session_ready", "session_id": session.session_id})
        while session.is_active:
            data = await websocket.receive_bytes()
            buffer.extend(data)
            if len(buffer) >= chunk_bytes:
                raw_chunk = buffer[:chunk_bytes]
                buffer = buffer[chunk_bytes:]

                audio = (
                    np.frombuffer(raw_chunk, dtype=np.int16).astype(np.float32) / 32768.0
                )
                chunk = chunk_manager.add_chunk(session.session_id, audio, sr=16000)
                label, confidence, prob_real, prob_fake, raw_score, used_model = await run_in_threadpool(_detect_ssl_array, audio, 16000)
                chunk_fake_prob = prob_fake
                if chunk:
                    chunk.score = chunk_fake_prob

                history_scores = [c.score for c in session.chunks if c.score is not None]
                risk_eval = risk_engine.compute_risk(
                    new_chunk_score=chunk_fake_prob,
                    previous_risk=session.current_risk,
                    chunk_history=history_scores,
                )
                session.current_risk = risk_eval.current_risk
                session.peak_risk = max(session.peak_risk, risk_eval.current_risk)

                reasons = reason_generator.generate_reasons(chunk_fake_prob, audio, sr=16000)
                alerts = alert_engine.evaluate_alerts(
                    session_id=session.session_id,
                    risk_score=session.current_risk,
                    risk_level=risk_eval.risk_level,
                    caller_number=session.caller_number,
                )

                event = StreamDetectionEvent(
                    timestamp_ms=time.time() * 1000,
                    window_id=len(session.chunks),
                    label=label,
                    confidence=confidence,
                    model=used_model,
                    final=not session.is_active,
                    risk_score=round(session.current_risk, 2),
                    risk_level=risk_eval.risk_level.value,
                    alerts=alerts,
                    reasons=reasons,
                )
                await websocket.send_json(event.model_dump())
    except WebSocketDisconnect:
        logger.info("Call WebSocket disconnected for session %s", session_id)


# ── Standalone Detect & Explain Endpoints ──────────────────────────────────────


@app.post("/detect", response_model=DetectionResult, tags=["detection"])
@limiter.limit("60/minute")
async def detect(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: ModelType = ModelType.wav2vec2_spoof,
    explain: bool = False,
    _user: str = Depends(get_current_user),
):
    """Analyze an uploaded audio recording for synthetic voice manipulation."""
    path, audio_hash = await save_upload(file)
    background_tasks.add_task(pdpl_auto_delete, path)

    active_key, active_model = registry.find_available_detector(str(model))
    if active_model is None:
        logger.error("No detection model available for requested key '%s'", str(model))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No detection model available. Place checkpoint in checkpoints/ or set {str(model).upper()}_PATH.",
        )

    logger.info("Model selected: %s", active_key)

    try:
        t0 = time.perf_counter()
        audio, sr = await run_in_threadpool(_read_audio, path)
        det_res = await run_in_threadpool(_detect_audio_payload, audio, sr, str(model))
        latency_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:
        logger.exception("Inference failed for audio %s with model '%s'", audio_hash, active_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference failed on model '{active_key}': {str(exc)}",
        ) from exc

    return DetectionResult(
        label=det_res["label"],
        verdict=det_res["verdict"],
        risk_level=det_res["risk_level"],
        risk_score=det_res["risk_score"],
        audio_profile=det_res["audio_profile"],
        confidence=det_res["confidence"],
        raw_score=det_res["raw_score"],
        probability_real=det_res["prob_real"],
        probability_fake=det_res["prob_fake"],
        final_score=det_res["final_score"],
        artifact_score=det_res["artifact_score"],
        metadata_score=det_res["metadata_score"],
        evidence=det_res["evidence"],
        engine_breakdown=det_res["engine_breakdown"],
        model=det_res["used_model"],
        latency_ms=round(latency_ms, 2),
        audio_hash=audio_hash,
        seconds_analyzed=round(len(audio) / sr, 2) if sr > 0 else 0.0,
        explanation=None,
    )







# ── System Ops Endpoints ───────────────────────────────────────────────────────


@app.get("/models", tags=["ops"])
async def models_list():
    """List all available local detection models."""
    status_map = registry.status()
    available = [k for k, v in status_map.items() if v.get("available")]
    return {
        "available_models": available,
    }


@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health():
    """Return system health status and detector availability."""
    status_map = registry.status()
    return HealthResponse(
        status="ok",
        version=__version__,
        models_loaded={k: v["available"] for k, v in status_map.items()},
    )
