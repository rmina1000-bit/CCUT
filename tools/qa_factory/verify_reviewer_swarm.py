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
                "intelligence": {"description": "Wide shot of the tech office scenery."}
            }
        ]
    def get_evidence_board(self, sid):
        return [
            {"fragment_id": "SF_TEST_1", "text": "Hello world", "audio_energy": 0.5, "motion_score": 0.3},
            {"fragment_id": "SF_TEST_2", "text": "하하 웃음", "audio_energy": 0.1, "motion_score": 0.1},
            {"fragment_id": "SF_TEST_3", "text": "", "audio_energy": 0.02, "motion_score": 0.05}
        ]

def test_reviewer_swarm():
    from engine.proposal_audit_engine import ProposalAuditEngine
    
    mock_bams = MockBams()
    audit_engine = ProposalAuditEngine(mock_bams)
    
    # Simulate a proposal sequence
    proposal = {
        "proposal_id": "PROP_TEST_123",
        "mode": "B",
        "sequence": [
            {
                "fragment_id": "SF_TEST_1",
                "source_id": "SRC_TEST",
                "start": 0,
                "end": 5,
                "duration": 5.0,
                "structural": {"role": "main"}
            },
            {
                "fragment_id": "SF_TEST_2",
                "source_id": "SRC_TEST",
                "start": 5,
                "end": 10,
                "duration": 5.0,
                "structural": {"role": "reaction"}
            },
            {
                "fragment_id": "SF_TEST_3",
                "source_id": "SRC_TEST",
                "start": 10,
                "end": 15,
                "duration": 5.0,
                "structural": {"role": "scenery"}
            }
        ]
    }
    
    print("=== Running Synthetic Reviewer Swarm Audit ===")
    audit_report = audit_engine.audit_proposal(proposal, "SRC_TEST")
    
    print("\n--- Composite Metrics ---")
    print(f"Average Swarm Rating: {audit_report['average_overall_rating'] * 100:.1f}%")
    for metric, score in audit_report['composite_metrics'].items():
        print(f" - {metric}: {score:.2f}")
        
    print("\n--- Reviewer Swarm Critiques ---")
    for r in audit_report['reviews']:
        print(f"[{r['name']}] Rating: {r['overall_rating'] * 100:.1f}%")
        print(f"  Critique: {r['critique']}")
        print(f"  Scores - Flow: {r['cinematic_flow_score']}, Boredom: {r['boredom_score']}, Fatigue: {r['pacing_fatigue_score']}")
        print("-" * 50)
        
    print("=== Swarm Audit Verification Finished ===")

if __name__ == "__main__":
    test_reviewer_swarm()
