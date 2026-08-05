import json
import os
import tempfile
import unittest

from story_gate import proposal_axis


class TechniquePackTest(unittest.TestCase):
    def test_pack_reads_new_fixture_technique_without_operating_json_edit(self):
        fixture = {
            "version": "fixture",
            "techniques": [
                {
                    "technique_id": "fixture_boundary_nudge",
                    "display_name": "fixture",
                    "category": "cutting",
                    "authority": {
                        "verdict": "AI_ALLOWED",
                        "basis": ["description: 조각 경계 안쪽 보정"],
                    },
                    "description": "조각 경계 안쪽만 보정",
                    "requires_materials": ["word_timestamps"],
                    "requires_rules": [],
                    "engine_effect": {"max_trim_each_edge_ms": 1000},
                },
                {
                    "technique_id": "fixture_future_beat_sync",
                    "display_name": "fixture future",
                    "category": "pacing",
                    "authority": {
                        "verdict": "AI_ALLOWED",
                        "basis": ["description: 음악 박자에 맞춰 화면 전환"],
                    },
                    "description": "음악 박자에 맞춰 화면 전환",
                    "requires_materials": ["audio_beat"],
                    "requires_rules": [],
                    "engine_effect": {"cut_at_beat": True},
                },
            ],
        }
        material_state = {
            "word_timestamps": {"present": True, "count": 3},
            "audio_beat": {"present": True, "count": 3},
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(fixture, f, ensure_ascii=False)
            path = f.name
        try:
            pack = proposal_axis.build_technique_pack(
                config_path=path,
                material_state=material_state,
                seed="fixture",
            )
        finally:
            os.unlink(path)

        self.assertIn("fixture_boundary_nudge", pack["usable_now"])
        self.assertNotIn("fixture_future_beat_sync", pack["usable_now"])
        self.assertIn("fixture_boundary_nudge", pack["variants"]["A"]["techniques"])


if __name__ == "__main__":
    unittest.main()
