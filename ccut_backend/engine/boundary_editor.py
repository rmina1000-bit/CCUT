import uuid
from archive.manager import bams
from archive.models import DecisionLog
from engine.video_engine import video_engine
from archive.models import DecisionLog

class BoundaryEditor:
    """議곌컖 鍮꾨?諛??뺣??몄쭛李??꾩슜 而⑦듃濡ㅻ윭"""

    def get_seam_context(self, left_frag_id: str, right_frag_id: str):
        """?댁쓬???묒쁿??議곌컖怨?洹??뚯뒪???욌뮘 ?щ갚(Rejected ?ы븿) ?곗씠?곕? 異붿텧"""
        left_frag = bams.fragments.get(left_frag_id, {"id": left_frag_id, "start": 0, "duration": 5.0})
        right_frag = bams.fragments.get(right_frag_id, {"id": right_frag_id, "start": 5.0, "duration": 5.0})

        # ?뚯뒪 鍮꾨뵒??寃쎈줈 (?붾?寃쎈줈)
        video_path = "D:/test_video.mp4"

        # ?뚮끂?쇰쭏 ?꾨젅??異붿텧
        left_frames = video_engine.extract_panorama_frames(video_path, left_frag.get("start", 0), left_frag.get("start", 0) + left_frag.get("duration", 5.0), 5)
        right_frames = video_engine.extract_panorama_frames(video_path, right_frag.get("start", 5.0), right_frag.get("start", 5.0) + right_frag.get("duration", 5.0), 5)
        
        # ?뺤뀛?덈━濡?而⑦뀓?ㅽ듃 ?ш뎄??
        left_scope = {"id": left_frag.get("id"), "duration": left_frag.get("duration"), "frames": left_frames}
        right_scope = {"id": right_frag.get("id"), "duration": right_frag.get("duration"), "frames": right_frames}

        context = {
            "seam_id": f"SEAM_{left_frag_id}_{right_frag_id}",
            "left_scope": left_scope,
            "right_scope": right_scope
        }
        return context

    def finalize_boundary(self, seam_id: str, new_split_point: float, user_msg: str = "鍮꾨?諛?議곗젙"):
        """?뺣? ?몄쭛 寃곌낵瑜??꾩뭅?대툕 5痢?援ъ“???곴뎄 諛섏쁺"""
        # (?쒕??덉씠?? ?ㅼ젣 議곌컖??start/end ?쒓컙媛?蹂寃?
        
        # 3痢? Decision Log 湲곕줉 (?먮떒 洹쇨굅 ?먯궛??
        log = DecisionLog(
            decision_id=f"DEC_BND_{uuid.uuid4().hex[:4]}",
            target_id=seam_id,
            action="BOUNDARY_ADJUSTED",
            user_reason=user_msg,
            ai_rationale=f"{new_split_point}% 寃쎄퀎 ?뺤젙"
        )
        bams.log_decision(log)
        return {"status": "SUCCESS", "log_id": log.decision_id}

pbe_engine = BoundaryEditor()

