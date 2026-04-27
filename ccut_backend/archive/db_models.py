from sqlalchemy import Column, String, Float, DateTime, JSON, ForeignKey
from database import Base
import datetime

class SourceTable(Base):
    __tablename__ = "sources"
    source_id = Column(String, primary_key=True, index=True)
    file_path = Column(String)
    title = Column(String)
    duration = Column(Float)
    fps = Column(Float, default=30.0)
    hash_value = Column(String, index=True, nullable=True) # [STEP 1] Fingerprint
    created_at = Column(DateTime, default=datetime.datetime.now)

class FragmentTable(Base):
    __tablename__ = "fragments"
    fragment_id = Column(String, primary_key=True, index=True)
    source_id = Column(String, ForeignKey("sources.source_id"))
    start_time = Column(Float)
    end_time = Column(Float)
    duration = Column(Float)
    intelligence = Column(JSON) # deep merge logic will apply here
    waveform = Column(JSON)
    status = Column(String, default="AVAILABLE")

class DecisionTable(Base):
    __tablename__ = "decisions"
    decision_id = Column(String, primary_key=True)
    target_id = Column(String)
    action = Column(String)
    adjust_data = Column(JSON, nullable=True)
    user_reason = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.now)

class ProgramTable(Base):
    __tablename__ = "programs"
    program_id = Column(String, primary_key=True, index=True)
    name = Column(String)
    theme_color = Column(String)
    fragments_sequence = Column(JSON, default=list)
    export_path = Column(String, nullable=True)
    status = Column(String, default="DRAFT")
    last_updated_at = Column(DateTime, default=datetime.datetime.now)
    created_at = Column(DateTime, default=datetime.datetime.now)

class PublishedTable(Base):
    __tablename__ = "published"
    publish_id = Column(String, primary_key=True, index=True)
    program_id = Column(String)
    platform = Column(String)
    final_video_path = Column(String)
    title = Column(String)
    published_at = Column(DateTime, default=datetime.datetime.now)

class EvidenceTable(Base):
    __tablename__ = "evidence_board"
    fragment_id = Column(String, primary_key=True, index=True)
    source_id = Column(String, ForeignKey("sources.source_id"), index=True)
    start = Column(Float) # [STEP 2] 명시적 시작 시간
    end = Column(Float)   # [STEP 2] 명시적 종료 시간
    time_offset = Column(Float) # Legacy 
    text = Column(String, nullable=True)
    audio_energy = Column(Float, default=0.0)
    silence = Column(JSON, default=list)
    scene_change = Column(JSON, default=list)
    motion_score = Column(Float, default=0.0)
    keyframe = Column(String, nullable=True) # [STEP 2] 대표 키프레임 경로
    speaker = Column(String, nullable=True)
    confidence = Column(Float, default=1.0)
    fallback_reason = Column(String, nullable=True) # [STEP 2] 분석 실패 사유
    worker_sources = Column(JSON, default=dict)      # [STEP 2] 필드별 워커 정보
    metadata_json = Column(JSON, default=dict)
    last_updated = Column(DateTime, default=datetime.datetime.now)

class QuickScanTable(Base):
    __tablename__ = "quick_scan"
    source_id = Column(String, primary_key=True, index=True)
    summary = Column(JSON) # {text, confidence, fallback_reason, summary_basis}
    representative_images = Column(JSON) # [ {time, keyframe, reason}, ... ]
    hypothesis = Column(JSON) # {video_type, core_elements, recommended_direction, reason, confidence, fallback_reason}
    questions = Column(JSON) # [ "Q1", "Q2", ... ]
    default_intent_seed = Column(JSON) # {..., source: "default_hypothesis"}
    evidence_progress = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now)

class SubtitleTable(Base):
    __tablename__ = "subtitles"
    subtitle_id = Column(String, primary_key=True)
    source_id = Column(String, ForeignKey("sources.source_id"))
    language = Column(String)
    segments = Column(JSON)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now)

class SemanticFragmentTable(Base):
    __tablename__ = "semantic_fragments"
    id = Column(String, primary_key=True, index=True) # internal PK or SF_id
    fragment_id = Column(String, index=True)         # SF_XXXX
    source_id = Column(String, ForeignKey("sources.source_id"), index=True)
    start = Column(Float)
    end = Column(Float)
    semantic_json = Column(JSON)   # summary, topic, transcript_refs, evidence_refs
    structural_json = Column(JSON) # role, edit_value, duration
    continuity_json = Column(JSON) # topic_similarity, time_proximity, etc.
    confidence = Column(Float, default=1.0)
    fallback_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now)

class UserIntentTable(Base):
    __tablename__ = "user_intent"
    source_id = Column(String, primary_key=True, index=True)
    must_keep = Column(JSON, default=list)
    avoid = Column(JSON, default=list)
    tone = Column(String, nullable=True)
    target_length = Column(Float, nullable=True) # [STEP 5] 저장만 수행 (STEP 6 활용)
    priority_axis = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.datetime.now)

class ProposalTable(Base):
    __tablename__ = "proposals"
    proposal_id = Column(String, primary_key=True, index=True)
    source_id = Column(String, ForeignKey("sources.source_id"), index=True)
    mode = Column(String) # [STEP 6] A: Market Mode, B: User Mode
    sequence = Column(JSON) # [{sf_id, start, end, role, edit_value}, ...]
    duration = Column(Float)
    proposal_reason = Column(JSON) # [v3.2.1] Structured Reasoning
    confidence = Column(Float, default=1.0)
    fallback_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

class ExportInputTable(Base):
    __tablename__ = "export_input"
    export_id = Column(String, primary_key=True, index=True)
    source_id = Column(String, ForeignKey("sources.source_id"), index=True)
    proposal_id = Column(String, ForeignKey("proposals.proposal_id"), index=True)
    mode = Column(String)
    clips = Column(JSON) # [{fragment_id, start, end, duration, order}, ...]
    total_duration = Column(Float)
    status = Column(String, default="EXPORT_INPUT_READY")
    created_at = Column(DateTime, default=datetime.datetime.now)

class ExportResultTable(Base):
    __tablename__ = "export_results"
    id = Column(String, primary_key=True, index=True) # RND_xxx
    export_input_id = Column(String, ForeignKey("export_input.export_id"), index=True)
    proposal_id = Column(String, index=True)
    source_id = Column(String, index=True)
    output_path_internal = Column(String)
    output_url = Column(String)
    status = Column(String) # RENDER_SUCCESS / RENDER_FAILED
    file_size = Column(Float, nullable=True)
    duration = Column(Float, nullable=True)
    codec = Column(String, nullable=True)
    ffmpeg_command_summary = Column(String, nullable=True)
    ffmpeg_stderr = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
