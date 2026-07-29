from sqlalchemy import Column, String, Float, DateTime, JSON, ForeignKey, Boolean, Text, Integer, LargeBinary
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
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    # [서사층 §2.2] 촬영일 — 원본은 '업로드된 순서'가 아니라 '살아진 날'에 속한다
    shot_date = Column(String, nullable=True)

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
    # [B-3a] 프로젝트 작업상태 영속 (전부 nullable, 레거시 보존)
    active_mode = Column(String, nullable=True)
    chat_state = Column(Text, nullable=True)
    reserve_state = Column(Text, nullable=True)
    ui_state = Column(Text, nullable=True)
    schema_version = Column(Integer, nullable=True)
    # [SOFT-DELETE] 삭제는 즉시 제거가 아니라 30일 보관 후 자동 완전삭제.
    # deleted_at IS NULL = 활성. 값 있음 = 휴지통(복원 가능).
    deleted_at = Column(DateTime, nullable=True)

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
    program_id = Column(String, nullable=True)  # [B-3a] 프로젝트 종속. 레거시=null. PK는 source_id 단일 유지

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
    program_id = Column(String, nullable=True)  # [B-3a] 신규 프로젝트 제안. 레거시=null
    # [PROPOSAL-AXIS-01 1-1] proposal = f(승인 스냅샷, 기법팩)
    #   story_approval_id : 이 제안이 파생된 승인(story_approval.approval_id). 조각·순서의 출처.
    #   technique_id      : A/B가 갈리는 유일한 축.
    #     [LAB-19] A=punch_in / B=word_boundary_snap(CCUT_TECHNIQUE_WORD_SNAP ON) 또는 as_is(OFF).
    #     게이트가 꺼져 있을 때만 A == B 가 정상이다 — 구판 주석의 'as_is 하나뿐' 전제는 끝났다.
    story_approval_id = Column(Integer, nullable=True)
    technique_id = Column(String, nullable=True)

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
    program_id = Column(String, nullable=True, index=True)
    program_title = Column(String, nullable=True)
    # [EXPORT-NAME-SNAPSHOT] 렌더 시점 이름 스냅샷 — proposal_id 조인이 아니라
    # 여기 박힌 값이 진실원. 제안 재생성으로 옛 proposal_id가 사라져도 불변.
    display_name = Column(String, nullable=True)
    output_path_internal = Column(String)
    output_url = Column(String)
    status = Column(String) # RENDER_SUCCESS / RENDER_FAILED
    file_size = Column(Float, nullable=True)
    duration = Column(Float, nullable=True)
    codec = Column(String, nullable=True)
    ffmpeg_command_summary = Column(String, nullable=True)
    ffmpeg_stderr = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

class EditOverlayTable(Base):
    __tablename__ = "edit_overlay"
    overlay_id = Column(String, primary_key=True, index=True)
    source_id = Column(String, index=True)
    fragment_id = Column(String, index=True)
    effective_start_sec = Column(Float)
    effective_end_sec = Column(Float)
    excluded = Column(Boolean, default=False, nullable=False)
    edit_type = Column(String, index=True)
    root_fragment_id = Column(String, index=True)
    parent_fragment_id = Column(String, nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now)
    program_id = Column(String, nullable=True)  # [B-3a] 프로젝트별 편집 분리. 레거시=null

class ProjectSourceTable(Base):
    __tablename__ = "project_sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    program_id = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    display_order = Column(Integer, nullable=True)
    added_at = Column(String, nullable=True)


class FragmentIndexTable(Base):
    """[FRAGMENT-SEARCH] 검색 가능한 조각 자산 인덱스.
    자연어 검색("영국 비 중년 아저씨")의 데이터 기반.
    - visual_desc: Qwen3-VL 키프레임 장면 설명 (없으면 메타 기반 폴백)
    - transcript: ASR 전사 텍스트
    - search_text: FTS5/임베딩 입력용 통합 텍스트
    - embedding: sentence-transformers float32 벡터 (numpy.tobytes())
    - is_curated: 사용자가 제안에서 선택/내보낸 조각 = 진짜 자산
    """
    __tablename__ = "fragment_index"
    fragment_id = Column(String, primary_key=True, index=True)
    source_id = Column(String, ForeignKey("sources.source_id"), index=True)
    start = Column(Float)
    end = Column(Float)
    duration = Column(Float)
    role = Column(String, nullable=True, index=True)
    edit_value = Column(Float, default=0.0, index=True)
    hook_score = Column(Float, default=0.0)
    motion_score = Column(Float, default=0.0)
    # 의미 텍스트
    visual_desc = Column(Text, nullable=True)      # Qwen VL 장면 설명
    transcript = Column(Text, nullable=True)       # ASR 전사
    scene_type = Column(String, nullable=True, index=True)
    main_subjects = Column(JSON, default=list)     # ["person", "elderly", ...]
    search_text = Column(Text, nullable=True)      # 통합 검색 텍스트
    # 벡터
    embedding = Column(LargeBinary, nullable=True) # float32 numpy bytes
    embedding_model = Column(String, nullable=True)
    embedding_dim = Column(Integer, nullable=True)
    # 자산성
    is_curated = Column(Boolean, default=False, index=True)
    usage_count = Column(Integer, default=0)
    keyframe = Column(String, nullable=True)       # 대표 썸네일 경로
    # 인덱싱 메타
    desc_source = Column(String, nullable=True)    # qwen_vl / meta_fallback / transcript
    indexed_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now)
