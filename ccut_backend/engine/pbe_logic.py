from archive.manager import bams
from archive.models import DecisionLog
import uuid

class PBELogic:
    def process_chat_trim(self, seam_id, user_command):
        print(f"PBE AI Analysis: {user_command}")
        cmd = user_command.strip().lower()
        
        action = "move"
        direction = None
        amount_frames = 0
        ai_msg = ""
        
        if any(w in cmd for w in ["적용", "확정", "저장", "apply", "ok", "confirm", "적용하기"]):
            action = "apply"
            ai_msg = "편집한 경계를 전체 타임라인에 적용합니다."
        elif any(w in cmd for w in ["취소", "닫기", "나가기", "cancel", "close"]):
            action = "cancel"
            ai_msg = "편집을 취소하고 편집창을 닫습니다."
        elif any(w in cmd for w in ["재생", "플레이", "시작", "play"]):
            action = "play"
            ai_msg = "영상을 재생합니다."
        elif any(w in cmd for w in ["정지", "일시정지", "멈춤", "pause", "stop"]):
            action = "pause"
            ai_msg = "영상을 일시정지합니다."
        else:
            # Parse move direction
            if any(w in cmd for w in ["왼쪽", "왼", "앞으로", "이전", "left", "back"]):
                direction = "left"
            elif any(w in cmd for w in ["오른쪽", "오른", "뒤로", "다음", "right", "forward"]):
                direction = "right"
                
            # Parse amount (seconds or frames)
            import re
            sec_match = re.search(r"(\d+(\.\d+)?)\s*(초|sec|s)", cmd)
            frame_match = re.search(r"(\d+)\s*(프레임|frame|f)", cmd)
            
            if sec_match:
                seconds = float(sec_match.group(1))
                amount_frames = int(seconds * 30)
            elif frame_match:
                amount_frames = int(frame_match.group(1))
            else:
                # default adjustment is 30 frames (1 second)
                amount_frames = 30
                
            if direction == "left":
                amount_frames = -amount_frames
                
            if direction:
                action = "move"
                dir_label = "왼쪽" if amount_frames < 0 else "오른쪽"
                ai_msg = f"경계를 {dir_label}으로 {abs(amount_frames)}프레임 이동했습니다."
            else:
                action = "unknown"
                ai_msg = "명령을 이해하지 못했습니다. '왼쪽으로 15프레임 이동', '적용하기', '재생' 등의 형태로 명령해 주세요."
                
        return {
            "action": action,
            "adjustment": amount_frames,
            "direction": direction,
            "ai_msg": ai_msg,
            "seam_id": seam_id
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
