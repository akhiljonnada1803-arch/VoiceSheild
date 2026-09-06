<div align="center">

<img src="assets/hero.png" alt="VoiceShield" width="100%">

# VoiceShield 🛡️

**Real-time AI voice detection for India's telecom & banking fraud defence.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org)
[![SIH 2026](https://img.shields.io/badge/SIH-2026-FF6600.svg)](#-team)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[Quick start](#-quick-start) ·
[How it works](#-how-it-works) ·
[API](#-api) ·
[Results](#-results) ·
[Architecture](#-architecture) ·
[Contributing](CONTRIBUTING.md)

</div>

---

## Why VoiceShield?

AI voice cloning has made phone fraud trivially scalable. In 2024 alone, criminals stole
**US $25 M** from a single company using a deepfaked CFO on a video call, and voice-phishing
("vishing") incidents **surged over 1,600%** in early 2025. Existing detectors collapse on
real-world audio — phone codecs, background noise, unseen TTS engines — and give no explanation
a human analyst can act on.

**VoiceShield** is a production-ready platform built for **SIH 2026** that detects AI-generated
voice in real time, explains every decision with forensic evidence, and is hardened for Indian
telephony (8 kHz / G.711 / noisy environments).

---

## ✨ Features

- 🛡️ **Strict 3-tier detection** — verdicts are `Human` (>90% confidence), `Possible AI` (86–90%), or `AI` (<86%), with no ambiguous middle-ground that bad actors can exploit
- 🧠 **Multi-engine ensemble** — Wav2Vec2 spoof detection, acoustic artifact forensics, metadata analysis, all fused into a single calibrated risk score (0–100)
- 🔍 **Forensic evidence** — every verdict is backed by human-readable evidence items (jitter, HNR, spectral artifacts, pitch regularity, etc.) for analyst review
- ☎️ **Live call protection** — streaming call analysis via WebSocket; per-chunk risk scoring with EMA smoothing and anomaly boost
- 🌍 **Telephony-hardened** — automatic detection of G.711 / narrowband / VoIP profiles with adaptive weights for each condition
- ⚡ **Edge-ready** — ONNX INT8 export at **0.62 MB**, ~30 ms CPU inference — runs on Raspberry Pi / low-power edge devices
- 🔌 **VoIP bridge** — Twilio Media Streams integration for real phone call screening
- 🧾 **Chain-of-custody** — SHA-256 audit trail and NIST SP 800-86 PDF forensic reports

---

## 🎯 Classification Thresholds

VoiceShield uses a **strict, asymmetric** threshold design: a voice must score >90% real to be cleared as human. This is intentional — in fraud prevention, false negatives (missing a fake) are far more costly than false positives.

| Verdict | Risk Score | `prob_real` | Meaning |
|---------|:----------:|:-----------:|---------|
| 🟢 **Human** | 0 – 9 | > 90% | High confidence genuine speech |
| 🟡 **Possible AI** | 10 – 13 | 86% – 90% | Borderline — flag for manual review |
| 🔴 **AI** | ≥ 14 | < 86% | AI-generated or cloned voice |

---

## 📊 Results

| Benchmark | Result |
|-----------|--------|
| Real-audio pass rate (speaker/text-disjoint held-out) | **96%** |
| Kokoro voice-clone detection | **100%** |
| XTTS v2 voice-clone detection | **100%** |
| IndexTTS-2 voice-clone detection | **97%** |
| ElevenLabs-v3 (unseen engine) | **95.8%** |
| Edge model size (ONNX INT8) | **0.62 MB** |
| CPU inference latency (p50) | **~30 ms** |

> **Transparent & bounded.** Known limitations are documented, not hidden. See [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).

---

## 🏗️ Architecture

```mermaid
flowchart LR
    subgraph Client["React 18 Dashboard"]
        UI["Detect · Live · Call Protection · Results"]
    end
    subgraph API["FastAPI · JWT · Rate Limit"]
        D["/detect"]
        CS["/call/start · /call/chunk · /call/end"]
        WS["/ws/stream"]
    end
    subgraph Engine["Detection Engine (Ensemble)"]
        W2V["Wav2Vec2\nSpoof Engine"]
        ART["Acoustic Artifact\nEngine"]
        META["Metadata\nEngine"]
        RISK["Risk Engine\n(EMA + Anomaly Boost)"]
    end
    subgraph Output["3-Tier Verdict"]
        H["🟢 Human\n(prob_real > 90%)"]
        P["🟡 Possible AI\n(86–90%)"]
        A["🔴 AI\n(< 86%)"]
    end

    UI -->|audio file / mic stream| API
    D --> W2V & ART & META
    CS --> RISK
    WS --> RISK
    W2V & ART & META --> RISK
    RISK --> H & P & A
    H & P & A --> UI
    RISK -.ONNX INT8.--> EDGE["Edge (0.62 MB)"]
```

<details>
<summary><b>📁 Repository layout</b></summary>

```
VoiceSheild/
├── src/voiceshield/
│   ├── api/               # FastAPI app — auth (JWT), routes, middleware, WebSockets
│   ├── models/            # Wav2Vec2, ensemble, classical, acoustic artifact engines
│   ├── risk/              # Risk engine — EMA, anomaly boost, 3-tier classification
│   ├── alerts/            # Alert engine — actionable fraud alerts
│   ├── features/          # Acoustic feature extraction
│   ├── preprocessing/     # Telephony profile detection & audio normalization
│   ├── explanations/      # Evidence generator & human-readable reason builder
│   ├── evaluation/        # EER / minDCF scoring, OOD & adversarial eval
│   ├── call_processing/   # Per-call chunk manager & session tracking
│   ├── voip/              # Twilio Media Streams bridge & stream processor
│   └── xai/               # SHAP, GradCAM, SSL attribution
├── frontend/              # React 18 + Vite + TypeScript dashboard
├── edge/                  # 0.62 MB ONNX INT8 runtime (no torch)
├── integrations/iped/     # IPED digital-forensics pipeline add-on
├── deploy/                # Nginx + systemd scripts
├── docs/                  # Results, protocols, known limitations
└── tests/                 # pytest suite
```

</details>

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+

### Backend

```bash
git clone https://github.com/akhiljonnada1803-arch/VoiceSheild.git
cd VoiceSheild

# Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

# Install dependencies
pip install -e .

# Copy and configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY at minimum

# Run API server
$env:PYTHONPATH="src"
python -m uvicorn voiceshield.api.main:app --host 127.0.0.1 --port 8000 --reload
# API docs → http://127.0.0.1:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Dashboard → http://localhost:5173
```

### Docker Compose (all-in-one)

```bash
docker compose up --build
# Serves everything on http://localhost
```

> The production Wav2Vec2 detector needs a checkpoint at `checkpoints/`. Without it, the system falls back to the classical baseline automatically.

---

## ⚙️ Configuration

All configuration is via environment variables. Copy `.env.example` → `.env` to get started.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | dev placeholder | JWT signing key — **always set in production** (`openssl rand -hex 32`) |
| `VS_ENV` | `development` | `production` enforces strict auth & Twilio checks |
| `WAV2VEC_MODEL_PATH` | — | Path to Wav2Vec2 spoof detection checkpoint |
| `VS_ADMIN_PASSWORD` / `VS_ANALYST_PASSWORD` | demo creds | Override built-in demo users |
| `FRONTEND_ORIGIN` | — | CORS allowlist for the web app |
| `PDPL_MAX_AGE_SECONDS` | `60` | Auto-delete window for uploaded audio (PDPL compliance) |
| `VS_MAX_AUDIO_SECONDS` | `600` | Maximum accepted upload length |
| `TWILIO_AUTH_TOKEN` | — | Enables `X-Twilio-Signature` validation on VoIP bridge |

---

## 🔌 API

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|:----:|
| `POST` | `/token` | OAuth2 password → JWT | — |
| `POST` | `/detect` | Audio file → 3-tier verdict + evidence | 🔑 |
| `POST` | `/call/start` | Begin a live call protection session | 🔑 |
| `POST` | `/call/chunk/{session_id}` | Stream audio chunk → real-time risk score | 🔑 |
| `POST` | `/call/end/{session_id}` | End session → final verdict + summary | 🔑 |
| `GET`  | `/call/status/{session_id}` | Live session risk trajectory & alerts | 🔑 |
| `POST` | `/forensic/report` | NIST SP 800-86 PDF audit report | 🔑 |
| `WS`   | `/ws/stream` | Live microphone streaming (JWT as first message) | 🔑 |
| `WS`   | `/twilio/stream` | Twilio call screening bridge | ✍️ |
| `GET`  | `/models` · `/health` · `/docs` | Ops & Swagger | — |

🔑 JWT bearer · ✍️ Twilio request signature

---

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest --cov=src/voiceshield tests/
ruff check src/ tests/
```

---

## 📖 Documentation

| Document | What's inside |
|----------|---------------|
| [KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Honest platform limitations (streaming latency, scope, OOD) |
| [ADVERSARIAL_ROBUSTNESS.md](docs/ADVERSARIAL_ROBUSTNESS.md) | PGD attack curve & measured adversarial limits |
| [EVAL_PROTOCOLS.md](docs/EVAL_PROTOCOLS.md) | Evaluation protocols & how to reproduce numbers |
| [CLONE_DETECTION_LIMITS.md](docs/CLONE_DETECTION_LIMITS.md) | Measured boundaries of clone detection |
| [SYNTHESIS_ENGINES.md](docs/SYNTHESIS_ENGINES.md) | Supported TTS/voice-clone engine guide |
| [RESULTS_canonical.md](docs/RESULTS_canonical.md) | Canonical results with provenance per checkpoint |

---

## 🛠️ Tech Stack

**ML** PyTorch · transformers (Wav2Vec2, WavLM) · XGBoost · SHAP · ONNX Runtime  
**Backend** FastAPI · python-jose (JWT) · slowapi · WebSockets  
**Frontend** React 18 · Vite · TypeScript · Recharts  
**Audio** librosa · torchaudio · soundfile  
**Infra** Nginx · Docker · GitHub Actions · ruff · bandit

---

## 🗺️ Roadmap

- [x] Multi-engine ensemble (Wav2Vec2 + acoustic artifacts + metadata)
- [x] Strict 3-tier classification (Human / Possible AI / AI)
- [x] Live call protection with per-chunk streaming
- [x] Telephony profile detection & adaptive weights
- [x] Forensic evidence generation for each verdict
- [x] Twilio VoIP bridge
- [x] ONNX INT8 edge export (0.62 MB)
- [ ] GADC (Gulf/Indian voice corpus) fine-tuning for regional accents
- [ ] Backbone adversarial fine-tuning for true PGD robustness
- [ ] Mobile SDK (Android/iOS) for in-app call screening

---

## 👥 Team

| Name | Role |
|------|------|
| **Akhil Jonnada** | Detection engine, FastAPI backend, ensemble architecture, CI/CD |

**Competition:** Smart India Hackathon (SIH) 2026 — Internal Hackathon Round

---

## 🤝 Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) and our [Code of Conduct](CODE_OF_CONDUCT.md).  
For security issues, see [SECURITY.md](SECURITY.md).

---

## 📄 License

The VoiceShield source code and documentation are licensed under the [Apache License 2.0](LICENSE).  
Third-party models, pretrained weights, and external assets remain subject to their own licenses.
