# VoiceShield Detection Engine — Accuracy Audit

> Audited files: `ensemble.py`, `hf_spoof.py`, `registry.py`, `api/main.py`, `preprocessing/telephony.py`, `features/extractor.py`, `risk/risk_engine.py`

---

## 🔴 CRITICAL BUGS (Direct Accuracy Impact)

### BUG 1 — Double Inference on `/detect` (Conflicting Results Overwrite Each Other)

**File:** [`main.py:796–826`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/api/main.py#L796-L826)

```python
# Line 796: First full ensemble inference run inside _detect_ssl_array
label, confidence, prob_real, prob_fake, raw_score, used_model = await run_in_threadpool(_detect_ssl_array, audio, sr, str(model))

# Line 815: Second full ensemble inference run again (for the same audio!)
ens_out = ensemble_detector.predict(audio, sr)
label = ens_out["verdict"]
...
```

**What's happening:** For `wav2vec2_spoof`, `_detect_ssl_array` internally calls `ensemble_detector.predict()` (see `main.py:323`), which is **one complete inference pass**. Then, lines 814–826 call `ensemble_detector.predict()` **a second time** on the **original unprocessed audio** (not preprocessed). The second call's results silently **overwrite** the first call's results.

**Why this causes inaccuracy:**
- The two runs may produce different results due to non-determinism in wav2vec2 attention layers.
- The second call bypasses the `used_model` result from run 1 but does use `active_key == "wav2vec2_spoof"` — so it always runs the second time regardless.
- The `latency_ms` measured (line 797) only covers Run 1. Run 2 (the one whose results are actually returned) is not timed at all.

**Fix:** Remove the redundant second call. `_detect_ssl_array` already returns the full ensemble output. Simply return its values directly:

```diff
- label, confidence, prob_real, prob_fake, raw_score, used_model = await run_in_threadpool(...)
- ...
- if used_model.startswith("ensemble") or active_key == "wav2vec2_spoof":
-     ens_out = ensemble_detector.predict(audio, sr)   # ← DELETE THIS ENTIRE BLOCK
-     label = ens_out["verdict"]
-     ...
+ # _detect_ssl_array already returns the ensemble result for wav2vec2_spoof
+ label, confidence, prob_real, prob_fake, raw_score, used_model = await run_in_threadpool(_detect_ssl_array, audio, sr, str(model))
+ final_score = round(prob_fake * 100.0, 2)
```

---

### BUG 2 — `prob_fake` Normalization Bug in `hf_spoof.py`

**File:** [`hf_spoof.py:68–79`](file:///c:/PROJECTS/SIH%202026/Internal Hackathon/VoiceSheild/src/voiceshield/models/hf_spoof.py#L68-L79)

```python
prob_real = 0.5   # ← Default: 50/50 prior
prob_fake = 0.5

for item in results:
    norm = _norm_label(item["label"])
    if norm == "real":
        prob_real = float(item["score"])
    elif norm == "fake":
        prob_fake = float(item["score"])

total = prob_real + prob_fake
if total > 0:
    prob_real = prob_real / total  # ← Re-normalizing already-softmaxed probabilities!
    prob_fake = prob_fake / total
```

**What's happening:** The HuggingFace pipeline already returns **softmax-normalized probabilities** that sum to 1.0. The `prob_real` and `prob_fake` from the pipeline are already calibrated (e.g., `0.85 real, 0.15 fake`).

By dividing by `total` again, if only one label matches (e.g., the model has a label like `"bonafide"` that maps to `"real"` but its pair maps to neither), the 0.5 default for the unmatched label gets injected and **re-normalizes both values incorrectly**. For example:

| Situation | prob_real | prob_fake | After re-norm |
|---|---|---|---|
| Both labels matched | 0.85 | 0.15 | 0.85, 0.15 ✅ |
| Only "fake" matched | **0.50 (default!)** | 0.15 | 0.77, 0.23 ❌ |
| Only "real" matched | 0.85 | **0.50 (default!)** | 0.63, 0.37 ❌ |

**Fix:** Initialize defaults to `0.0` (not `0.5`), and skip re-normalization if both are available from the model:

```python
prob_real = 0.0
prob_fake = 0.0
for item in results:
    norm = _norm_label(item["label"])
    if norm == "real":
        prob_real = float(item["score"])
    elif norm == "fake":
        prob_fake = float(item["score"])
total = prob_real + prob_fake
if total > 1e-6:
    prob_real /= total
    prob_fake /= total
else:
    prob_real, prob_fake = 0.5, 0.5  # True fallback when nothing matched
```

---

### BUG 3 — `AcousticArtifactEngine` Jitter Computed via `piptrack` (Unreliable F0)

**File:** [`ensemble.py:109–121`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/models/ensemble.py#L109-L121)

```python
pitches, magnitudes = librosa.piptrack(y=sig, sr=sr)
for t in range(pitches.shape[1]):
    idx = magnitudes[:, t].argmax()   # ← Peak magnitude index, not pitch bin
    pitch = float(pitches[idx, t])
    if pitch > 50.0:
        f0_series.append(pitch)
```

**What's happening:** `librosa.piptrack()` returns a sparse 2D matrix where most values are 0. The idiom `magnitudes[:, t].argmax()` finds the **frequency bin with maximum magnitude**, which is **not the same** as the frequency bin with a valid tracked pitch. For frames without any voiced activity, this returns a random dominant frequency bin (possibly from noise), inflating the `f0_series` with garbage values.

This incorrectly lowers jitter variance estimates and makes **real human voices look robotic** (flat pitch), pushing `risk_points` higher and causing **false positives**.

**Fix:** Use the standard `librosa.piptrack` idiom with a magnitude threshold:

```python
pitches, magnitudes = librosa.piptrack(y=sig, sr=sr, fmin=50, fmax=400)
mag_threshold = np.max(magnitudes) * 0.1  # only trust strong pitch frames
for t in range(pitches.shape[1]):
    idx = magnitudes[:, t].argmax()
    if magnitudes[idx, t] > mag_threshold and pitches[idx, t] > 50.0:
        f0_series.append(float(pitches[idx, t]))
```

---

## 🟠 SIGNIFICANT DESIGN FLAWS (High Accuracy Impact)

### FLAW 4 — Ensemble Weights Are Fixed; No Calibration for Real-World Indian Accents

**File:** [`ensemble.py:298–308`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/models/ensemble.py#L298-L308)

```python
weight_wav2vec: float = 0.60,
weight_artifact: float = 0.25,
weight_metadata: float = 0.15,
```

The base HuggingFace model `Gustking/wav2vec2-large-xlsr-deepfake-audio-classification` was trained predominantly on **English speech** (LibriSpeech, ASVspoof). Indian languages have distinct prosodic patterns (tonal rhythm in Tamil, Hindi pitch accent), which the model hasn't seen. This creates a systematic bias where legitimate Indian-accented real speech gets scored as suspicious by the wav2vec2 engine, and the 60% weight amplifies this.

**Impact:** Elevated false-positive rate for Indian-language calls.

---

### FLAW 5 — `AcousticArtifactEngine` Risk Score Not Normalized to [0,1] Space

**File:** [`ensemble.py:152–182`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/models/ensemble.py#L152-L182)

```python
risk_points = 0.0
if f0_std < 3.0:   risk_points += 30.0
if jitter < 0.0015: risk_points += 25.0
if shimmer < 0.003: risk_points += 20.0
if hnr_db < 0.0:   risk_points += 15.0
if zcr_mean > 0.25: risk_points += 15.0
artifact_score = np.clip(risk_points, 0.0, 100.0)
```

The maximum achievable `artifact_score` is `30+25+20+15+15 = 105`, capped to 100. But in practice, a **completely silent audio clip** would trigger:
- `f0_std = 15.0` (default, no penalty) 
- `jitter = 0.0105` (default, no penalty)
- `shimmer = 0.0177` (default, no penalty)
- `hnr_db` — for silence, `hpss` returns near-zero, which gives near-0 dB → no penalty
- `zcr_mean ≈ 0` → no penalty

→ `artifact_score = 0.0`, meaning silence is scored as "perfectly real". This is a calibration gap: the thresholds were hand-tuned without a validation dataset.

---

### FLAW 6 — `MetadataEngine` Receives **Original** Audio, Not Preprocessed Audio

**File:** [`ensemble.py:330`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/models/ensemble.py#L330)

```python
w2v_out = self.wav2vec_engine.analyze(proc_audio, proc_sr)   # preprocessed
art_out = self.artifact_engine.analyze(proc_audio, proc_sr)  # preprocessed
meta_out = self.metadata_engine.analyze(audio, sr, ...)      # ← original raw audio!
```

The `MetadataEngine` intentionally receives the raw audio to detect native sample rate and codec artifacts. However, the `high_band_ratio` calculation uses `freqs > 7000`, which is only meaningful if the audio is at 44.1kHz or higher. If the audio comes in at 22kHz (common for compressed recordings), this heuristic misfires.

Also, if the original audio is 44.1kHz, `high_band_ratio` may be very low even for real human voices, triggering the `metadata_risk += 20.0` penalty incorrectly on line 268.

---

### FLAW 7 — `_detect_ssl_array` Returns Stale Data for wav2vec2_spoof

**File:** [`main.py:320–346`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/api/main.py#L320-L346)

```python
if active_key == "wav2vec2_spoof":
    ens_out = ensemble_detector.predict(audio, sr)
    label = ens_out["label"]     # ← "verdict" field used as "label"
    raw_score = ens_out["raw_score"]  # ← This is prob_fake, NOT final_score/100
    return label, ..., raw_score, "ensemble(...)"
```

`raw_score` here is `prob_fake` (0.0–1.0) from the wav2vec2 head **only**, not the full ensemble score. But then in `main.py:814–825`, `ensemble_detector.predict()` is called again and returns `raw_score = prob_fake` at the ensemble level — which is `final_score / 100`. The two `raw_score` values mean **different things** (one is wav2vec2-only probability, the other is ensemble-level probability). This inconsistency propagates to the `DetectionResult` response.

---

## 🟡 MODERATE ISSUES

### ISSUE 8 — `_norm_label` Has No Mapping for LABEL_0 / LABEL_1 Style Labels

**File:** [`hf_spoof.py:25–33`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/models/hf_spoof.py#L25-L33)

```python
def _norm_label(raw: str) -> str:
    s = raw.strip().lower()
    if any(k in s for k in ("fake", "spoof", "ai", "synth", "clone")):
        return "fake"
    if any(k in s for k in ("real", "human", "bona", "genuine")):
        return "real"
    return "fake"  # ← Unknown label → conservative fallback
```

Some HuggingFace models use numeric labels like `LABEL_0`, `LABEL_1`. If the Gustking model uses this scheme and the label order is `LABEL_0=bonafide, LABEL_1=spoof` (standard ASVspoof convention), neither label will match any keyword. Both fall through to the `"fake"` fallback → **the model always outputs fake for every audio**.

**Fix:** Add label index handling:
```python
if s in ("label_0", "0"):
    return "real"  # bonafide = 0 in ASVspoof convention
if s in ("label_1", "1"):
    return "fake"
```

---

### ISSUE 9 — `RiskEngine` Thresholds Are Inconsistent Between Modules

**File:** [`risk_engine.py:85–93`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/risk/risk_engine.py#L85-L93) vs [`ensemble.py:352–360`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/models/ensemble.py#L352-L360)

| Module | Human | Suspicious | Synthetic |
|---|---|---|---|
| `RiskEngine` | ≤ 30 | 31–60 | > 60 |
| `EnsembleFusion` | ≤ 30 | 31–60 | > 60 |
| `main.py` (SSL path, L375) | ≤ 30 | 31–60 | > 60 |
| `main.py` (call/end, L564) | < 70 | 40–70 | ≥ 70 |

The `/call/end` endpoint uses a **completely different threshold** (40/70 instead of 30/60). A call with `peak_risk = 65` would be `"Likely Synthetic"` according to the ensemble, but only `"Suspicious"` in the call summary. This creates contradictory verdicts between the chunk-level and call-level responses.

---

### ISSUE 10 — No Audio Length Guard Before Wav2Vec2 Inference

**File:** [`ensemble.py:311–330`](file:///c:/PROJECTS/SIH%202026/Internal%20Hackathon/VoiceSheild/src/voiceshield/models/ensemble.py#L311-L330)

There's no minimum duration check before passing audio to the HuggingFace pipeline. Wav2Vec2 has a known minimum input size requirement (~400 samples). Very short audio clips (< 0.025s) sent to the pipeline can cause silent inference failures or nonsensical probabilities.

The `MetadataEngine` adds a risk penalty for clips < 0.6s, but the wav2vec2 inference still runs. For a 0.1s silence clip, wav2vec2 may return an arbitrary probability.

---

## Summary Table

| # | Severity | Bug/Flaw | File | Fix Effort |
|---|---|---|---|---|
| 1 | 🔴 Critical | Double inference on /detect — results overwritten | `main.py:814` | Small |
| 2 | 🔴 Critical | `hf_spoof` 0.5 default corrupts re-normalization | `hf_spoof.py:68` | Tiny |
| 3 | 🔴 Critical | `piptrack` idiom returns garbage F0 values | `ensemble.py:109` | Small |
| 4 | 🟠 High | No Indian-accent calibration on HF model (60% weight) | `ensemble.py:298` | Large |
| 5 | 🟠 High | Artifact scoring thresholds hand-tuned, no validation | `ensemble.py:152` | Medium |
| 6 | 🟠 High | MetadataEngine high-band heuristic misfires at 44.1kHz | `ensemble.py:330` | Medium |
| 7 | 🟠 High | `raw_score` has inconsistent semantics across code paths | `main.py:328` | Medium |
| 8 | 🟡 Moderate | `_norm_label` doesn't handle LABEL_0/LABEL_1 style | `hf_spoof.py:25` | Tiny |
| 9 | 🟡 Moderate | Threshold mismatch: chunk-level vs call-end verdict | `main.py:564` | Tiny |
| 10 | 🟡 Moderate | No minimum audio duration guard before wav2vec2 | `ensemble.py:311` | Small |

---

## Recommended Fix Priority

1. **Fix Bug #1** (double inference) — most impactful, easiest to fix
2. **Fix Bug #2** (hf_spoof normalization) — 2-line change, immediate accuracy gain
3. **Fix Bug #8** (LABEL_0 mapping) — verify actual model labels first (`print(results)`)
4. **Fix Bug #3** (piptrack F0) — reduces false positives on real human voices
5. **Fix Issue #9** (threshold consistency) — stops contradictory verdicts

> [!TIP]
> Run `print(results)` in `hf_spoof.predict_proba_array` to first confirm what label strings the model actually returns. This will immediately tell you if Bug #8 is actively causing always-fake outputs.
