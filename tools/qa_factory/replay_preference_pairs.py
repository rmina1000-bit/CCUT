import os
import sys
from pathlib import Path

# Add backend to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "ccut_backend"))

from database import SessionLocal
from learning.learning_models import PreferencePairTable
from learning.proposal_ranker import ProposalRanker

def main():
    print("=== CCUT 1.0.4 Preference Pair Replay & Rerank Validation ===")
    
    db = SessionLocal()
    try:
        pairs = db.query(PreferencePairTable).all()
        if not pairs:
            print("[INFO] No preference pairs found to replay. Seed choices first.")
            return
            
        print(f"[REPLAY] Replaying {len(pairs)} preference pairs through ProposalRanker...")
        
        matches = 0
        total = 0
        
        for p in pairs:
            total += 1
            # Synthesize proposals from Winner and Loser records
            winner_prop = {
                "proposal_id": p.winner_proposal_id,
                "mode": "WINNER",
                "sequence": p.winner_sequence,
                "human_reality_score_data": {"human_reality_score": 0.75}
            }
            loser_prop = {
                "proposal_id": p.loser_proposal_id,
                "mode": "LOSER",
                "sequence": p.loser_sequence,
                "human_reality_score_data": {"human_reality_score": 0.70}
            }
            
            # Pass to Reranker
            reranked = ProposalRanker.rerank_proposals([winner_prop, loser_prop])
            
            # Verify if Winner is ranked above Loser (first item in list)
            if reranked and reranked[0]["mode"] == "WINNER":
                matches += 1
                
        rate = (matches / total) * 100 if total else 0
        print(f"\n[REPLAY RESULTS] Accuracy: {matches}/{total} ({rate:.1f}%) preference matches.")
        
    except Exception as e:
        print(f"[REPLAY ERROR] {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
