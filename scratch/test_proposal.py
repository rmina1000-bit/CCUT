import sys
import os
import json
import sqlite3

# Add backend directory to path
sys.path.append(os.path.abspath("ccut_backend"))

from engine.proposal_engine import ProposalEngine

# Define a mock BAMS class or use actual DB connection to fetch fragments
class MockBAMS:
    def __init__(self):
        self.db_path = "ccut_backend/ccut_app.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def get_semantic_fragments(self, source_id):
        cur = self.conn.cursor()
        rows = cur.execute("SELECT * FROM semantic_fragments WHERE source_id=?", (source_id,)).fetchall()
        fragments = []
        for r in rows:
            # Parse JSON fields
            f = dict(r)
            f["structural"] = json.loads(f["structural"]) if f.get("structural") else {}
            f["semantic"] = json.loads(f["semantic"]) if f.get("semantic") else {}
            f["continuity"] = json.loads(f["continuity"]) if f.get("continuity") else {}
            fragments.append(f)
        return fragments

    def get_user_intent(self, source_id):
        cur = self.conn.cursor()
        row = cur.execute("SELECT * FROM user_intents WHERE source_id=?", (source_id,)).fetchone()
        if row:
            return json.loads(row["intent_json"])
        return None

    def get_quick_scan(self, source_id):
        return None

    def save_proposals(self, source_id, proposals):
        print(f"[MockBAMS] save_proposals called for {source_id} with {len(proposals)} proposals")

    def get_evidence_board(self, source_id):
        cur = self.conn.cursor()
        rows = cur.execute("SELECT * FROM evidence_board WHERE source_id=?", (source_id,)).fetchall()
        return [dict(r) for r in rows]

# Try to run proposal generation for the first source in database
try:
    bams = MockBAMS()
    cur = bams.conn.cursor()
    sources = cur.execute("SELECT DISTINCT source_id FROM semantic_fragments").fetchall()
    if not sources:
        print("No sources found with semantic fragments in DB.")
        sys.exit(1)
    
    source_id = sources[0]["source_id"]
    print(f"Testing Proposal Engine for source_id: {source_id}")
    
    engine = ProposalEngine(bams)
    proposals = engine.generate_proposals(source_id)
    print("Proposal generation completed successfully!")
except Exception as e:
    import traceback
    print("--- EXCEPTION ---")
    traceback.print_exc()
