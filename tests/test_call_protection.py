"""Tests for VoiceShield Call Protection & Real-time Impersonation Detection API."""

import io
import os
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

os.environ["PDPL_MAX_AGE_SECONDS"] = "0"
os.environ["VOICEGUARD_SECRET_KEY"] = "test-secret-key-for-voiceshield-sih-2026-hackathon"
os.environ["VG_ENV"] = "development"

from voiceshield.api.main import app
from voiceshield.api.auth import create_access_token


def get_client():
    return TestClient(app)


def get_auth_headers():
    token = create_access_token(data={"sub": "test_analyst", "role": "analyst"})
    return {"Authorization": f"Bearer {token}"}


def get_dummy_wav_bytes():
    buf = io.BytesIO()
    sr = 16000
    t = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False)
    # 440Hz sine wave tone
    audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(buf, audio, sr, format="WAV")
    buf.seek(0)
    return buf.read()


def test_call_lifecycle(client, auth_headers, dummy_wav_bytes):
    # 1. Start Call Session
    start_payload = {
        "caller_number": "+91 98765 43210",
        "call_type": "inbound",
        "environment": "android_recording",
        "language_hint": "en-IN",
        "chunk_duration_s": 3.0,
    }
    res = client.post("/call/start", json=start_payload, headers=auth_headers)
    assert res.status_code == 200, res.text
    start_data = res.json()
    assert "session_id" in start_data
    session_id = start_data["session_id"]
    assert start_data["status"] == "active"
    assert start_data["caller_number"] == "+91 98765 43210"

    # 2. Ingest Call Chunk 1
    files = {"file": ("chunk1.wav", dummy_wav_bytes, "audio/wav")}
    data = {"session_id": session_id}
    res_chunk = client.post("/call/chunk", data=data, files=files, headers=auth_headers)
    assert res_chunk.status_code == 200, res_chunk.text
    chunk_data = res_chunk.json()
    assert chunk_data["session_id"] == session_id
    assert chunk_data["chunk_index"] == 1
    assert "current_risk_score" in chunk_data
    assert "risk_level" in chunk_data
    assert isinstance(chunk_data["reasons"], list)

    # 3. Get Call Status
    res_status = client.get(f"/call/status/{session_id}", headers=auth_headers)
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["session_id"] == session_id
    assert status_data["is_active"] is True
    assert status_data["total_chunks"] == 1

    # 4. Get Call Risk Trajectory
    res_risk = client.get(f"/call/risk/{session_id}", headers=auth_headers)
    assert res_risk.status_code == 200
    risk_data = res_risk.json()
    assert risk_data["total_chunks"] == 1
    assert "current_risk" in risk_data

    # 5. Get Call Explanations
    res_exp = client.get(f"/call/explanations/{session_id}", headers=auth_headers)
    assert res_exp.status_code == 200
    exp_data = res_exp.json()
    assert exp_data["total_chunks_analyzed"] == 1
    assert isinstance(exp_data["acoustic_reasons"], list)

    # 6. End Call Session
    res_end = client.post(f"/call/end?session_id={session_id}", json={"reason": "call_completed"}, headers=auth_headers)
    assert res_end.status_code == 200
    end_data = res_end.json()
    assert end_data["status"] == "ended"
    assert end_data["total_chunks"] == 1
    assert "summary_verdict" in end_data
    print("ALL CALL PROTECTION API TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    c = get_client()
    h = get_auth_headers()
    w = get_dummy_wav_bytes()
    test_call_lifecycle(c, h, w)
