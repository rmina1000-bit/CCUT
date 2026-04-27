from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

# --- 1痢? Source (?먮낯 蹂닿?) ---
class SourceVideo(BaseModel):
    source_id: str = Field(..., description="遺덈????먮낯 ID (AOID)")
    file_path: str
    title: str
    duration: float
    created_at: datetime = Field(default_factory=datetime.now)
    hash_value: str  # ?뚯씪 臾닿껐???뺤씤??
    metadata: Dict = {} # 移대찓???뺣낫, 珥ъ쁺 ?μ냼 ??

# --- 2痢? Fragment (?몄? 議곌컖) ---
class CognitiveFragment(BaseModel):
    fragment_id: str
    source_id: str
    start_time: float
    end_time: float
    duration: float
    
    # ?몄? 吏???꾨뱶 (AI 遺꾩꽍 寃곌낵)
    intelligence: Dict = {
        "hook_score": 0.0,      # ?쒖꽑 媛뺥깉??
        "narrative_score": 0.0, # ?쒖궗??以묒슂??
        "emotional_score": 0.0, # 媛먯젙 媛뺣룄
        "transcript": "",       # ?띿뒪???꾩궗
        "tags": []              # AI ?먮룞 ?앹꽦 ?쒓렇
    }
    
    status: str = "AVAILABLE" # AVAILABLE, ARCHIVED, REJECTED
    preview_path: Optional[str] = None # 議곌컖 ?몃꽕???꾨줉??寃쎈줈

# --- 3痢? Decision (寃곗젙 諛??먮떒 湲곕줉) ---
class DecisionLog(BaseModel):
    decision_id: str
    target_id: str # Fragment ID ?먮뒗 Proposal ID
    action: str    # SELECTED, REJECTED, HELD, MOVED
    user_reason: Optional[str] = None # ?좎????섏젙 吏??(梨꾪똿 ?댁슜 ??
    ai_rationale: Optional[str] = None # AI媛 ???쒖븞?덈뒗吏?????洹쇨굅
    timestamp: datetime = Field(default_factory=datetime.now)

# --- 4痢? Program (?몄꽦 諛??쒕━利? ---
class Program(BaseModel):
    program_id: str
    name: str # ?? "?쒖＜???ы뻾 ?쒕━利?, "?곗씪由?癒밸갑"
    theme_color: str
    fragments_sequence: List[str] = [] # ?좏깮??議곌컖?ㅼ쓽 ?쒖꽌 由ъ뒪??
    created_at: datetime = Field(default_factory=datetime.now)

# --- 5痢? Published (諛쒗뻾 諛??깃낵) ---
class PublishedAsset(BaseModel):
    publish_id: str
    program_id: str
    platform: str # YouTube, TikTok, Instagram
    final_video_path: str
    title: str
    performance_metrics: Dict = {} # 議고쉶?? ?섏씡, ?꾨떖瑜?(?섎쪟 ?곗씠??
    published_at: datetime = Field(default_factory=datetime.now)

