import datetime

class CognitiveFragment:
    """?곸긽???몄? ?⑥쐞濡?履쇨컿 '議곌컖' 媛앹껜"""
    def __init__(self, video_id, start, end, intelligence_scores):
        self.fragment_id = f"FRAG_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.video_id = video_id
        self.time_range = (start, end)
        
        # AI(4B/7B)媛 遺꾩꽍???먯닔 (0.0 ~ 1.0)
        self.scores = {
            "hook": intelligence_scores.get("hook", 0),      # ?쒖꽑 媛뺥깉
            "emotion": intelligence_scores.get("emotion", 0),# 媛먯젙 怨쇱엵
            "story": intelligence_scores.get("story", 0),    # ?쒖궗 以묒슂??
            "revenue": intelligence_scores.get("revenue", 0) # ?섏씡 李쎌텧 媛?μ꽦
        }
        self.metadata = {
            "tags": [], # AI媛 ?먮룞 ?앹꽦 (?? "?껋쓬", "媛뺤븘吏", "寃곗젣")
            "created_at": datetime.datetime.now().isoformat()
        }

class ArchiveManager:
    """Archive manager for finding cognitive fragments."""
    def save_fragment(self, fragment):
        # ?곗씠?곕쿋?댁뒪 諛??ㅽ넗由ъ? ???濡쒖쭅
        print(f"議곌컖 {fragment.fragment_id} ?꾩뭅?대툕 ?깅줉 ?꾨즺. (?쒓렇: {fragment.metadata['tags']})")

    def find_flashback(self, keyword):
        # "3?????щ쫫 ?곸긽 李얠븘以? ???濡쒖쭅
        return f"{keyword} 愿???덉쟾 議곌컖?ㅼ쓣 遺덈윭?듬땲??"

