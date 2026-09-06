"""Unit tests for multi-engine ensemble detection."""

from __future__ import annotations

import unittest
import numpy as np

from voiceshield.models.ensemble import (
    Wav2Vec2SpoofEngine,
    AcousticArtifactEngine,
    MetadataEngine,
    EnsembleFusion,
)
from voiceshield.explanations.evidence import ForensicEvidenceGenerator


class TestEnsemble(unittest.TestCase):
    def setUp(self):
        self.sr = 16000
        t = np.linspace(0, 2.5, int(self.sr * 2.5), endpoint=False)
        pitch = 140.0 * (1.0 + 0.04 * np.sin(2 * np.pi * 4.0 * t))
        harmonics = sum((0.4 / k) * np.sin(2 * np.pi * k * np.cumsum(pitch) / self.sr) for k in range(1, 28))
        self.audio_real = (harmonics / (np.max(np.abs(harmonics)) + 1e-6)).astype(np.float32)
        self.audio_fake = (0.5 * np.sign(np.sin(2 * np.pi * 160.0 * t))).astype(np.float32)

    def test_artifact_engine(self):
        engine = AcousticArtifactEngine()
        out = engine.analyze(self.audio_real, self.sr)
        self.assertEqual(out["engine"], "AcousticArtifactEngine")
        self.assertIn("artifact_score", out)
        self.assertGreaterEqual(out["artifact_score"], 0.0)
        self.assertLessEqual(out["artifact_score"], 100.0)
        self.assertIn("jitter", out)
        self.assertIn("shimmer", out)
        self.assertIn("hnr_db", out)
        self.assertIn("zcr", out)

    def test_metadata_engine(self):
        engine = MetadataEngine()
        out = engine.analyze(self.audio_real, self.sr)
        self.assertEqual(out["engine"], "MetadataEngine")
        self.assertIn("metadata_risk_score", out)
        self.assertGreaterEqual(out["metadata_risk_score"], 0.0)
        self.assertLessEqual(out["metadata_risk_score"], 100.0)
        self.assertIn("sample_rate", out)
        self.assertIn("clipping_ratio", out)
        self.assertIn("silence_ratio", out)

    def test_wav2vec2_engine(self):
        engine = Wav2Vec2SpoofEngine()
        out = engine.analyze(self.audio_real, self.sr)
        self.assertEqual(out["engine"], "Wav2Vec2SpoofEngine")
        self.assertIn("wav2vec_score", out)
        self.assertIn("probability_real", out)
        self.assertIn("probability_fake", out)
        self.assertAlmostEqual(out["probability_real"] + out["probability_fake"], 1.0, places=3)

    def test_ensemble_fusion_math(self):
        fusion = EnsembleFusion(
            weight_wav2vec=0.60,
            weight_artifact=0.25,
            weight_metadata=0.15,
            threshold=50.0,
        )
        res = fusion.predict(self.audio_real, self.sr)
        w2v = res["engine_breakdown"]["wav2vec2_spoof"]["wav2vec_score"]
        art = res["artifact_score"]
        meta = res["metadata_score"]

        # Check fusion formula weights
        if res["audio_profile"] == "telephony":
            expected_final = 0.70 * w2v + 0.20 * art + 0.10 * meta
        else:
            expected_final = 0.60 * w2v + 0.25 * art + 0.15 * meta

        self.assertAlmostEqual(res["final_score"], expected_final, delta=0.05)
        self.assertAlmostEqual(res["probability_real"] + res["probability_fake"], 1.0, places=3)
        self.assertIn(res["verdict"], ("Likely Human", "Suspicious", "Likely Synthetic"))
        self.assertEqual(res["risk_level"], res["verdict"])
        self.assertIn("risk_score", res)
        self.assertIn("audio_profile", res)
        self.assertIn("evidence", res)
        self.assertIsInstance(res["evidence"], list)



    def test_forensic_evidence_generator_rules(self):
        gen = ForensicEvidenceGenerator()

        # 1. Unnatural pitch stability & Excessive spectral smoothing
        synth_artifacts = {
            "f0_std_hz": 1.2,
            "jitter": 0.0008,
            "shimmer": 0.0015,
            "hnr_db": -2.0,
            "spectral_rolloff_hz": 3200.0,
        }
        synth_metadata = {
            "sample_rate": 16000,
            "high_band_ratio": 0.0002,
            "silence_ratio": 0.72,
            "clipping_ratio": 0.09,
        }
        synth_w2v = {
            "probability_fake": 0.95,
            "probability_real": 0.05,
        }

        evidence = gen.generate_evidence(
            artifact_metrics=synth_artifacts,
            metadata_metrics=synth_metadata,
            wav2vec_metrics=synth_w2v,
            final_score=88.5,
        )

        types = [e["type"] for e in evidence]
        self.assertIn("Unnatural pitch stability", types)
        self.assertIn("Missing harmonic structure", types)
        self.assertIn("Excessive spectral smoothing", types)
        self.assertIn("Codec inconsistency", types)
        self.assertIn("High silence artifact ratio", types)
        self.assertIn("Digital clipping saturation", types)
        self.assertIn("Neural representation spoof match", types)

        for item in evidence:
            self.assertIn(item["severity"], ("LOW", "MEDIUM", "HIGH"))
            self.assertTrue(len(item["explanation"]) > 10)

    def test_forensic_evidence_organic_speech(self):
        gen = ForensicEvidenceGenerator()
        real_artifacts = {
            "f0_std_hz": 18.5,
            "jitter": 0.012,
            "shimmer": 0.025,
            "hnr_db": 16.2,
            "spectral_rolloff_hz": 6800.0,
        }
        real_metadata = {
            "sample_rate": 16000,
            "high_band_ratio": 0.06,
            "silence_ratio": 0.15,
            "clipping_ratio": 0.0,
        }
        real_w2v = {
            "probability_fake": 0.08,
            "probability_real": 0.92,
        }

        evidence = gen.generate_evidence(
            artifact_metrics=real_artifacts,
            metadata_metrics=real_metadata,
            wav2vec_metrics=real_w2v,
            final_score=12.0,
        )

        types = [e["type"] for e in evidence]
        self.assertIn("Organic vocal prosody confirmed", types)
        self.assertEqual(evidence[0]["severity"], "LOW")

    def test_telephony_detection_and_preprocessing(self):
        from voiceshield.preprocessing.telephony import (
            detect_audio_profile,
            preprocess_telephony,
            process_audio_stream,
        )

        # 1. 8kHz native telephony audio
        t_8k = np.linspace(0, 1.5, int(8000 * 1.5), endpoint=False)
        audio_8k = (0.5 * np.sin(2 * np.pi * 500.0 * t_8k)).astype(np.float32)

        prof, bw = detect_audio_profile(audio_8k, 8000)
        self.assertEqual(prof, "telephony")
        self.assertLessEqual(bw, 4000.0)

        proc_audio, out_sr = preprocess_telephony(audio_8k, 8000, target_sr=16000)
        self.assertEqual(out_sr, 16000)
        self.assertEqual(len(proc_audio), int(1.5 * 16000))

        # 2. 16kHz container with bandwidth < 4 kHz (band-limited phone recording)
        t_16k = np.linspace(0, 2.0, int(16000 * 2.0), endpoint=False)
        # Tone at 1000 Hz with zero energy above 3 kHz
        audio_narrow = (0.5 * np.sin(2 * np.pi * 1000.0 * t_16k)).astype(np.float32)

        prof_narrow, bw_narrow = detect_audio_profile(audio_narrow, 16000)
        self.assertEqual(prof_narrow, "telephony")
        self.assertLessEqual(bw_narrow, 4000.0)

        # 3. Ensemble prediction with automatic telephony adaptation
        fusion = EnsembleFusion()
        res = fusion.predict(audio_8k, 8000)
        self.assertEqual(res["audio_profile"], "telephony")
        self.assertIn("bandwidth_hz", res)
        self.assertIn(res["verdict"], ("Likely Human", "Suspicious", "Likely Synthetic"))


if __name__ == "__main__":
    unittest.main()


