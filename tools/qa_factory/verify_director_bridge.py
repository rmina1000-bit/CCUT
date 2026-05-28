import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ccut_backend")))

# Mocking database / bams
class MockBams:
    def get_semantic_fragments(self, sid):
        return [
            {
                "fragment_id": "SF_TEST_1",
                "source_id": "SRC_TEST",
                "start": 0,
                "end": 5,
                "start_time": 0,
                "end_time": 5,
                "confidence": 0.9,
                "structural": {"edit_value": 0.8, "role": "main", "duration": 5.0},
                "intelligence": {"description": "A character is explaining the main mechanism of CCUT."}
            },
            {
                "fragment_id": "SF_TEST_2",
                "source_id": "SRC_TEST",
                "start": 5,
                "end": 10,
                "start_time": 5,
                "end_time": 10,
                "confidence": 0.85,
                "structural": {"edit_value": 0.6, "role": "reaction", "duration": 5.0},
                "intelligence": {"description": "The listener nods and smiles with warm emotion."}
            },
            {
                "fragment_id": "SF_TEST_3",
                "source_id": "SRC_TEST",
                "start": 10,
                "end": 15,
                "start_time": 10,
                "end_time": 15,
                "confidence": 0.7,
                "structural": {"edit_value": 0.4, "role": "scenery", "duration": 5.0},
                "intelligence": {"description": "Wide shot of the beautiful tech office scenery."}
            }
        ]
    def get_user_intent(self, sid):
        return {"coverage": "balanced_sources", "instruction_text": "풍경은 최대한 줄이고 감성적인 연출에 맞게 리액션을 강조해서 제안해줘."}
    def get_quick_scan(self, sid):
        return {}
    def get_evidence_board(self, sid):
        return [
            {"fragment_id": "SF_TEST_1", "text": "Hello world", "audio_energy": 0.5, "motion_score": 0.3},
            {"fragment_id": "SF_TEST_2", "text": "하하 웃음", "audio_energy": 0.1, "motion_score": 0.1},
            {"fragment_id": "SF_TEST_3", "text": "", "audio_energy": 0.02, "motion_score": 0.05}
        ]
    def save_proposals(self, sid, proposals):
        pass

from engine.proposal_engine import ProposalEngine
pe = ProposalEngine(MockBams())
print("=== Running ProposalEngine with Narrative Director Bridge ===")
proposals = pe.generate_proposals("SRC_TEST")
print("=== Verification Finished ===")
