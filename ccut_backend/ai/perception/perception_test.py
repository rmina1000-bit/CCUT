import unittest
from ccut_backend.ai.perception.visual_attention_simulator import VisualAttentionSimulator
from ccut_backend.ai.perception.auditory_fatigue_simulator import AuditoryFatigueSimulator
from ccut_backend.ai.perception.emotional_continuity_simulator import EmotionalContinuitySimulator
from ccut_backend.ai.perception.cognitive_load_simulator import CognitiveLoadSimulator
from ccut_backend.ai.perception.immersion_simulator import ImmersionSimulator
from ccut_backend.ai.perception.human_reality_score import HumanRealityScore

class TestHumanPerceptionSimulators(unittest.TestCase):
    def setUp(self):
        # Create normal and extreme mock clips
        self.normal_sequence = [
            {
                "duration": 5.0, "source_id": "SRC_1",
                "structural": {"role": "hook", "edit_value": 0.8},
                "intelligence": {"transcript": "안녕하세요 반갑습니다."},
                "motion_score": 0.4, "audio_energy": 0.5
            },
            {
                "duration": 6.0, "source_id": "SRC_1",
                "structural": {"role": "main", "edit_value": 0.6},
                "intelligence": {"transcript": "오늘 소개할 내용은 CCUT 편집 미학 운영체제입니다."},
                "motion_score": 0.3, "audio_energy": 0.4
            },
            {
                "duration": 4.0, "source_id": "SRC_1",
                "structural": {"role": "reaction", "edit_value": 0.7},
                "intelligence": {"transcript": ""},
                "motion_score": 0.2, "audio_energy": 0.1
            },
            {
                "duration": 5.0, "source_id": "SRC_1",
                "structural": {"role": "payoff", "edit_value": 0.9},
                "intelligence": {"transcript": "다음 버전을 기대해주세요!"},
                "motion_score": 0.5, "audio_energy": 0.6
            }
        ]
        
        # Extreme visual whiplash (lots of rapid cuts under 2.5s)
        self.whiplash_sequence = [
            {"duration": 1.2, "structural": {"role": "main"}, "intelligence": {"transcript": ""}} for _ in range(6)
        ]
        
        # Extremely fast subtitles (panic reading)
        self.panic_subtitle_sequence = [
            {
                "duration": 2.0, "structural": {"role": "main"},
                "intelligence": {"transcript": "이 문장은 단 2초의 짧은 시간동안 시청자가 소화하기에는 턱없이 지나치게 길어서 읽는 동안 패닉을 유발하는 문자열입니다."}
            }
        ]
        
        # Audio loudness transition shock (loud -> quiet -> loud)
        self.loudness_shock_sequence = [
            {"duration": 4.0, "audio_energy": 0.9, "intelligence": {"transcript": "소음"}},
            {"duration": 4.0, "audio_energy": 0.01, "intelligence": {"transcript": ""}},
            {"duration": 4.0, "audio_energy": 0.85, "intelligence": {"transcript": "소음"}}
        ]
        
        # High cognitive switching sequence (constantly switching source IDs)
        self.switching_sequence = [
            {"duration": 3.0, "source_id": "SRC_A", "structural": {"role": "hook"}},
            {"duration": 3.0, "source_id": "SRC_B", "structural": {"role": "main"}},
            {"duration": 3.0, "source_id": "SRC_C", "structural": {"role": "main"}},
            {"duration": 3.0, "source_id": "SRC_D", "structural": {"role": "reaction"}},
            {"duration": 3.0, "source_id": "SRC_E", "structural": {"role": "payoff"}}
        ]

    def test_visual_attention_simulator(self):
        sim = VisualAttentionSimulator()
        
        # Test normal sequence
        res_normal = sim.simulate_attention(self.normal_sequence)
        self.assertGreater(res_normal["attention_retention"], 0.5)
        self.assertFalse(res_normal["overstimulated"])
        
        # Test whiplash sequence (rapid cuts)
        res_whiplash = sim.simulate_attention(self.whiplash_sequence)
        self.assertGreater(res_whiplash["visual_fatigue"], 0.2)
        
        # Test subtitle reading panic
        res_panic = sim.simulate_attention(self.panic_subtitle_sequence)
        self.assertGreater(res_panic["visual_fatigue"], 0.05)
        self.assertTrue(any(e["type"] == "subtitle_panic" for e in res_panic["gaze_drift_events"]))

    def test_auditory_fatigue_simulator(self):
        sim = AuditoryFatigueSimulator()
        
        # Test normal sequence
        res_normal = sim.simulate_audio(self.normal_sequence)
        self.assertFalse(res_normal["breathing_recommended"])
        
        # Test loudness shock
        res_shock = sim.simulate_audio(self.loudness_shock_sequence)
        self.assertTrue(any(e["type"] == "loudness_shock" for e in res_shock["auditory_events"]))
        self.assertGreater(res_shock["loudness_instability"], 0.2)

    def test_emotional_continuity_simulator(self):
        sim = EmotionalContinuitySimulator()
        
        # Normal sequence with reaction shot following payoff
        res_normal = sim.simulate_emotion(self.normal_sequence)
        self.assertGreater(res_normal["continuity_score"], 0.6)
        
        # Jarring sequence without reaction shot after payoff
        jarring_seq = [
            {
                "duration": 5.0, "structural": {"role": "payoff", "edit_value": 0.95},
                "semantic_json": {"emotion": "tense"}
            },
            {
                "duration": 5.0, "structural": {"role": "scenery", "edit_value": 0.4},
                "semantic_json": {"emotion": "calm"}
            }
        ]
        res_jarring = sim.simulate_emotion(jarring_seq)
        self.assertTrue(any(e["type"] == "missing_reaction_carryover" for e in res_jarring["emotional_events"]))

    def test_cognitive_load_simulator(self):
        sim = CognitiveLoadSimulator(memory_buffer_capacity=3)
        
        # Normal
        res_normal = sim.simulate_cognitive_load(self.normal_sequence)
        self.assertLess(res_normal["cognitive_load"], 0.5)
        
        # Excess context switching (memory buffer eviction)
        res_switching = sim.simulate_cognitive_load(self.switching_sequence)
        self.assertGreater(res_switching["cognitive_load"], 0.3)
        self.assertTrue(any(e["type"] == "working_memory_eviction" for e in res_switching["cognitive_events"]))

    def test_immersion_simulator(self):
        sim = ImmersionSimulator()
        
        # Normal
        res_normal = sim.simulate_immersion(self.normal_sequence)
        self.assertGreater(res_normal["immersion_score"], 0.4)
        
        # Scenery boredom drift
        scenery_seq = [{"duration": 6.0, "structural": {"role": "scenery"}, "intelligence": {}} for _ in range(4)]
        res_scenery = sim.simulate_immersion(scenery_seq)
        self.assertTrue(any(e["type"] == "boredom_drift" for e in res_scenery["immersion_events"]))

    def test_human_reality_score(self):
        hrs = HumanRealityScore()
        res = hrs.evaluate_sequence(self.normal_sequence)
        
        self.assertIn("human_reality_score", res)
        self.assertIn("metrics", res)
        self.assertIn("timeline_events", res)
        
        metrics = res["metrics"]
        self.assertEqual(len(metrics), 10)  # Should have exactly 10 human perception metrics

if __name__ == "__main__":
    unittest.main()
