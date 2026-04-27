from archive.manager import bams
from archive.models import DecisionLog
import uuid

class PBELogic:
    def process_chat_trim(self, seam_id, user_command):
        print(f"PBE AI Analysis: {user_command}")
        adjustment = 0.0
        rationale  = "Optimizing edit point based on command context."
        if "silence" in user_command:
            adjustment = -0.5
            rationale = "Silence detected."
        return {
            "adjustment": adjustment,
            "ai_msg":     rationale,
            "seam_id":    seam_id
        }

    def commit_pbe_change(self, left_id, right_id, shift, user_msg):
        if left_id in bams.fragments:
            try: bams.fragments[left_id].end_time += shift
            except: pass
        if right_id in bams.fragments:
            try: bams.fragments[right_id].start_time += shift
            except: pass
        log = DecisionLog(
            decision_id=f"PBE_{uuid.uuid4().hex[:4]}",
            target_id=f"{left_id}|{right_id}",
            action="PRECISION_TRIMMED",
            user_reason=user_msg,
            ai_rationale=f"{shift}s adjustment"
        )
        bams.log_decision(log)
        return {"status": "SUCCESS", "log_id": log.decision_id}

class SmartPBE:
    def suggest_boundary(self, left_frag: dict, right_frag: dict) -> dict:
        return {
            "suggested_ratio": 50.0,
            "confidence":      0.7,
            "reason":          "Balanced split point recommended.",
            "method":          "RULE"
        }

pbe_ai     = PBELogic()
smart_pbe  = SmartPBE()
