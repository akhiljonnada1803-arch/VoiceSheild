"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear slowapi rate-limit counters between tests so the shared per-test
    /token logins (auth_client fixture) and burst tests don't bleed across tests."""
    from voiceshield.api.middleware import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from voiceshield.api.main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    from voiceshield.api.auth import create_access_token
    token = create_access_token(data={"sub": "test_analyst", "role": "analyst"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def dummy_wav_bytes():
    import io
    import numpy as np
    import soundfile as sf
    buf = io.BytesIO()
    sr = 16000
    t = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False)
    audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(buf, audio, sr, format="WAV")
    buf.seek(0)
    return buf.read()


