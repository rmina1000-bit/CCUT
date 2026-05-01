import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from archive.manager import bams
from archive.models import SourceVideo
from archive.db_models import PublishedTable, ProgramTable, FragmentTable, SourceTable
from database import get_db

from engine.boundary_editor import pbe_engine
from engine.pbe_logic import pbe_ai, smart_pbe
from engine.voice_engine import voice_engine
from engine.vector_engine import vector_engine
from engine.search_engine import search_engine
from engine.vision_engine import vision_engine
from engine.llm_engine import llm_pd
from engine.generative_engine import generative_engine
from ai import get_registry
from engine.video_engine import VideoEngine

from auth.manager import user_manager
from report.generator import report_gen


# ═══════════════════════════════════════════════════════════════════
#   App / Paths / URL helpers
# ═══════════════════════════════════════════════════════════════════

BACKEND_DIR = Path(__file__).resolve().parent
STORAGE_DIR = Path(os.getenv("CCUT_STORAGE_DIR", str(BACKEND_DIR / "storage")))
UPLOAD_DIR = STORAGE_DIR / "uploads"
APP_BASE_URL = os.getenv("CCUT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Global Engine Initialization with STORAGE_DIR
video_engine = VideoEngine(storage_path=STORAGE_DIR)


def build_static_url(*parts: str) -> str:
    normalized = "/".join(str(p).strip("/\\") for p in parts if p)
    return f"{APP_BASE_URL}/static/{normalized}"


def build_upload_static_url(filename: str) -> str:
    return build_static_url("uploads", filename)


def build_export_static_url(filename: str) -> str:
    return build_static_url("exports", filename)


def build_dubbing_static_url(filename: str) -> str:
    return build_static_url("dubbing", filename)


app = FastAPI()

app.mount("/static", StaticFiles(directory=str(STORAGE_DIR)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════
#   업로드 / 조각 생성 상태 레지스트리
# ═══════════════════════════════════════════════════════════════════

# 업로드된 파일의 source_id → 내부 경로 매핑 (인메모리)
# { source_id: abs_path }
_upload_registry: dict[str, str] = {}

# 인메모리 진행 상태 레지스트리
# { source_id: { "progress": int, "status": str, "fragments": list } }
_fragment_job_registry: dict[str, dict] = {}

# 인메모리 배치 레지스트리
# { batch_id: { "status": str, "items": [...], "created_at": float } }
_batch_registry: dict[str, dict] = {}

# 진행 중인 program_id → batch_id 역방향 인덱스 (중복 요청 감지용)
_program_to_batch: dict[str, str] = {}


@app.get("/health")
async def health_check():
    return {"status": "OK", "timestamp": time.time()}


# ═══════════════════════════════════════════════════════════════════
#   CCUT: 영상 파일 업로드 엔드포인트
# ═══════════════════════════════════════════════════════════════════

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """
    [영상 업로드 v3.2.1]
    SHA-256 fingerprint를 생성하여 동일 영상 존재 시 기존 source_id를 반환합니다.
    """
    try:
        print(f"[DEBUG] /upload request received: filename={file.filename}")
        safe_name = Path(file.filename).name
        save_path = UPLOAD_DIR / safe_name

        with open(save_path, "wb") as buf:
            while chunk := await file.read(1024 * 1024):
                buf.write(chunk)

        abs_path = str(save_path.resolve())
        
        # [STEP 1] Fingerprint 생성 및 중복 확인
        from engine.video_engine import video_engine
        fingerprint = video_engine.generate_fingerprint(abs_path)
        
        existing = bams.get_source_by_hash(fingerprint)
        if existing:
            print(f"[UPLOAD] Fingerprint HIT: {fingerprint} -> source_id={existing.source_id}")
            return {
                "status": "SOURCE_REUSED",
                "file_name": safe_name,
                "source_id": existing.source_id,
                "hash_value": fingerprint,
                "cache_hit": True,
                "reused": True,
                "static_url": f"/static/uploads/{Path(existing.file_path).name}"
            }

        source_id = f"SRC_{uuid.uuid4().hex[:8].upper()}"
        _upload_registry[source_id] = abs_path

        # [STEP 1] 보완: 1차 업로드 시점에 DB에 hash_value를 등록해야 2차 업로드 시 hit 가능
        source_data = {
            "source_id": source_id,
            "file_path": abs_path,
            "title": safe_name,
            "duration": 0.0, # /generate-fragments 에서 업데이트됨
            "hash_value": fingerprint
        }
        bams.register_source(source_data)

        print(f"[UPLOAD] 신규 저장 및 DB 등록 완료: {abs_path} → source_id={source_id}")

        return {
            "status": "SOURCE_CREATED",
            "file_name": safe_name,
            "source_id": source_id,
            "hash_value": fingerprint,
            "cache_hit": False,
            "reused": False,
            "static_url": f"/static/uploads/{safe_name}",
        }
    except Exception as e:
        import traceback
        print(f"[CRITICAL] /upload error: {str(e)}")
        traceback.print_exc()
        return {"status": "ERROR", "message": str(e)}


# ═══════════════════════════════════════════════════════════════════
#   Background jobs
# ═══════════════════════════════════════════════════════════════════

def _background_whisper(source_id: str, video_path: str, fragments: list):
    print("[PIPELINE] Whisper pipeline STARTED")

    # Update registry: 시작 상태 기록
    if source_id in _fragment_job_registry:
        _fragment_job_registry[source_id]["status"] = "ANALYSIS_RUNNING"

    import importlib
    import engine.ai_engine
    importlib.reload(engine.ai_engine)
    
    from engine.ai_engine import (
        transcribe_full_then_split,
        calculate_hook_score_safe,
        classify_role,
        rebalance_roles,
        log_hook_distribution,
    )

    try:
        asr = get_registry().get_asr()
        if not asr._loaded:
            asr._ensure_loaded()
    except Exception as e:
        print(f"[ASR BG] Adapter 로드 실패: {e}")
        if source_id in _fragment_job_registry:
            _fragment_job_registry[source_id]["status"] = "FAILED"
            _fragment_job_registry[source_id]["error"] = str(e)
        return

    if not fragments:
        print(f"[ASR BG] {source_id} — 조각 없음")
        if source_id in _fragment_job_registry:
            _fragment_job_registry[source_id]["status"] = "FAILED"
            _fragment_job_registry[source_id]["error"] = "No fragments to analyze"
        return

    try:
        total_duration = max(float(f.get("end_time", 0)) for f in fragments)
        whisper_res    = asr.transcribe_fragments(video_path, fragments)
        
        transcripts  = whisper_res.get("fragment_transcripts", {})
        all_segments = whisper_res.get("all_segments", [])

        # [STEP 10-I.5.3] Store raw segments as evidence for Text-first Semantic Path
        for i, seg in enumerate(all_segments):
            bams.update_evidence(f"SPEECH_{i}_{source_id}", {
                "source_id": source_id,
                "worker_name": "whisper_segments",
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
                "confidence": 0.95
            })

        # 1. 조각별 intelligence 계산
        for frag in fragments:
            frag_id    = frag["fragment_id"]
            transcript = transcripts.get(frag_id, "")

            if not transcript:
                print(f"[WARN] transcript empty: {frag_id}")

            hook_score = calculate_hook_score_safe(frag, video_path, transcript)
            role       = classify_role(frag, total_duration, hook_score, transcript)

            frag["intelligence"] = {
                "hook_score": hook_score,
                "transcript": transcript,
                "role":       role,
            }

            print(f"[ASR BG] {frag_id} | hook={hook_score:.3f} | role={role} | transcript={transcript[:20]!r}")

        # 2. role 분포 보정 (Main 쏠림 방지)
        fragments = rebalance_roles(fragments)

        # 3. Evidence Board 및 DB 업데이트
        for frag in fragments:
            try:
                # [STEP 2] Evidence Board 필드 병합 (Text)
                bams.update_evidence(frag["fragment_id"], {
                    "source_id": source_id,
                    "worker_name": "whisper",
                    "start": frag["start_time"],
                    "end": frag["end_time"],
                    "text": frag["intelligence"]["transcript"],
                    "confidence": 0.9
                })
                bams.flush_evidence(frag["fragment_id"])

                # Legacy Intelligence 업데이트 (UI 연동용)
                bams.update_fragment_intelligence(
                    frag["fragment_id"],
                    frag["intelligence"]
                )
            except Exception as e:
                print(f"[ASR BG] {frag['fragment_id']} 저장 실패: {e}")

        # 4. 분포 로그
        log_hook_distribution(source_id, fragments)
        
        # [STEP 10-I.5.2] Semantic Analysis & Proposal Generation Trigger
        print(f"[PIPELINE] Triggering Semantic Analysis for {source_id}")
        from engine.semantic_engine import SemanticFragmentGenerator
        from engine.proposal_engine import ProposalEngine
        
        sem_gen = SemanticFragmentGenerator(bams)
        sem_gen.generate(source_id)
        
        prop_eng = ProposalEngine(bams)
        prop_eng.generate_proposals(source_id)
        
        # 완료 상태 기록
        if source_id in _fragment_job_registry:
            _fragment_job_registry[source_id]["status"] = "ANALYSIS_COMPLETE"
            _fragment_job_registry[source_id]["progress"] = 100
            
        print(f"[ASR BG] {source_id} 완료 (Semantic/Proposals Ready)")
    except Exception as e:
        print(f"[ASR BG] {source_id} 실행 오류: {e}")
        if source_id in _fragment_job_registry:
            _fragment_job_registry[source_id]["status"] = "FAILED"
            _fragment_job_registry[source_id]["error"] = str(e)




def _background_panorama(source_id: str, video_path: str, fragments: list):
    """
    백그라운드: PBE용 파노라마 썸네일 생성
    조각별 대표 프레임 1장씩 추출 → storage/panorama/{fragment_id}.jpg
    """
    from engine.video_engine import video_engine

    print(f"[PANORAMA BG] source_id={source_id} 파노라마 생성 시작")
    for frag in fragments:
        try:
            thumb_path = video_engine.extract_thumbnail(
                video_path,
                frag["start_time"],
                frag["fragment_id"],
            )
            bams.update_fragment_thumb(frag["fragment_id"], thumb_path)
            print(f"[PANORAMA BG] {frag['fragment_id']} 썸네일 생성 완료: {thumb_path}")
        except Exception as e:
            print(f"[PANORAMA BG] {frag['fragment_id']} 썸네일 실패: {e}")
    print(f"[PANORAMA BG] source_id={source_id} 파노라마 전체 완료")


def _background_signal_analysis(source_id: str, video_path: str, fragments: list):
    """
    [STEP 2] Signal Worker: 오디오 에너지(RMS) 분석 및 Evidence Board 업데이트
    """
    from engine.signal_processor import SignalProcessor
    print(f"[SIGNAL BG] Analysis STARTED for source_id={source_id}")
    
    sp = SignalProcessor(video_path)
    for frag in fragments:
        fid = frag["fragment_id"]
        start = frag["start_time"]
        dur = frag["duration"]
        
        try:
            # 1. 오디오 에너지(RMS) 추출
            energy = sp.get_rms_energy(start, dur)
            
            # 2. Evidence Board 필드 병합 (Field-level merge)
            bams.update_evidence(fid, {
                "source_id": source_id,
                "worker_name": "audio",
                "start": start,
                "end": start + dur,
                "audio_energy": energy,
                "confidence": 0.8
            })
            bams.flush_evidence(fid)
            
        except Exception as e:
            print(f"[SIGNAL BG] {fid} 분석 실패: {e}")
            
    print(f"[SIGNAL BG] Analysis COMPLETE for source_id={source_id}")


# ═══════════════════════════════════════════════════════════════════
#   CCUT 1.0.6: VIRTUAL CLIPPING — /generate-fragments  [N-01]
# ═══════════════════════════════════════════════════════════════════

@app.post("/generate-fragments")
async def generate_fragments(
    background_tasks: BackgroundTasks,
    source_id: str = "",
    video_path: str = "",
    db: Session = Depends(get_db),
):
    """
    [CCUT 1.0.6 Virtual Clipping — N-01]

    source_id (업로드 후 반환된 값) 또는 video_path(레거시) 중 하나로 호출.
    source_id 우선. video_path는 하위 호환용으로만 유지.
    """
    # from engine.video_engine import video_engine (Removing local import to use global)
    from engine.signal_processor import SignalProcessor

    resolved_path: Optional[str] = None

    if source_id:
        if source_id in _upload_registry:
            resolved_path = _upload_registry[source_id]
            print(f"[GENERATE-FRAGMENTS] source_id={source_id} (Registry) → {resolved_path}")
        else:
            src_entry = db.query(SourceTable).filter_by(source_id=source_id).first()
            if src_entry:
                resolved_path = src_entry.file_path
                _upload_registry[source_id] = resolved_path
                print(f"[GENERATE-FRAGMENTS] source_id={source_id} (DB) → {resolved_path}")

    if not resolved_path and video_path:
        resolved_path = video_path
        print(f"[GENERATE-FRAGMENTS] 레거시 video_path 사용: {resolved_path}")

    if not resolved_path:
        return {
            "status": "ERROR",
            "message": "source_id 또는 video_path가 필요합니다. 유효한 원본을 찾을 수 없습니다.",
        }

    print(f"[GENERATE-FRAGMENTS] 시작: {resolved_path}")

    meta = video_engine.get_metadata(resolved_path)
    total_duration = meta.get("duration", 30.0)

    # [STEP 1] Fingerprint 생성 및 소스 식별
    fingerprint = video_engine.generate_fingerprint(resolved_path)
    print(f"[GENERATE-FRAGMENTS] Fingerprint: {fingerprint}")

    is_new_source = False
    if not source_id:
        existing = bams.get_source_by_hash(fingerprint)
        if existing:
            print(f"[GENERATE-FRAGMENTS] Fingerprint Match! hit source_id={existing.source_id}")
            source_id = existing.source_id
        else:
            source_id = f"SRC_{uuid.uuid4().hex[:8].upper()}"
            is_new_source = True
    else:
        # source_id가 명시된 경우 (업로드 직후 흐름)
        # 이미 조각 데이터가 있다면 신규 분석 생략 (Dedupe)
        existing_frags = bams.get_fragments_by_source(source_id)
        is_new_source = False if existing_frags else True

    # [STEP 1] Proxy 생성 (분석용 저용량 영상)
    proxy_path = video_engine.create_proxy(resolved_path, source_id)

    # 신규 소스인 경우에만 분석 및 등록 수행
    if is_new_source:
        source_data = {
            "source_id": source_id,
            "file_path": resolved_path,
            "title": os.path.basename(resolved_path),
            "duration": total_duration,
            "fps": meta.get("fps", 30.0),
            "hash_value": fingerprint
        }
        bams.register_source(source_data)
        
        # [STEP 1] Dynamic Partitioning
        sp = SignalProcessor(proxy_path or resolved_path)
        try:
            smart_segments, triggers = sp.build_dynamic_segments(total_duration)
            analysis_mode = "DYNAMIC_PARTITION_V321"
        except Exception as e:
            print(f"[GENERATE-FRAGMENTS] 신호 전처리 실패: {e}")
            smart_segments = [{"index": 0, "start": 0, "end": total_duration, "duration": total_duration}]
            analysis_mode = "FALLBACK"

        fragments = []
        for seg in smart_segments:
            frag_id = f"VF{seg['index'] + 1}_{source_id}"
            fps = meta.get("fps", 30.0)
            start_frame = int(round(seg["start"] * fps))
            end_frame = int(round(seg["end"] * fps))

            frag_data = {
                "fragment_id": frag_id,
                "source_id": source_id,
                "start_time": seg["start"],
                "end_time": seg["end"],
                "start_frame": start_frame,
                "end_frame": end_frame,
                "duration": seg["duration"],
                "_proxy_video_path": proxy_path,
                "intelligence": {
                    "transcript": "", 
                    "hook_score": 0.5,
                    "scene_change": [t for t in triggers if seg["start"] <= t <= seg["end"]]
                },
                "status": "VIRTUAL"
            }
            fragments.append(frag_data)
        
        bams.archive_fragments(fragments)
        
        # [STEP 2] Initialize Evidence Board with Signal Triggers
        for frag in fragments:
            bams.update_evidence(frag["fragment_id"], {
                "source_id": source_id,
                "worker_name": "signal_processor",
                "start": frag["start_time"],
                "end": frag["end_time"],
                "scene_change": frag["intelligence"].get("scene_change", []),
                "confidence": 1.0
            })
            bams.flush_evidence(frag["fragment_id"])
            
        print(f"[GENERATE-FRAGMENTS] New Analysis Started: {source_id}")
    else:
        # [STEP 1] 캐시 히트: 기존 조각 재사용
        fragments = bams.get_fragments_by_source(source_id)
        analysis_mode = "FINGERPRINT_CACHE_HIT"
        print(f"[GENERATE-FRAGMENTS] Using Cached Analysis: {source_id}")

    _fragment_job_registry[source_id] = {
        "progress": 30, # L1 작업 완료 직후이므로 30% 정도로 표시
        "status": "FRAGMENT_READY",
        "source_id": source_id,
        "fragment_count": len(fragments),
        "analysis_mode": analysis_mode,
    }

    background_tasks.add_task(_background_whisper, source_id, resolved_path, fragments)
    background_tasks.add_task(_background_panorama, source_id, resolved_path, fragments)
    background_tasks.add_task(_background_signal_analysis, source_id, resolved_path, fragments)

    print(f"[GENERATE-FRAGMENTS] L1 완료. {len(fragments)}개 Virtual Fragment 즉시 반환.")

    safe_fragments = [
        {k: v for k, v in f.items() if k != "_internal_video_path"}
        for f in fragments
    ]

    return {
        "status": "L1_COMPLETE",
        "progress": 100,
        "source_id": source_id,
        "count": len(safe_fragments),
        "fragments": safe_fragments,
        "analysis_mode": analysis_mode,
        "bg_tasks": ["whisper_transcription", "panorama_generation"],
        "pipeline": "virtual_clipping_v1.0.6",
    }


@app.get("/generate-fragments/status/{source_id}")
async def get_fragment_analysis_status(source_id: str):
    """의미분석 진행 상태 조회 (Index.tsx polling용)"""
    job = _fragment_job_registry.get(source_id)
    if not job:
        return {"status": "NOT_FOUND", "source_id": source_id}
    return {
        "status": job.get("status", "PENDING"),
        "progress": job.get("progress", 0),
        "source_id": source_id,
        "error": job.get("error"),
    }

@app.get("/fragments/{source_id}")
async def get_fragments_by_source(source_id: str):
    """의미분석 완료 후 최신 intelligence가 포함된 조각 재조회"""
    # [STEP 6] Semantic Fragments 가 존재하면 우선 반환하여 Proposal 과 ID 를 맞춤
    fragments = bams.get_semantic_fragments(source_id)
    if not fragments:
        fragments = bams.get_fragments_by_source(source_id)
        
    return {
        "status": "SUCCESS",
        "source_id": source_id,
        "fragments": fragments
    }

@app.get("/evidence/{source_id}")
async def get_evidence_board(source_id: str):
    """[STEP 2] 소스별 Evidence Board 데이터 조회"""
    board = bams.get_evidence_board(source_id)
    return {
        "status": "SUCCESS",
        "source_id": source_id,
        "count": len(board),
        "coverage": bams.calculate_coverage(source_id), # [STEP 2]
        "evidence": board
    }

@app.get("/quick-scan/{source_id}")
async def get_quick_scan(source_id: str):
    """[STEP 3] Quick Scan 및 AI 가설 조회 (미응답 시 default 처리 보장)"""
    from engine.hypothesis_engine import hypothesis_engine
    
    # 1. DB에 저장된 캐시 확인
    cached = bams.get_quick_scan(source_id)
    
    # 2. 캐시가 없거나 실시간 업데이트가 필요한 경우 (Partial Evidence 등)
    # 10% 이상 조건은 엔진 내부에서 체크함
    result = hypothesis_engine.generate_quick_scan(source_id)
    
    if result:
        return result
    elif cached:
        return cached

    return {
        "status": "PENDING",
        "source_id": source_id,
        "msg": "Evidence Board 분석 진행 중... (10% 미확보)"
    }

@app.post("/semantic-fragments/{source_id}")
async def generate_semantic_fragments(source_id: str):
    """[STEP 4] Evidence Board 기반 Semantic Fragment 생성"""
    from engine.semantic_engine import SemanticFragmentGenerator
    gen = SemanticFragmentGenerator(bams)
    fragments = gen.generate(source_id)
    
    # Role 분산 통계 계산
    role_dist = {}
    for f in fragments:
        role = f["structural"].get("role", "context")
        role_dist[role] = role_dist.get(role, 0) + 1
        
    return {
        "status": "SEMANTIC_FRAGMENT_READY",
        "source_id": source_id,
        "fragment_count": len(fragments),
        "role_distribution": role_dist,
        "fragments": fragments
    }

@app.get("/semantic-fragments/{source_id}")
async def get_semantic_fragments(source_id: str):
    """[STEP 4] 저장된 Semantic Fragments 조회 (v3.2.1 보완)"""
    fragments = bams.get_semantic_fragments(source_id)
    
    role_dist = {}
    for f in fragments:
        role = f.get("structural", {}).get("role", "context")
        role_dist[role] = role_dist.get(role, 0) + 1
        
    status = "SEMANTIC_FRAGMENT_READY" if fragments else "NOT_FOUND"
    
    return {
        "status": status,
        "source_id": source_id,
        "fragment_count": len(fragments),
        "role_distribution": role_dist,
        "fragments": fragments
    }

# ═══════════════════════════════════════════════════════════════════
#   [STEP 5] User Intent Reflections
# ═══════════════════════════════════════════════════════════════════

@app.post("/user-intent/{source_id}")
async def post_user_intent(source_id: str, intent: dict):
    """
    [STEP 5] User Intent 반영 및 Rescoring 트리거
    must_keep, avoid, target_length, priority_axis 등을 반영하여 
    기존 Semantic Fragments의 edit_value를 재계산함.
    """
    # 1. Intent 영구 저장
    bams.save_user_intent(source_id, intent)
    
    # 2. Rescoring 엔진 가동 (Dynamic Import to avoid circular refs if any)
    from engine.semantic_engine import SemanticFragmentGenerator
    generator = SemanticFragmentGenerator(bams)
    rescored_fragments = generator.rescore_all_fragments(source_id, intent)
    
    role_dist = {}
    for f in rescored_fragments:
        role = f.get("structural", {}).get("role", "context")
        role_dist[role] = role_dist.get(role, 0) + 1

    return {
        "status": "USER_INTENT_REFLECTED",
        "source_id": source_id,
        "fragment_count": len(rescored_fragments),
        "role_distribution": role_dist
    }

@app.get("/user-intent/{source_id}")
async def get_user_intent(source_id: str):
    """[STEP 5] 저장된 User Intent 조회"""
    intent = bams.get_user_intent(source_id)
    if not intent:
        return {"status": "NOT_FOUND", "source_id": source_id}
    return intent

# ═══════════════════════════════════════════════════════════════════
#   [STEP 6] Proposal Engine Integration
# ═══════════════════════════════════════════════════════════════════

@app.post("/proposals/{source_id}")
async def post_generate_proposals(source_id: str):
    """
    [STEP 6] Proposal 생성 트리거
    Semantic Fragments를 조합하여 A(Market)/B(User) 두 가지 제안 생성.
    """
    from engine.proposal_engine import ProposalEngine
    engine = ProposalEngine(bams)
    proposals = engine.generate_proposals(source_id)
    
    return {
        "status": "PROPOSAL_READY",
        "source_id": source_id,
        "proposal_count": len(proposals),
        "proposals": proposals
    }

@app.get("/proposals/{source_id}")
async def get_proposals_api(source_id: str):
    """[STEP 6] 저장된 제안 조회"""
    proposals = bams.get_proposals(source_id)
    return {
        "status": "SUCCESS",
        "source_id": source_id,
        "count": len(proposals),
        "proposals": proposals
    }

# ═══════════════════════════════════════════════════════════════════
#   [STEP 7] Export Input Generation
# ═══════════════════════════════════════════════════════════════════

@app.post("/export-input/{proposal_id}")
async def post_export_input(proposal_id: str, payload: dict = None):
    """
    [STEP 7] Proposal -> Export Input 변환
    해당 proposal_id의 시퀀스를 렌더링용 클립 리스트로 전환합니다.
    payload에 'clips'가 있으면 이를 직접 사용하여 Resolver 결과를 반영합니다.
    """
    from engine.export_engine import ExportEngine
    engine = ExportEngine(bams)
    
    custom_clips = payload.get("clips") if payload else None
    export_input = engine.create_export_input(proposal_id, custom_clips=custom_clips)
    
    if not export_input:
        return {"status": "NOT_FOUND", "proposal_id": proposal_id}
        
    return export_input

@app.get("/export-input/{source_id}")
async def get_export_input_source(source_id: str):
    """[STEP 7] 소스별 Export Input 목록 조회"""
    data = bams.get_export_input_by_source(source_id)
    return {
        "status": "SUCCESS", 
        "source_id": source_id, 
        "export_inputs": data
    }

@app.get("/export-input/by-proposal/{proposal_id}")
async def get_export_input_proposal(proposal_id: str):
    """[STEP 7] 제안별 Export Input 조회"""
    data = bams.get_export_input_by_proposal(proposal_id)
    if not data:
        return {"status": "NOT_FOUND", "proposal_id": proposal_id}
    return data

# ═══════════════════════════════════════════════════════════════════
#   [STEP 8] Render Engine API
# ═══════════════════════════════════════════════════════════════════

@app.post("/render/{export_input_id}")
async def post_render(export_input_id: str):
    """
    [STEP 8] Render 실행
    ExportInput ID를 받아 실제 mp4 영상을 생성합니다.
    """
    from engine.render_engine import render_engine
    result = render_engine.render_from_export_input(export_input_id)
    return result

@app.get("/render-result/{export_input_id}")
async def get_render_result(export_input_id: str):
    """[STEP 8] Render 결과 조회"""
    result = bams.get_render_result(export_input_id)
    if not result:
        return {"status": "NOT_FOUND", "export_input_id": export_input_id}
    return result

@app.get("/generate-fragments/status/{source_id}")
async def get_fragment_status_legacy(source_id: str):
    # 하위 호환성 유지용 (필요 시)
    return await get_fragment_analysis_status(source_id)
    """
    [Virtual Clipping 폴링 엔드포인트]
    프론트에서 Whisper / 파노라마 완료 여부를 주기적으로 확인할 때 사용.
    """
    job = _fragment_job_registry.get(source_id)
    if not job:
        return {"status": "NOT_FOUND", "source_id": source_id}
    return job


# ═══════════════════════════════════════════════════════════════════
#   CCUT 1.0.6: BATCH EXPORT API  [Phase 2.5]
# ═══════════════════════════════════════════════════════════════════

def _run_batch_export(batch_id: str, program_ids: list[str], db_session_factory=None):
    """
    백그라운드: 배치 내 각 program_id를 순차 렌더링.
    단건 /export/{program_id} 와 독립 실행
    """
    batch = _batch_registry.get(batch_id)
    if not batch:
        return

    print(f"[BATCH] {batch_id} 시작 — {len(program_ids)}개 프로그램")
    batch["status"] = "RUNNING"

    from database import SessionLocal
    db = SessionLocal()

    try:
        for item in batch["items"]:
            pid = item["program_id"]
            if pid not in program_ids:
                continue

            item["status"] = "RENDERING"
            print(f"[BATCH] {batch_id} → {pid} 렌더링 시작")

            try:
                program = db.query(ProgramTable).filter_by(program_id=pid).first()
                if not program:
                    item["status"] = "FAILED"
                    item["error"] = "프로그램을 찾을 수 없습니다"
                    print(f"[BATCH] {pid} FAILED: 프로그램 없음")
                    continue

                program.status = "RENDERING"
                db.commit()

                final_path = export_engine.render_virtual_program(pid)
                if not final_path:
                    print(f"[BATCH] {pid} virtual 렌더 실패 → render_program 폴백 시도")
                    final_path = export_engine.render_program(pid)

                if not final_path:
                    item["status"] = "FAILED"
                    item["error"] = "render_virtual_program 및 render_program 모두 실패"
                    print(f"[BATCH] {pid} FAILED: 렌더링 실패")
                    continue

                existing = db.query(PublishedTable).filter_by(program_id=pid).first()
                if existing:
                    existing.final_video_path = final_path
                    existing.platform = "PENDING"
                    existing.title = f"{program.name} [재렌더링]"
                else:
                    new_pub = PublishedTable(
                        publish_id=f"PUB_{uuid.uuid4().hex[:6].upper()}",
                        program_id=pid,
                        platform="PENDING",
                        final_video_path=final_path,
                        title=f"{program.name} 배치 렌더",
                    )
                    db.add(new_pub)
                db.commit()

                item["status"] = "DONE"
                item["download_url"] = build_export_static_url(os.path.basename(final_path))
                print(f"[BATCH] {pid} DONE → {final_path}")

            except Exception as e:
                item["status"] = "FAILED"
                item["error"] = str(e)
                print(f"[BATCH] {pid} FAILED: {e}")

    finally:
        db.close()

    statuses = [item["status"] for item in batch["items"]]
    if all(s == "DONE" for s in statuses):
        batch["status"] = "FINISHED"
    elif all(s in ("DONE", "FAILED") for s in statuses):
        batch["status"] = "FINISHED_WITH_ERRORS"
    else:
        batch["status"] = "FINISHED"

    for pid in program_ids:
        _program_to_batch.pop(pid, None)

    print(f"[BATCH] {batch_id} 완료 — 최종 상태: {batch['status']}")


class BatchExportRequest(BaseModel):
    program_ids: list[str]


@app.post("/export/batch")
async def export_batch(
    req: BatchExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    [Phase 2.5] 여러 프로그램을 한 번에 배치 렌더링 요청.
    """
    if not req.program_ids:
        return {"status": "ERROR", "message": "program_ids가 비어있습니다"}

    for pid in req.program_ids:
        existing_batch_id = _program_to_batch.get(pid)
        if existing_batch_id:
            existing_batch = _batch_registry.get(existing_batch_id, {})
            if existing_batch.get("status") in ("PENDING", "RUNNING"):
                print(f"[BATCH] 중복 요청 감지: {pid} → 기존 batch_id={existing_batch_id} 반환")
                return {
                    "status": "DUPLICATE",
                    "batch_id": existing_batch_id,
                    "message": f"이미 진행 중인 배치입니다. batch_id={existing_batch_id}",
                }

    batch_id = f"BATCH_{uuid.uuid4().hex[:8].upper()}"
    items = [
        {
            "program_id": pid,
            "status": "PENDING",
            "download_url": None,
            "error": None,
        }
        for pid in req.program_ids
    ]
    _batch_registry[batch_id] = {
        "batch_id": batch_id,
        "status": "PENDING",
        "items": items,
        "created_at": time.time(),
    }

    for pid in req.program_ids:
        _program_to_batch[pid] = batch_id

    background_tasks.add_task(_run_batch_export, batch_id, req.program_ids, None)

    print(f"[BATCH] 새 배치 생성: {batch_id} — {len(req.program_ids)}개 프로그램")
    return {
        "status": "ACCEPTED",
        "batch_id": batch_id,
        "program_ids": req.program_ids,
        "item_count": len(req.program_ids),
        "poll_url": f"{APP_BASE_URL}/export/batch/{batch_id}",
    }


@app.get("/export/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """
    [Phase 2.5] 배치 진행 상태 폴링.
    """
    batch = _batch_registry.get(batch_id)
    if not batch:
        return {"status": "NOT_FOUND", "batch_id": batch_id}

    total = len(batch["items"])
    done = sum(1 for i in batch["items"] if i["status"] == "DONE")
    failed = sum(1 for i in batch["items"] if i["status"] == "FAILED")

    return {
        "batch_id": batch_id,
        "status": batch["status"],
        "progress": f"{done + failed}/{total}",
        "done": done,
        "failed": failed,
        "total": total,
        "items": batch["items"],
        "created_at": batch["created_at"],
    }


@app.post("/export/batch/{batch_id}/retry")
async def retry_batch_failed(
    batch_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    [Phase 2.5 — 검증 항목 5] 실패 항목 재시도
    """
    batch = _batch_registry.get(batch_id)
    if not batch:
        return {"status": "NOT_FOUND", "batch_id": batch_id}

    failed_items = [i for i in batch["items"] if i["status"] == "FAILED"]
    if not failed_items:
        return {
            "status": "NO_FAILED_ITEMS",
            "batch_id": batch_id,
            "message": "재시도할 실패 항목이 없습니다",
        }

    for item in failed_items:
        item["status"] = "PENDING"
        item["error"] = None

    batch["status"] = "RUNNING"
    retry_ids = [i["program_id"] for i in failed_items]

    background_tasks.add_task(_run_batch_export, batch_id, retry_ids, None)

    print(f"[BATCH RETRY] {batch_id} — {len(retry_ids)}개 항목 재시도")
    return {
        "status": "RETRY_ACCEPTED",
        "batch_id": batch_id,
        "retry_count": len(retry_ids),
        "retry_ids": retry_ids,
    }


# ═══════════════════════════════════════════════════════
#   기타 엔드포인트
# ═══════════════════════════════════════════════════════

@app.post("/dubbing/global")
async def global_dubbing_simple(
    source_language: str,
    target_language: str,
    text: str,
    voice_id: str = "ko-KR-Standard-A",
):
    """[1.0.6 글로벌 더빙] 텍스트 번역 + 더빙 오디오 생성"""
    try:
        if source_language != target_language:
            translated_text = generative_engine.translate_text(text, source_language, target_language)
        else:
            translated_text = text

        audio_path = generative_engine.generate_dubbing(translated_text, target_language, voice_id)
        return {
            "status": "SUCCESS",
            "translated_text": translated_text,
            "audio_path": audio_path,
            "download_url": build_dubbing_static_url(os.path.basename(audio_path)),
        }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


current_theme = {
    "season": "겨울",
    "primary": "#3B82F6",
    "bg": "#050505",
}


@app.get("/theme")
async def get_theme():
    return current_theme


@app.post("/theme/update")
async def update_theme(season: str):
    themes = {
        "봄": {"primary": "#EC4899", "bg": "#0D080A"},
        "여름": {"primary": "#06B6D4", "bg": "#050A0B"},
        "가을": {"primary": "#F97316", "bg": "#0B0905"},
        "겨울": {"primary": "#3B82F6", "bg": "#050505"},
    }
    global current_theme
    current_theme = {"season": season, **themes.get(season, themes["겨울"])}
    return current_theme


from auth.sns_api import sns_publisher


@app.post("/export/{program_id}")
async def export_program(program_id: str, platform: str = "YOUTUBE", db: Session = Depends(get_db)):
    """[4단계: PRODUCTION RENDER] Virtual-to-Physical 렌더링 수행"""
    print(f"[{program_id}] 렌더링 요청 수신 (Platform: {platform})")

    try:
        final_path = export_engine.render_virtual_program(program_id)
    except Exception as e:
        return {"status": "ERROR", "message": f"렌더링 엔진 오류: {str(e)}"}

    if not final_path:
        return {"status": "ERROR", "message": "렌더링 가능한 실제 조각 파일이 없습니다."}

    return {
        "status": "SUCCESS",
        "download_url": build_export_static_url(os.path.basename(final_path)),
        "ai_msg": "렌더링이 완료되었습니다.",
    }


@app.post("/publish/{publish_id}")
async def publish_to_sns(publish_id: str, db: Session = Depends(get_db)):
    """[5단계: REAL TRANSMISSION] 최종본을 YouTube에 실제 송출"""
    asset = db.query(PublishedTable).filter_by(publish_id=publish_id).first()
    if not asset:
        return {"status": "ERROR", "message": "발행할 자산을 찾을 수 없습니다."}
    if not os.path.exists(asset.final_video_path):
        return {"status": "ERROR", "message": f"렌더링된 파일을 찾을 수 없습니다: {asset.final_video_path}"}

    print(f"[BAMS TRANSMISSION] '{asset.title}' 세계 송출 시작... ({asset.final_video_path})")
    result = sns_publisher.publish(
        video_path=asset.final_video_path,
        title=asset.title,
        description="CCUT 1.0.6 AI PD가 자동 편집 및 발행한 영상입니다.",
        credentials_dict=None,
    )
    asset.platform = "YouTube"
    asset.title = f"{asset.title} [YT:{result['video_id']}]"
    db.commit()

    return {
        "status": "SUCCESS",
        "platform": "YouTube",
        "video_id": result["video_id"],
        "url": result["url"],
        "message": f"'{asset.title}' — 전 세계 송출 완료!",
    }


@app.post("/export/final")
async def run_final_broadcast(project_id: str = "DEFAULT", db: Session = Depends(get_db)):
    """[CCUT 1.0.6 최종 송출] 편집본을 실제 .mp4 파일로 렌더링하고 DB 아카이브에 기록"""
    print(f"[{project_id}] 최종 송출본 렌더링 시작: {project_id}")

    final_path = export_engine.render_virtual_program(project_id)

    if not final_path:
        return {"status": "ERROR", "message": "렌더링할 시퀀스가 비어있거나 분석이 완료되지 않았습니다."}

    new_publish = PublishedTable(
        publish_id=f"PUB_{uuid.uuid4().hex[:6].upper()}",
        program_id=project_id,
        platform="LOCAL",
        final_video_path=final_path,
        title=f"최종 송출본 ({project_id})",
    )
    db.add(new_publish)
    db.commit()

    return {
        "status": "ON-AIR SUCCESS",
        "file_url": build_export_static_url(os.path.basename(final_path)),
        "ai_msg": "국장님, 렌더링 작업이 완료되었습니다! 파일을 확인해 보세요.",
    }


class SaveEditRequest(BaseModel):
    fragments: list[dict]
    timestamp: int


@app.post("/save_edit")
async def save_edit(req: SaveEditRequest, db: Session = Depends(get_db)):
    """[PBE Persistence] PBE 편집 결과를 DB에 영구 저장합니다."""
    print(f"[SAVE_EDIT] {len(req.fragments)}개 조각 저장 요청 수신 (timestamp={req.timestamp})")
    try:
        bams.archive_fragments(req.fragments)
        return {"status": "SUCCESS", "message": f"{len(req.fragments)} fragments saved."}
    except Exception as e:
        print(f"[SAVE_EDIT] 실패: {e}")
        return {"status": "ERROR", "message": str(e)}


# ── PBE 라우트 ──────────────────────────────────────────────────────

class ContextRequest(BaseModel):
    left_frag_id: str
    right_frag_id: str


@app.post("/pbe/context")
async def get_pbe_context(req: ContextRequest):
    return pbe_engine.get_seam_context(req.left_frag_id, req.right_frag_id)


class BoundaryChangeRequest(BaseModel):
    seam_id: str
    new_split_point: float
    user_msg: str


@app.post("/pbe/apply")
async def apply_pbe_change(req: BoundaryChangeRequest):
    parts = req.seam_id.split("_")
    left_id = parts[1] if len(parts) > 1 else ""
    right_id = parts[2] if len(parts) > 2 else ""
    return pbe_ai.commit_pbe_change(left_id, right_id, req.new_split_point, req.user_msg)


class SmartSuggestRequest(BaseModel):
    left_frag: dict
    right_frag: dict


@app.post("/pbe/suggest")
async def smart_pbe_suggest(req: SmartSuggestRequest):
    """[1.0.6 SMART PBE] 최적 Seam 위치 + 이유 + 신뢰도 반환"""
    suggestion = smart_pbe.suggest_boundary(
        left_frag=req.left_frag,
        right_frag=req.right_frag,
    )
    return suggestion


class PBEChatRequest(BaseModel):
    message: str
    seam_id: str = ""


@app.post("/pbe/analyze")
async def analyze_pbe_chat(req: PBEChatRequest):
    return pbe_ai.process_chat_trim(req.seam_id, req.message)


# ── 프로그램 생성 라우트 (/programs) ───────────────────────────────

class ProgramCreateRequest(BaseModel):
    program_id: str
    name: str
    fragments_sequence: list[str]
    source_id: str = ""


@app.post("/programs")
async def create_program(req: ProgramCreateRequest, db: Session = Depends(get_db)):
    """
    [A/B 선택 → 프로그램 생성]
    프론트엔드에서 선택한 편집안(A 또는 B)의 조각 시퀀스를 DB에 저장.
    이후 /export/{program_id} 로 렌더링 요청.
    """
    existing = db.query(ProgramTable).filter_by(program_id=req.program_id).first()
    if existing:
        existing.fragments_sequence = req.fragments_sequence
        existing.name = req.name
        existing.status = "PENDING"
        db.commit()
        return {"status": "UPDATED", "program_id": req.program_id}

    new_pg = ProgramTable(
        program_id=req.program_id,
        name=req.name,
        fragments_sequence=req.fragments_sequence,
        status="PENDING",
    )
    db.add(new_pg)
    db.commit()
    return {"status": "SUCCESS", "program_id": req.program_id}


# ── 유저 라우트 ────────────────────────────────────────────────────

@app.get("/user/status")
async def get_user_status():
    return user_manager.current_user


@app.post("/user/login")
async def login():
    return user_manager.login_with_google()


# ── 레거시 /analyze 엔드포인트 (호환성 유지) ─────────────────────────

from engine.video_engine import video_engine
from engine.ai_engine import ai_engine
from engine.ai_pipeline import ai_pipeline


@app.post("/analyze")
async def analyze_video(video_path: str | None = None):
    """
    [레거시] CCUT 1.0.5 통합 분석. 물리 클립 생성 방식.
    신규 작업은 /generate-fragments 를 사용하세요.
    """
    print(f"[ANALYZE LEGACY] 파이프라인 가동: {video_path}")
    meta = video_engine.get_metadata(video_path)
    source = SourceVideo(
        source_id=f"SRC_{uuid.uuid4().hex[:4]}",
        file_path=video_path,
        title=os.path.basename(video_path),
        duration=meta["duration"],
        hash_value="pipeline_v1.0.5",
    )
    bams.register_source(source)

    fragments, analysis_mode = await ai_pipeline.process_video(source)
    bams.archive_fragments(fragments)

    for f in fragments:
        vector_engine.upsert_fragment(
            fragment_id=f["fragment_id"],
            transcript=f["intelligence"].get("transcript", ""),
            metadata={
                "start": f["start"],
                "hook_score": f["intelligence"].get("hook_score", 0.5),
            },
        )

    sorted_frags = sorted(
        fragments,
        key=lambda x: x["intelligence"].get("hook_score", 0),
        reverse=True,
    )
    top_hooks = [f["id"] for f in sorted_frags[:3]]
    top_score = (
        int(sorted_frags[0]["intelligence"].get("hook_score", 0.5) * 100)
        if sorted_frags
        else 50
    )

    proposals = {
        "A": {
            "title": "AI 훅 스나이퍼",
            "desc": f"Hook 점수 상위 {min(3, len(fragments))}개 조각.",
            "score": f"{top_score}%",
            "key_fragments": top_hooks,
        },
        "B": {
            "title": "서사 브이로그",
            "desc": "시간 순서 기반 자연스러운 흐름.",
            "score": "88%",
            "key_fragments": [f["id"] for f in fragments],
        },
    }

    return {
        "count": len(fragments),
        "source": source.dict(),
        "fragments": fragments,
        "proposals": proposals,
        "analysis_mode": analysis_mode,
        "pipeline": "ai_pipeline_v1.0.5",
    }


# ── 스마트 분석 /smart-analyze (레거시, 물리 클립 방식) ──────────────

@app.post("/smart-analyze")
async def smart_analyze_video(video_path: str | None = None):
    """
    [레거시] 1.0.5 스마트 파이프라인. 물리 클립 생성 방식.
    신규 작업은 /generate-fragments 를 사용하세요.
    """
    from engine.signal_processor import SignalProcessor

    print(f"[SMART ANALYZE LEGACY] 시작: {video_path}")
    meta = video_engine.get_metadata(video_path)
    total_duration = meta.get("duration", 30.0)

    source = SourceVideo(
        source_id=f"SRC_{uuid.uuid4().hex[:4]}",
        file_path=video_path,
        title=os.path.basename(video_path),
        duration=total_duration,
        hash_value="smart_analyzed",
    )
    bams.register_source(source)

    sp = SignalProcessor(video_path)
    try:
        smart_segments = sp.build_fragment_segments(total_duration)
        analysis_mode = "SIGNAL_BASED"
    except Exception as e:
        print(f"[SMART ANALYZE] 신호 전처리 실패: {e} → 고정 5초 폴백")
        smart_segments = [
            {"index": i, "start": i * 5.0, "end": (i + 1) * 5.0, "duration": 5.0}
            for i in range(min(6, int(total_duration // 5)))
        ]
        analysis_mode = "FIXED_FALLBACK"

    fragments = []
    for seg in smart_segments:
        frag_id = f"SF{seg['index'] + 1}_{source.source_id}"
        thumb_path = video_engine.extract_thumbnail(video_path, seg["start"], frag_id)
        clip_path = video_engine.create_fragment_clip(video_path, seg["start"], seg["duration"], frag_id)
        transcript = ai_engine.transcribe_fragment(clip_path)
        intelligence = ai_engine.analyze_intelligence(transcript)

        frag_data = {
            "id": frag_id,
            "fragment_id": frag_id,
            "source_id": source.source_id,
            "start": seg["start"],
            "start_time": seg["start"],
            "end_time": seg["end"],
            "duration": seg["duration"],
            "thumb": thumb_path,
            "clip": clip_path,
            "intelligence": intelligence,
            "analysis_mode": analysis_mode,
            "status": "AVAILABLE",
        }
        fragments.append(frag_data)

        vector_engine.upsert_fragment(
            fragment_id=frag_id,
            transcript=transcript,
            metadata={
                "start": seg["start"],
                "end": seg["end"],
                "hook_score": intelligence.get("hook_score", 0.5),
            },
        )

    bams.archive_fragments(fragments)

    sorted_by_hook = sorted(
        fragments,
        key=lambda x: x["intelligence"].get("hook_score", 0),
        reverse=True,
    )
    top_hook_frags = [f["id"] for f in sorted_by_hook[:3]]

    proposals = {
        "A": {
            "title": "AI 훅 스나이퍼",
            "desc": f"Hook 점수 상위 {len(top_hook_frags)}개 조각.",
            "score": f"{int(sorted_by_hook[0]['intelligence'].get('hook_score', 0.5) * 100)}%",
            "key_fragments": top_hook_frags,
        },
        "B": {
            "title": "서사 브이로그",
            "desc": "시간 순서 기반의 자연스러운 흐름.",
            "score": "88%",
            "key_fragments": [f["id"] for f in fragments],
        },
    }

    return {
        "count": len(fragments),
        "source": source.dict(),
        "fragments": fragments,
        "proposals": proposals,
        "analysis_mode": analysis_mode,
        "smart_split_count": len(smart_segments),
        "vector_indexed": vector_engine.is_ready(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)