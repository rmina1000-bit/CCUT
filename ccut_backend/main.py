import os
import time
import uuid
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import FastAPI, Depends, BackgroundTasks, UploadFile, File, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from archive.manager import bams
from archive.models import SourceVideo
from archive.db_models import PublishedTable, ProgramTable, FragmentTable, SourceTable, ProposalTable
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
from engine.story_template_resolver import StoryTemplateResolver
from engine.proposal_guards import response_level_sequence_guard

from auth.manager import user_manager
from report.generator import report_gen


# ═══════════════════════════════════════════════════════════════════
#   App / Paths / URL helpers
# ═══════════════════════════════════════════════════════════════════

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
STORAGE_DIR = Path(os.getenv("CCUT_STORAGE_DIR", str(PROJECT_ROOT / "storage"))).resolve()
UPLOAD_DIR = STORAGE_DIR / "uploads"
APP_BASE_URL = os.getenv("CCUT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Global Engine Initialization with STORAGE_DIR
video_engine = VideoEngine(storage_path=STORAGE_DIR)
template_resolver = StoryTemplateResolver()


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

def get_video_range_response(file_path: Path, request: Request):
    from fastapi.responses import StreamingResponse, FileResponse
    from fastapi import HTTPException
    
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")
    
    ext = file_path.suffix.lower()
    content_type = "video/mp4"
    if ext == ".webm":
        content_type = "video/webm"
    elif ext in (".mov", ".qt"):
        content_type = "video/quicktime"
    elif ext == ".ogg":
        content_type = "video/ogg"

    if not range_header:
        return FileResponse(file_path, media_type=content_type)
        
    try:
        range_str = range_header.replace("bytes=", "").strip()
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if (len(parts) > 1 and parts[1]) else (file_size - 1)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Range Header")
        
    if start >= file_size or end >= file_size or start > end:
        return StreamingResponse(
            iter([]),
            status_code=416,
            headers={
                "Content-Range": f"bytes */{file_size}",
                "Accept-Ranges": "bytes"
            },
            media_type=content_type
        )
        
    chunk_size = end - start + 1
    
    def range_generator():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                chunk = f.read(min(remaining, 64 * 1024))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
                
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
    }
    
    return StreamingResponse(
        range_generator(),
        status_code=206,
        headers=headers,
        media_type=content_type
    )

@app.get("/static/{path:path}")
async def serve_static_range(path: str, request: Request):
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    full_path = (STORAGE_DIR / path).resolve()
    if not str(full_path).startswith(str(STORAGE_DIR)):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
        
    ext = full_path.suffix.lower()
    if ext in (".mp4", ".webm", ".mov", ".ogg"):
        return get_video_range_response(full_path, request)
    return FileResponse(full_path)

@app.get("/api/static/{path:path}")
async def serve_api_static_range(path: str, request: Request):
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    full_path = (STORAGE_DIR / path).resolve()
    if not str(full_path).startswith(str(STORAGE_DIR)):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
        
    ext = full_path.suffix.lower()
    if ext in (".mp4", ".webm", ".mov", ".ogg"):
        return get_video_range_response(full_path, request)
    return FileResponse(full_path)

app.mount("/static", StaticFiles(directory=str(STORAGE_DIR)), name="static")
app.mount("/api/static", StaticFiles(directory=str(STORAGE_DIR)), name="api_static")

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

def init_job_timing():
    return {
        "upload_start": None,
        "raw_start": None,
        "raw_done": None,
        "semantic_start": None,
        "semantic_done": None,
        "proposal_start": None,
        "proposal_done": None,
        "analysis_done": None
    }

def get_timing_summary(timing: dict):
    if not timing:
        return None
    def _diff(end, start):
        if end is not None and start is not None and end > start:
            return round(end - start, 2)
        return None

    return {
        "raw_sec": _diff(timing.get("raw_done"), timing.get("raw_start")),
        "semantic_sec": _diff(timing.get("semantic_done"), timing.get("semantic_start")),
        "proposal_sec": _diff(timing.get("proposal_done"), timing.get("proposal_start")),
        "total_sec": _diff(timing.get("analysis_done"), timing.get("upload_start"))
    }


@app.get("/health")
async def health_check():
    return {"status": "OK", "timestamp": time.time()}


@app.get("/static/thumbnails/P_{prefix}_{i}.jpg")
async def get_panorama_thumbnail(prefix: str, i: int):
    # Serve panorama thumbnail if exists, otherwise fallback or generate on the fly
    from fastapi.responses import FileResponse
    path = STORAGE_DIR / "thumbnails" / f"P_{prefix}_{i}.jpg"
    if path.exists():
        return FileResponse(path)
    # Check if there is a semantic thumbnail or fallback
    fallback_path = STORAGE_DIR / "thumbnails" / f"{prefix}.jpg"
    if fallback_path.exists():
        return FileResponse(fallback_path)
    # Dynamic generation fallback
    return {"status": "NOT_FOUND"}


# ═══════════════════════════════════════════════════════════════════
#   CCUT: 영상 파일 업로드 엔드포인트
# ═══════════════════════════════════════════════════════════════════

@app.post("/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
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
        fingerprint = video_engine.generate_fingerprint(abs_path)
        
        existing = bams.get_source_by_hash(fingerprint)
        source_id = None
        if existing:
            source_id = existing.source_id
            print(f"[UPLOAD] Fingerprint HIT: {fingerprint} -> source_id={source_id}")
            
            # [STEP 2-D-R5] Smart Cache Reanalysis: 품질 체크 및 재분석 트리거
            quality = bams.get_analysis_quality(source_id)
            print(f"[UPLOAD] Analysis Quality check: {quality}")

            if quality.get("needs_asr_reanalysis"):
                fragments = bams.get_fragments_by_source(source_id)
                if fragments:
                    print(f"[UPLOAD] Triggering Smart Reanalysis for {source_id} (Reason: {quality['reason']})")
                    _fragment_job_registry[source_id] = {
                        "status": "ANALYSIS_RUNNING",
                        "progress": 30,
                        "stage": "smart_reanalysis",
                        "source_id": source_id,
                        "error": None,
                        "timing": init_job_timing()
                    }
                    _fragment_job_registry[source_id]["timing"]["upload_start"] = time.time()
                    background_tasks.add_task(_background_whisper, source_id, abs_path, fragments)
                    background_tasks.add_task(_background_signal_analysis, source_id, abs_path, fragments)
                    
                    return {
                        "status": "SOURCE_REUSED_REANALYSIS_STARTED",
                        "file_name": safe_name,
                        "source_id": source_id,
                        "hash_value": fingerprint,
                        "cache_hit": True,
                        "reused": True,
                        "reanalysis": True,
                        "quality": quality,
                        "static_url": f"/static/uploads/{Path(existing.file_path).name}"
                    }

            return {
                "status": "SOURCE_REUSED",
                "file_name": safe_name,
                "source_id": source_id,
                "hash_value": fingerprint,
                "cache_hit": True,
                "reused": True,
                "static_url": f"/static/uploads/{Path(existing.file_path).name}"
            }

        source_id = f"SRC_{uuid.uuid4().hex[:8].upper()}"
        _upload_registry[source_id] = abs_path
        
        # [STEP 10-I.5.22-D] Initialize registry for new source
        _fragment_job_registry[source_id] = {
            "status": "PENDING",
            "progress": 0,
            "source_id": source_id,
            "error": None,
            "timing": init_job_timing()
        }
        _fragment_job_registry[source_id]["timing"]["upload_start"] = time.time()

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
        job = _fragment_job_registry[source_id]
        job["status"] = "ANALYSIS_RUNNING"
        if "timing" not in job:
            job["timing"] = init_job_timing()
        job["timing"]["raw_start"] = time.time()

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
        fragment_words = whisper_res.get("fragment_words", {})
        provider = whisper_res.get("provider", "whisper")
        provider_error = whisper_res.get("provider_error")
        rejected_fragments = whisper_res.get("rejected_fragments", {})

        # [R14] Read current model_size from config.yaml for metadata persistence
        import yaml as _yaml
        _config_path = os.path.join(os.path.dirname(__file__), "ai", "config.yaml")
        try:
            with open(_config_path, encoding="utf-8") as _f:
                _cfg = _yaml.safe_load(_f)
            current_model_size = (
                _cfg.get("providers", {})
                    .get("whisper", {})
                    .get("config", {})
                    .get("model_size", "unknown")
            )
        except Exception:
            current_model_size = "unknown"

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
                "words":      fragment_words.get(frag_id, []),
            }

            print(f"[ASR BG] {frag_id} | hook={hook_score:.3f} | role={role} | transcript={transcript[:20]!r}")

        # 2. role 분포 보정 (Main 쏠림 방지)
        fragments = rebalance_roles(fragments)

        # 3. Evidence Board 및 DB 업데이트
        for frag in fragments:
            try:
                # [STEP 2] Evidence Board 필드 병합 (Text)
                frag_id = frag["fragment_id"]
                transcript = frag["intelligence"]["transcript"]
                
                # [ASR-CONTRACT-R4] Determine fallback reason and metadata
                fb_reason = None
                if not transcript:
                    if frag_id in rejected_fragments:
                        fb_reason = "asr_rejected:" + rejected_fragments[frag_id]
                    elif provider_error:
                        fb_reason = "asr_provider_error:" + provider_error
                    else:
                        fb_reason = "asr_empty"

                bams.update_evidence(frag_id, {
                    "source_id": source_id,
                    "worker_name": provider or "asr",
                    "start": frag["start_time"],
                    "end": frag["end_time"],
                    "text": transcript,
                    "confidence": 0.9,
                    "fallback_reason": fb_reason,
                    "metadata_json": {
                        "asr_provider": provider,
                        "asr_model_size": current_model_size,  # [R14]
                        "asr_provider_error": provider_error,
                        "asr_rejected_reason": rejected_fragments.get(frag_id),
                        "asr_has_text": bool(transcript)
                    }
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
        if source_id in _fragment_job_registry:
            job = _fragment_job_registry[source_id]
            job["stage"] = "semantic_boundary"
            job["progress"] = 80
            if "timing" in job:
                job["timing"]["raw_done"] = time.time()
                job["timing"]["semantic_start"] = time.time()

        from engine.semantic_engine import SemanticFragmentGenerator
        from engine.proposal_engine import ProposalEngine
        
        sem_gen = SemanticFragmentGenerator(bams)
        sem_gen.generate(source_id)
        
        if source_id in _fragment_job_registry:
            job = _fragment_job_registry[source_id]
            job["stage"] = "proposal_generation"
            job["progress"] = 90
            if "timing" in job:
                job["timing"]["semantic_done"] = time.time()
                job["timing"]["proposal_start"] = time.time()

        prop_eng = ProposalEngine(bams)
        prop_eng.generate_proposals(source_id)
        
        if source_id in _fragment_job_registry:
            job = _fragment_job_registry[source_id]
            if "timing" in job:
                job["timing"]["proposal_done"] = time.time()
        
        # 완료 상태 기록
        if source_id in _fragment_job_registry:
            job = _fragment_job_registry[source_id]
            job["status"] = "ANALYSIS_COMPLETE"
            job["progress"] = 100
            if "timing" in job:
                job["timing"]["analysis_done"] = time.time()
                summary = get_timing_summary(job["timing"])
                print(f"[PIPELINE-TIMING] source={source_id} raw={summary['raw_sec']}s semantic={summary['semantic_sec']}s proposal={summary['proposal_sec']}s total={summary['total_sec']}s")
            
        print(f"[ASR BG] {source_id} 완료 (Semantic/Proposals Ready)")
    except Exception as e:
        print(f"[ASR BG] {source_id} 실행 오류: {e}")
        if source_id in _fragment_job_registry:
            _fragment_job_registry[source_id]["status"] = "FAILED"
            _fragment_job_registry[source_id]["error"] = str(e)

    _background_vl_perception(source_id, fragments)


def _background_vl_perception(source_id: str, fragments: list, max_fragments: int = 3):
    print("[PIPELINE] VL Perception pipeline STARTED")
    try:
        from ai.vision.qwen_vl_visual_worker import QwenVLVisualWorker
        worker = QwenVLVisualWorker()

        processed = 0
        for frag in fragments:
            if processed >= max_fragments:
                break

            frag_id = frag.get("fragment_id") or frag.get("id")
            thumb_path = (
                frag.get("thumbnail_path")
                or frag.get("thumb_path")
                or frag.get("thumbnail_url")
                or frag.get("thumb_url")
            )

            if not thumb_path or not os.path.exists(str(thumb_path)):
                print(f"[VL_PERCEPTION] skip {frag_id}: no local thumbnail")
                continue

            result = worker.analyze_image(
                thumb_path,
                resize_max=384,
                timeout_sec=120
            )

            if result.get("status") == "OK":
                existing_intelligence = frag.get("intelligence") or {}
                if not isinstance(existing_intelligence, dict):
                    existing_intelligence = {}
                existing_intelligence["perception"] = result

                if hasattr(bams, "update_fragment_intelligence"):
                    bams.update_fragment_intelligence(frag_id, existing_intelligence)
                    print(f"[VL_PERCEPTION] SAVED {frag_id} scene={result.get('scene_type')}")
                else:
                    print(f"[VL_PERCEPTION] OK {frag_id} artifact-only")
                processed += 1
            else:
                print(f"[VL_PERCEPTION] FAIL {frag_id} status={result.get('status')}")

    except Exception as e:
        print(f"[VL_PERCEPTION] ERROR: {e}")


def _background_panorama(source_id: str, video_path: str, fragments: list):
    """
    백그라운드: PBE용 파노라마 썸네일 생성
    조각별 대표 프레임 1장씩 추출 → storage/panorama/{fragment_id}.jpg
    """
    print(f"[PANORAMA BG] source_id={source_id} 파노라마 생성 시작")
    for frag in fragments:
        try:
            thumb_path = video_engine.extract_thumbnail(
                video_path,
                frag["start_time"],
                frag["fragment_id"],
            )
            if thumb_path:
                bams.update_fragment_thumb(frag["fragment_id"], thumb_path)
                print(f"[PANORAMA BG] {frag['fragment_id']} 썸네일 생성 완료: {thumb_path}")
            else:
                print(f"[PANORAMA BG] {frag['fragment_id']} 썸네일 생성 실패 (None)")
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

    # [STEP 10-I.5.18] 이미 분석 완료된 데이터가 있는지 확인
    proposals = bams.get_proposals(source_id)

    # [FIX] Registry에 이미 진행 중인 작업이 있는지 확인 (중복 방지)
    existing_job = _fragment_job_registry.get(source_id)
    if existing_job and existing_job.get("status") in ["ANALYSIS_RUNNING", "FRAGMENT_READY"]:
        print(f"[GENERATE-FRAGMENTS] Job already in progress for {source_id}")
        return {
            "status": "L1_COMPLETE",
            "progress": 100,
            "source_id": source_id,
            "count": len(fragments),
            "fragments": fragments,
            "analysis_mode": analysis_mode,
            "pipeline": "virtual_clipping_v1.0.6",
        }

    if not is_new_source and proposals:
        # [STEP 2-D-R5] Smart Cache Reanalysis: 캐시 히트 시에도 품질 미달이면 재분석
        quality = bams.get_analysis_quality(source_id)
        if quality.get("needs_asr_reanalysis"):
            print(f"[GENERATE-FRAGMENTS] Low Quality detected ({quality['reason']}). Triggering Reanalysis.")
            
            existing_job = _fragment_job_registry.get(source_id)
            upload_start = existing_job["timing"]["upload_start"] if (existing_job and "timing" in existing_job) else time.time()
            
            _fragment_job_registry[source_id] = {
                "progress": 30,
                "status": "ANALYSIS_RUNNING",
                "stage": "smart_reanalysis",
                "source_id": source_id,
                "fragment_count": len(fragments),
                "analysis_mode": analysis_mode,
                "error": None,
                "timing": init_job_timing()
            }
            _fragment_job_registry[source_id]["timing"]["upload_start"] = upload_start
            
            background_tasks.add_task(_background_whisper, source_id, resolved_path, fragments)
            background_tasks.add_task(_background_signal_analysis, source_id, resolved_path, fragments)

            safe_fragments = [
                {k: v for k, v in f.items() if k != "_internal_video_path"}
                for f in fragments
            ]

            return {
                "status": "L1_REANALYSIS_STARTED",
                "progress": 30,
                "source_id": source_id,
                "count": len(safe_fragments),
                "fragments": safe_fragments,
                "analysis_mode": analysis_mode,
                "reanalysis": True,
                "quality": quality,
                "pipeline": "virtual_clipping_v1.0.6"
            }
        else:
            print(f"[GENERATE-FRAGMENTS] Already Analyzed: {source_id}")
            existing_job = _fragment_job_registry.get(source_id)
            upload_start = existing_job["timing"]["upload_start"] if (existing_job and "timing" in existing_job) else time.time()
            
            _fragment_job_registry[source_id] = {
                "progress": 100,
                "status": "ANALYSIS_COMPLETE",
                "stage": "proposal_generation",
                "source_id": source_id,
                "fragment_count": len(fragments),
                "analysis_mode": analysis_mode,
                "error": None,
                "timing": init_job_timing()
            }
            _fragment_job_registry[source_id]["timing"]["upload_start"] = upload_start
    else:
        existing_job = _fragment_job_registry.get(source_id)
        upload_start = existing_job["timing"]["upload_start"] if (existing_job and "timing" in existing_job) else time.time()

        _fragment_job_registry[source_id] = {
            "progress": 30, # L1 작업 완료 직후이므로 30% 정도로 표시
            "status": "FRAGMENT_READY",
            "source_id": source_id,
            "fragment_count": len(fragments),
            "analysis_mode": analysis_mode,
            "error": None,
            "timing": init_job_timing()
        }
        _fragment_job_registry[source_id]["timing"]["upload_start"] = upload_start

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
async def get_fragment_analysis_status(source_id: str, background_tasks: BackgroundTasks):
    """의미분석 진행 상태 조회 (Index.tsx polling용)"""
    job = _fragment_job_registry.get(source_id)
    if not job:
        # [STEP 10-I.5.18] Registry 에 없으면 DB에서 상태 복원 또는 재분석 트리거
        proposals = bams.get_proposals(source_id)
        if proposals:
            # [STEP 2-D-R5] Smart Cache Reanalysis check during status restoration
            quality = bams.get_analysis_quality(source_id)
            if quality.get("needs_asr_reanalysis"):
                fragments = bams.get_fragments_by_source(source_id)
                source = bams.get_source(source_id)
                if source and os.path.exists(source.file_path) and fragments:
                    print(f"[STATUS] Low Quality detected for {source_id}. Triggering Reanalysis during restoration.")
                    job = {
                        "status": "ANALYSIS_RUNNING",
                        "progress": 30,
                        "stage": "smart_reanalysis",
                        "source_id": source_id,
                        "error": None,
                        "timing": init_job_timing()
                    }
                    _fragment_job_registry[source_id] = job
                    job["timing"]["upload_start"] = time.time()
                    
                    background_tasks.add_task(_background_whisper, source_id, source.file_path, fragments)
                    background_tasks.add_task(_background_signal_analysis, source_id, source.file_path, fragments)
                    
                    return {
                        "status": "ANALYSIS_RUNNING",
                        "progress": 30,
                        "stage": "smart_reanalysis",
                        "source_id": source_id,
                        "error": None,
                        "quality": quality
                    }

            job = {
                "status": "ANALYSIS_COMPLETE",
                "progress": 100,
                "stage": "proposal_generation",
                "source_id": source_id,
                "error": None,
                "timing": init_job_timing()
            }
            _fragment_job_registry[source_id] = job
            print(f"[STATUS] Registry restored (COMPLETE) from DB for {source_id}")
        else:
            # 완료되지 않았지만 fragments는 있을 수 있음
            fragments = bams.get_fragments_by_source(source_id)
            if fragments:
                # 분석이 중단된 상태로 간주 -> 재분석 트리거 시도
                source = bams.get_source(source_id)
                if source and os.path.exists(source.file_path):
                    stage = bams.get_analysis_stage(source_id)
                    job = {
                        "status": "ANALYSIS_RUNNING",
                        "progress": 30,
                        "stage": f"restored_{stage}",
                        "source_id": source_id,
                        "error": None,
                        "timing": init_job_timing()
                    }
                    _fragment_job_registry[source_id] = job
                    background_tasks.add_task(_background_whisper, source_id, source.file_path, fragments)
                    background_tasks.add_task(_background_panorama, source_id, source.file_path, fragments)
                    background_tasks.add_task(_background_signal_analysis, source_id, source.file_path, fragments)
                    print(f"[STATUS] Registry restored (RUNNING) from DB for {source_id} at stage {stage}")
                else:
                    # 파일까지 없으면 실패로 간주
                    return {"status": "FAILED", "source_id": source_id, "error": "Source file missing or registry lost"}
            else:
                return {"status": "NOT_FOUND", "source_id": source_id}

    return {
        "status": job.get("status", "PENDING"),
        "progress": job.get("progress", 0),
        "stage": job.get("stage", "initial"),
        "source_id": source_id,
        "error": job.get("error"),
        "timing_summary": get_timing_summary(job.get("timing"))
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

def inject_semantic_thumbnails(fragments: list):
    """
    [STEP 10-K-C1-R42] Generate unique thumbnails for each Semantic Fragment.
    If SF specific thumbnail doesn't exist, extract it from source video.
    Falls back to parent VF thumbnail if extraction fails.
    """
    if not fragments:
        return fragments
        
    thumb_dir = STORAGE_DIR / "thumbnails"
    try:
        available_thumbs = set(os.listdir(thumb_dir))
    except Exception:
        available_thumbs = set()

    for f in fragments:
        fid = f.get("fragment_id")
        sid = f.get("source_id")
        
        if not fid or not sid:
            continue

        # 1. R42: Check if SF-specific thumbnail exists
        sf_thumb_filename = f"{fid}.jpg"
        if sf_thumb_filename in available_thumbs:
            url = f"/static/thumbnails/{sf_thumb_filename}"
            f["thumbnail_url"] = url
            if not isinstance(f.get("thumbnail"), dict): f["thumbnail"] = {}
            f["thumbnail"]["thumbnail_url"] = url
            # intelligence.thumb_url 보전
            if not isinstance(f.get("intelligence"), dict): f["intelligence"] = {}
            f["intelligence"]["thumb_url"] = url
            continue
            
        # 2. R42: Try to generate unique thumbnail for SF
        source_data = bams.get_source(sid)
        if source_data and source_data.file_path:
            fps = getattr(source_data, 'fps', 30.0) or 30.0
            start_frame = f.get("start_frame")
            if start_frame is None:
                start_sec = f.get("start") or f.get("start_time") or 0.0
                start_frame = int(float(start_sec) * fps)
            
            try:
                # Extract at exact start_frame (start_sec)
                extract_sec = max(0, start_frame / fps)
                # Output name format: SF_{fid}_{sid}
                video_engine.extract_thumbnail(source_data.file_path, extract_sec, fid)
                
                url = f"/static/thumbnails/{sf_thumb_filename}"
                f["thumbnail_url"] = url
                if not isinstance(f.get("thumbnail"), dict): f["thumbnail"] = {}
                f["thumbnail"]["thumbnail_url"] = url
                if not isinstance(f.get("intelligence"), dict): f["intelligence"] = {}
                f["intelligence"]["thumb_url"] = url
                
                # Update cache
                available_thumbs.add(sf_thumb_filename)
                continue
            except Exception as e:
                print(f"[R42] Thumbnail extraction failed for {fid}: {e}")

        # 3. Fallback to parent VF thumbnail (Legacy)
        # Skip if already has thumbnail_url in either format
        if f.get("thumbnail_url") or (isinstance(f.get("thumbnail"), dict) and f["thumbnail"].get("thumbnail_url")):
            continue
            
        parent_vf_id = None
        candidates = []
        sem = f.get("semantic")
        if isinstance(sem, dict):
            candidates.extend(sem.get("evidence_refs", []))
            candidates.extend(sem.get("transcript_refs", []))
        candidates.extend(f.get("evidence_refs", []))
        candidates.extend(f.get("transcript_refs", []))
        
        for cand in candidates:
            if isinstance(cand, str) and cand.startswith("VF") and "_SRC_" in cand:
                parent_vf_id = cand
                break
        
        if parent_vf_id:
            thumb_filename = f"{parent_vf_id}.jpg"
            if thumb_filename in available_thumbs:
                fallback_url = f"/static/thumbnails/{thumb_filename}"
                f["thumbnail_url"] = fallback_url
                if not isinstance(f.get("thumbnail"), dict): f["thumbnail"] = {}
                f["thumbnail"]["thumbnail_url"] = fallback_url
    
    return fragments

def inject_preview_clips(fragments: list, background: bool = True) -> list:
    """
    [PREVIEW_CLIP_INJECT] 각 Semantic Fragment에 preview_clip_url 필드를 주입.
    clip 파일이 없으면 ffmpeg로 생성(background=True 시 비동기), 있으면 재사용.
    video_url fallback 금지 — 생성 실패 시 preview_clip_url = None.
    """
    if not fragments:
        return fragments

    from engine.preview_clip_engine import ensure_preview_clip
    import threading

    def _make_clip(f: dict):
        fid = f.get("fragment_id")
        sid = f.get("source_id")
        if not fid:
            return

        # 이미 주입된 경우 스킵
        if f.get("preview_clip_url"):
            return

        # 시작/종료 초 결정
        start = (
            f.get("start")
            or f.get("start_time")
            or 0.0
        )
        end = (
            f.get("end")
            or f.get("end_time")
            or 0.0
        )
        if not isinstance(start, (int, float)):
            start = 0.0
        if not isinstance(end, (int, float)) or end <= start:
            return

        # 원본 파일 경로 결정
        source_data = bams.get_source(sid) if sid else None
        source_path = source_data.file_path if source_data else None
        if not source_path or not os.path.exists(source_path):
            print(f"[PREVIEW_CLIP_INJECT] source_path missing for {fid}")
            return

        result = ensure_preview_clip(
            fragment_id=fid,
            source_path=source_path,
            start=float(start),
            end=float(end),
            storage_dir=STORAGE_DIR,
            app_base_url=APP_BASE_URL,
        )
        clip_url = result.get("preview_clip_url")
        f["preview_clip_url"] = clip_url
        print(
            f"[PREVIEW_CLIP_INJECT] {fid} status={result['status']} "
            f"url={clip_url}"
        )

    if background:
        threads = []
        for f in fragments:
            t = threading.Thread(target=_make_clip, args=(f,), daemon=True)
            t.start()
            threads.append(t)
        # 최대 30초 대기 (응답 블로킹 방지 겸 첫 클립은 완료 보장)
        for t in threads:
            t.join(timeout=30)
    else:
        for f in fragments:
            _make_clip(f)

    return fragments


def inject_proposal_previews(proposals: list) -> list:
    """
    [PROPOSAL_PREVIEW_INJECT] proposals 배열의 각 제안에 preview_url을 주입.
    proposal.sequence -> clips -> ensure_proposal_preview -> preview_url.
    preview_url이 없으면 None (fallback 금지).
    """
    if not proposals:
        return proposals

    from engine.proposal_preview_engine import ensure_proposal_preview

    for p in proposals:
        variant     = (p.get("mode") or "A").upper()
        proposal_id = p.get("proposal_id") or p.get("id") or "UNKNOWN"
        sequence    = p.get("sequence", [])

        # sequence -> clips [{source_path, start, end}]
        clips = []
        for frag in sequence:
            sid   = frag.get("source_id") or ""
            start = float(frag.get("start_sec") or frag.get("start") or frag.get("start_time") or 0.0)
            end   = float(frag.get("end_sec")   or frag.get("end")   or frag.get("end_time")   or 0.0)
            if not sid or end <= start:
                continue
            source_data = bams.get_source(sid)
            source_path = source_data.file_path if source_data else None
            if not source_path or not os.path.exists(source_path):
                print(f"[PROPOSAL_PREVIEW_INJECT] source_path missing for {sid}")
                continue
            clips.append({"source_path": source_path, "start": start, "end": end})

        if not clips:
            p["preview_url"] = None
            print(f"[PROPOSAL_PREVIEW_INJECT] {proposal_id}/{variant}: clips 없음 -> preview_url=None")
            continue

        result = ensure_proposal_preview(proposal_id=proposal_id, variant=variant, clips=clips)
        p["preview_url"]      = result.get("preview_url")
        p["preview_duration"] = result.get("duration", 0.0)
        print(f"[PROPOSAL_PREVIEW_INJECT] {proposal_id}/{variant} status={result['status']} url={p['preview_url']}")

    return proposals


@app.post("/semantic-fragments/{source_id}")
async def generate_semantic_fragments(source_id: str, refresh_proposals: bool = False):
    """[STEP 4] Evidence Board 기반 Semantic Fragment 생성
    
    refresh_proposals=True 일 때만 ProposalEngine을 추가로 호출한다.
    기본값 False — 기존 동작 완전 유지 (preview PRODUCT PASS 흐름 불변).
    """
    from engine.semantic_engine import SemanticFragmentGenerator
    gen = SemanticFragmentGenerator(bams)
    fragments = gen.generate(source_id)

    print(f"[SEMANTIC] /semantic-fragments/{source_id} called. Result count: {len(fragments)}")

    # [STEP 10-I.5.22-C] Inject thumbnails
    fragments = inject_semantic_thumbnails(fragments)

    # [PREVIEW_CLIP] inject_preview_clips 제거 — 최종 해결은 proposal_preview_engine이므로 fragment 단위 clip 주입 불필요
    # (preview_clip_engine.py 미존재 시 ImportError → 500 상승 방지)

    # Role 분산 통계 계산
    role_dist = {}
    for f in fragments:
        role = f["structural"].get("role", "context")
        role_dist[role] = role_dist.get(role, 0) + 1

    response = {
        "status": "SEMANTIC_FRAGMENT_READY",
        "source_id": source_id,
        "fragment_count": len(fragments),
        "role_distribution": role_dist,
        "fragments": fragments,
        "proposal_refreshed": False,
        "snap_debug": getattr(gen, "_snap_debug", {}),   # ← 추가
    }

    # [STEP 1-R5] 명시적 요청 시에만 Proposal 재생성 — 자동 연동 금지
    if refresh_proposals:
        try:
            from engine.proposal_engine import ProposalEngine
            prop_eng = ProposalEngine(bams)
            proposals = prop_eng.generate_proposals(source_id)
            response["proposal_refreshed"] = True
            response["proposal_count"] = len(proposals)
            response["proposal_ids"] = [p.get("proposal_id") for p in proposals]
            print(f"[SEMANTIC] Proposal refreshed for {source_id}: {len(proposals)} proposals")
        except Exception as e:
            response["proposal_refreshed"] = False
            response["proposal_error"] = str(e)
            print(f"[SEMANTIC] Proposal refresh FAILED for {source_id}: {e}")

    return response

@app.get("/semantic-fragments/{source_id}")
async def get_semantic_fragments(source_id: str):
    """[STEP 4] 저장된 Semantic Fragments 조회 (v3.2.1 보완)"""
    fragments = bams.get_semantic_fragments(source_id)
    
    # [STEP 10-I.5.22-C] Inject thumbnails
    fragments = inject_semantic_thumbnails(fragments)

    # [PREVIEW_CLIP] inject_preview_clips 제거 — 최종 해결은 proposal_preview_engine이뮼로 fragment 단위 clip 주입 불필요
    # (preview_clip_engine.py 미존재 시 ImportError 상승 방지)
    
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
#   [STEP 5] User Intent Reflections & Narrative AI
# ═══════════════════════════════════════════════════════════════════

class NarrativeIntentRequest(BaseModel):
    message: str
    source_id: Optional[str] = None

@app.post("/api/narrative/intent")
@app.post("/narrative/intent")
async def post_narrative_intent(req: NarrativeIntentRequest):
    """
    [STEP 10-I.5.28-H] Narrative LLM (qwen3:4b) 연동
    사용자의 자연어를 StoryIntentPatch JSON으로 해석합니다.
    """
    from ai.boundary.narrative_provider_adapter import NarrativeProviderAdapter
    try:
        adapter = NarrativeProviderAdapter()
        result = adapter.get_story_intent_patch(req.message)
        
        # Result mapping to dict for FastAPI response
        return {
            "status": result.status,
            "patch": vars(result.patch) if result.patch else None,
            "latency_ms": result.latency_ms,
            "error": result.error_message
        }
    except Exception as e:
        return {
            "status": "ADAPTER_ERROR",
            "error": str(e)
        }

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

def validate_semantic_schema(fragments: list) -> list:
    """[STEP 10-I.5.11] Semantic Fragment Schema Validation"""
    errors = []
    for f in fragments:
        missing = []
        invalid = []
        
        if not f.get("fragment_id"): missing.append("fragment_id")
        if not f.get("source_id"): missing.append("source_id")
        
        start = f.get("start")
        end = f.get("end")
        if start is None: missing.append("start")
        if end is None: missing.append("end")
        
        if start is not None and end is not None:
            if end <= start: invalid.append(f"end({end}) <= start({start})")
            
        structural = f.get("structural")
        if not isinstance(structural, dict):
            invalid.append("structural is not a dict")
        else:
            if structural.get("duration") is None:
                if start is not None and end is not None:
                    pass # start/end 로 계산 가능하므로 허용
                else:
                    missing.append("structural.duration")
            elif structural.get("duration") <= 0:
                invalid.append(f"duration({structural.get('duration')}) <= 0")
            
        if not isinstance(f.get("semantic"), (dict, type(None))):
            invalid.append("semantic is not a dict or None")
            
        if missing or invalid:
            errors.append({
                "fragment_id": f.get("fragment_id", "UNKNOWN"),
                "missing": missing,
                "invalid": invalid
            })
    return errors

class ProjectProposalRequest(BaseModel):
    project_id: str
    source_ids: list[str]
    target_length: float = 60.0
    user_intent: Optional[dict] = None
    template_id: Optional[str] = None



@app.get("/proposals/project/{project_id}/sources")
async def get_project_sources(project_id: str):
    """
    [CCUT1.0.4 PROPOSALS PROJECT SOURCES HYDRATION]
    프로젝트에 매핑되어 있는 모든 source_id 목록 및 메타데이터를 역조회하여 프론트엔드로 전달합니다.
    """
    import os
    import json
    from database import SessionLocal
    from archive.db_models import ProposalTable, SourceTable

    source_ids = []
    
    with SessionLocal() as db:
        # 1. Proposals 테이블에서 source_id가 project_id인 것들을 쿼리
        props = db.query(ProposalTable).filter_by(source_id=project_id).all()
        for p in props:
            # sequence JSON 파싱
            seq = p.sequence or []
            if isinstance(seq, str):
                try:
                    seq = json.loads(seq)
                except Exception:
                    seq = []
            
            for clip in seq:
                sid = clip.get("source_id")
                if sid and sid not in source_ids:
                    source_ids.append(sid)
        
        # 2. 만약 해당 project_id로 저장된 제안 정보가 없다면, 에러 응답 반환
        if not source_ids:
            return {
                "status": "NO_PROPOSALS_FOUND",
                "project_id": project_id,
                "sources": [],
                "reason": "No proposal sequence found for project_id"
            }

        # 3. 각 source_id에 대해 Source 정보 조회 및 Fragment 로드
        collected_sources = []
        for idx, sid in enumerate(source_ids):
            src = db.query(SourceTable).filter_by(source_id=sid).first()
            if not src:
                continue
            
            # fragments 로드 (bams 이용)
            frags = bams.get_semantic_fragments(sid)
            if not frags:
                frags = bams.get_fragments_by_source(sid)

            # 비디오 URL 변환 (file_path가 절대 경로이면 basename을 따옴)
            video_name = os.path.basename(src.file_path) if src.file_path else f"{sid}.mp4"
            vurl = f"/static/{video_name}"

            # Label 순서대로 부여 (A, B, C, D...)
            label = chr(65 + idx)

            collected_sources.append({
                "source_id": sid,
                "label": label,
                "video_url": vurl,
                "fragments": frags,
                "file_size_bytes": 0, # mock size
                "duration_sec": src.duration or 0.0
            })

    return {
        "status": "OK",
        "project_id": project_id,
        "sources": collected_sources
    }

@app.post("/proposals/project")
async def post_generate_project_proposals(req: ProjectProposalRequest):
    """
    [STEP 10-I.5.24-R1] Multi-Source Project Proposal 생성 (v0.1)
    """
    import traceback
    from engine.proposal_engine import ProposalEngine

    project_id = req.project_id
    
    # [STEP 10-I.5.27-E6] Stable Dedupe: 순서 보존하며 중복 제거
    raw_source_ids = req.source_ids
    source_ids = []
    seen = set()
    for sid in raw_source_ids:
        if sid and sid not in seen:
            source_ids.append(sid)
            seen.add(sid)
            
    target_len = req.target_length
    user_intent = req.user_intent
    req_template_id = req.template_id

    # [STEP 10-K-B2] Resolve Story Template
    resolved_story_template = template_resolver.resolve_story_template(
        user_intent=user_intent, 
        template_id=req_template_id
    )
    resolved_story_template["user_intent"] = user_intent
    logger.info(f"[PROPOSAL] Resolved Template: {resolved_story_template.get('template_id')} (via {req_template_id or 'intent'})")

    if not source_ids:
        return {
            "status": "ERROR", 
            "message": "source_ids 배열이 비어있습니다.",
            "resolved_story_template": resolved_story_template # [STEP 10-K-B2-R1]
        }

    all_fragments = []
    warnings = []

    for sid in source_ids:
        frags = bams.get_semantic_fragments(sid)
        if not frags:
            # [STEP 10-I.5.24-R1] Raw fallback 금지, Skip + Warning
            warnings.append({
                "source_id": sid, 
                "reason": "NO_SEMANTIC_FRAGMENTS_SKIPPED"
            })
            continue
        
        # [STEP 10-I.5.22-C] Inject thumbnails
        frags = inject_semantic_thumbnails(frags)
        all_fragments.extend(frags)

    if not all_fragments:
        return {
            "status": "NO_SEMANTIC_DATA",
            "project_id": project_id,
            "source_ids": source_ids,
            "message": "제안을 생성할 유효한 Semantic 조각이 없습니다.",
            "resolved_story_template": resolved_story_template, # [STEP 10-K-B2-R1]
            "warnings": warnings
        }

    try:
        engine = ProposalEngine(bams)
        proposals = engine.generate_proposals_from_fragments(
            project_id=project_id,
            source_ids=source_ids,
            fragments=all_fragments,
            target_len=target_len,
            story_context=resolved_story_template # [STEP 10-K-B2]
        )

        # Source Usage 진단 (제안 A/B 통합)
        source_usage = {}
        for p in proposals:
            # [STEP 10-K-C1-R38] Response-Level Hard Guard (proposal_guards 위임)
            before = len(p.get("sequence", []))
            p["sequence"] = response_level_sequence_guard(p.get("sequence", []))
            after = len(p.get("sequence", []))
            p["duration"] = round(sum(
                float(f.get("duration_sec") or f.get("duration") or 0)
                for f in p["sequence"]
            ), 2)
            print(f"[R38_RESPONSE_GUARD] proposal={p.get('mode')} before={before} after={after}")

            for frag in p.get("sequence", []):
                sid = frag.get("source_id", "UNKNOWN")
                source_usage[sid] = source_usage.get(sid, 0) + 1

        # [PROPOSAL_PREVIEW_INJECT] preview_url 주입 (동기, 렌더 후 응답)
        proposals = inject_proposal_previews(proposals)

        # [STEP 14-D] Proposal Ranker integration
        try:
            from learning.proposal_ranker import ProposalRanker
            proposals = ProposalRanker.rerank_proposals(proposals)
        except Exception as rank_err:
            print(f"[RERANKER][ERROR] Failed to rerank project proposals: {rank_err}")

        return {
            "status": "PROPOSAL_READY",
            "project_id": project_id,
            "source_ids": source_ids,
            "semantic_count": len(all_fragments),
            "proposals": proposals,
            "source_usage": source_usage,
            "resolved_story_template": resolved_story_template, # [STEP 10-K-B2-R1]
            "warnings": warnings if warnings else None
        }


    except Exception as e:
        print(f"[PROJECT PROPOSAL ERROR] {str(e)}")
        traceback.print_exc()
        return {
            "status": "INTERNAL_SERVER_ERROR",
            "project_id": project_id,
            "message": str(e)
        }


@app.post("/proposals/{source_id}")
async def post_generate_proposals(source_id: str):
    """
    [STEP 6] Proposal 생성 트리거 (v3.2.1 정밀 진단 버전)
    """
    import traceback
    from engine.proposal_engine import ProposalEngine

    try:
        # 1. Semantic Fragment 조회 및 검증
        fragments = bams.get_semantic_fragments(source_id)
        if not fragments:
            print(f"[PROPOSAL] No semantic fragments found for {source_id}")
            return {
                "status": "NO_SEMANTIC_DATA",
                "source_id": source_id,
                "proposal_count": 0,
                "proposals": []
            }
        
        # 2. Schema Validation
        schema_errors = validate_semantic_schema(fragments)
        if schema_errors:
            print(f"[PROPOSAL] Schema Validation Failed for {source_id}")
            print(f"[PROPOSAL] Errors: {schema_errors[:5]}...") # 5개만 출력
            return {
                "status": "PROPOSAL_SCHEMA_INVALID",
                "source_id": source_id,
                "errors": schema_errors
            }

        # 3. Proposal 생성
        engine = ProposalEngine(bams)
        proposals = engine.generate_proposals(source_id)
        
        # [STEP 10-I.5.22-C] Inject thumbnails into proposal sequences
        for p in proposals:
            if "sequence" in p:
                p["sequence"] = inject_semantic_thumbnails(p["sequence"])
        
        # [PROPOSAL_PREVIEW_INJECT] preview_url 주입
        proposals = inject_proposal_previews(proposals)

        # [STEP 14-D] Proposal Ranker integration
        try:
            from learning.proposal_ranker import ProposalRanker
            proposals = ProposalRanker.rerank_proposals(proposals)
        except Exception as rank_err:
            print(f"[RERANKER][ERROR] Failed to rerank source proposals: {rank_err}")

        return {
            "status": "PROPOSAL_READY",
            "source_id": source_id,
            "proposal_count": len(proposals),
            "proposals": proposals
        }

    except Exception as e:
        print("\n" + "!" * 60)
        print(f"[PROPOSAL ERROR] source_id: {source_id}")
        print(f"Exception Type: {type(e).__name__}")
        print(f"Message: {str(e)}")
        print("-" * 60)
        traceback.print_exc()
        
        # Semantic Sample Logging
        fragments = bams.get_semantic_fragments(source_id)
        print(f"[PROPOSAL ERROR] Total semantic fragments: {len(fragments)}")
        if fragments:
            print("[PROPOSAL ERROR] Sample Fragments (first 3):")
            for f in fragments[:3]:
                print(f"  - ID: {f.get('fragment_id')}")
                print(f"    Source: {f.get('source_id')}")
                print(f"    Time: {f.get('start')} ~ {f.get('end')}")
                print(f"    Structural: {f.get('structural')}")
                print(f"    Semantic keys: {list(f.get('semantic', {}).keys()) if f.get('semantic') else 'None'}")
                print(f"    Confidence: {f.get('confidence')}")
                print(f"    Fallback: {f.get('fallback_reason')}")
        print("!" * 60 + "\n")

        return {
            "status": "INTERNAL_SERVER_ERROR",
            "source_id": source_id,
            "error_type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc()
        }


@app.get("/proposals/{source_id}")
async def get_proposals_api(source_id: str):
    """[STEP 6] 저장된 제안 조회"""
    proposals = bams.get_proposals(source_id)
    
    # [STEP 11-A] Swarm Audit Integration
    try:
        from engine.proposal_audit_engine import ProposalAuditEngine
        audit_engine = ProposalAuditEngine(bams)
        for p in proposals:
            p["swarm_audit"] = audit_engine.audit_proposal(p, source_id)
    except Exception as audit_err:
        print(f"[SWARM_AUDIT][ERROR] Failed to audit loaded proposals: {audit_err}")

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
        
    # [STEP 14-A] Log user proposal acceptance decision
    try:
        from learning.decision_logger import DecisionLogger
        with SessionLocal() as db_session:
            prop_row = db_session.query(ProposalTable).filter_by(proposal_id=proposal_id).first()
            if prop_row:
                src_id = prop_row.source_id
                # Fetch sibling proposals under the same project
                siblings = bams.get_proposals(src_id)
                sibling_dicts = []
                for s in siblings:
                    sibling_dicts.append({
                        "proposal_id": s.proposal_id,
                        "mode": s.mode,
                        "sequence": s.sequence,
                        "duration": s.duration,
                        "original_reason": s.proposal_reason,
                        "human_reality_score_data": s.proposal_reason.get("human_reality_score") if isinstance(s.proposal_reason, dict) else {}
                    })
                DecisionLogger.log_user_proposal_choice(
                    project_id=src_id,
                    chosen_mode=prop_row.mode,
                    proposals=sibling_dicts
                )
    except Exception as log_err:
        print(f"[DECISION_LOGGER][ERROR] Failed to log user proposal choice: {log_err}")
        
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

@app.get("/generate-fragments/status-legacy/{source_id}")
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


@app.get("/publish/list")
async def get_published_list(db: Session = Depends(get_db)):
    """[SNS Upload] Get list of all published items"""
    assets = db.query(PublishedTable).order_by(PublishedTable.published_at.desc()).all()
    return [{
        "publish_id": a.publish_id,
        "program_id": a.program_id,
        "platform": a.platform,
        "final_video_path": a.final_video_path,
        "title": a.title,
        "published_at": a.published_at.isoformat() if a.published_at else None
    } for a in assets]


@app.get("/archive/list")
async def get_archive_list(db: Session = Depends(get_db)):
    """[Archive] Get list of historical projects and sources"""
    sources = db.query(SourceTable).all()
    programs = db.query(ProgramTable).all()
    proposals = db.query(ProposalTable).all()
    
    return {
        "sources": [{
            "source_id": s.source_id,
            "file_path": s.file_path,
            "title": s.title,
            "duration": s.duration,
            "fps": s.fps,
            "created_at": s.created_at.isoformat() if s.created_at else None
        } for s in sources],
        "programs": [{
            "program_id": p.program_id,
            "name": p.name,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None
        } for p in programs],
        "proposals": [{
            "proposal_id": pr.proposal_id,
            "source_id": pr.source_id,
            "mode": pr.mode,
            "duration": pr.duration,
            "created_at": pr.created_at.isoformat() if pr.created_at else None
        } for pr in proposals]
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


class PanoramaExtractRequest(BaseModel):
    fragments: list[dict]


@app.post("/pbe/extract-panoramas")
async def extract_pbe_panoramas(req: PanoramaExtractRequest, background_tasks: BackgroundTasks):
    """
    [PBE PRE-EXTRACTION] PBE 모달 진입 시 프레임 스트립 썸네일 이미지의 엑스박스를 방지하기 위해
    비동기로 해당 조각들의 12개 panorama 프레임을 미리 FFmpeg로 추출합니다.
    """
    if not req.fragments:
        return {"status": "EMPTY"}
    
    # 각 fragment의 source_id 별로 file_path를 조회해 fragment 정보에 video_path 주입
    enriched_fragments = []
    source_cache = {}
    for f in req.fragments:
        source_id = f.get("source_id")
        if not source_id:
            continue
            
        if source_id not in source_cache:
            source_data = bams.get_source(source_id)
            if source_data and source_data.file_path:
                source_cache[source_id] = source_data.file_path
            else:
                source_cache[source_id] = None
                
        v_path = source_cache.get(source_id)
        if v_path:
            f_copy = dict(f)
            f_copy["video_path"] = v_path
            enriched_fragments.append(f_copy)
            
    if not enriched_fragments:
        return {"status": "ERROR", "message": "No valid source video found for fragments"}
        
    # ffmpeg batch panorama 추출을 백그라운드로 예약
    background_tasks.add_task(
        video_engine.batch_extract_panoramas,
        None,
        enriched_fragments,
        4
    )
    return {"status": "STARTED", "count": len(enriched_fragments)}


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
    res = pbe_ai.commit_pbe_change(left_id, right_id, req.new_split_point, req.user_msg)
    
    # [STEP 14-A] Log PBE boundary adjustments as negative feedback to predictions
    try:
        from learning.decision_logger import DecisionLogger
        DecisionLogger.log_pbe_manual_edit(
            project_id="pbe_manual_project",
            fragment_id=left_id,
            before_start=0.0,
            before_end=0.0,
            after_start=req.new_split_point,
            after_end=req.new_split_point
        )
    except Exception as log_err:
        print(f"[DECISION_LOGGER][ERROR] Failed to log manual PBE delta shift: {log_err}")
        
    return res


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


# [STEP 15] YouTube Robot Learner REST endpoints
class YouTubeRobotRequest(BaseModel):
    query: str
    limit: int = 3
    media: bool = False

@app.post("/learning/robot/run")
async def run_youtube_learning_robot(req: YouTubeRobotRequest):
    try:
        from learning.youtube_robot import YouTubeRobotLearner
        import asyncio
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(
            None,
            YouTubeRobotLearner.execute_learning_step,
            req.query,
            req.limit,
            req.media
        )
        return {"status": "SUCCESS", "data": res}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

@app.get("/learning/robot/stats")
async def get_youtube_learning_stats():
    try:
        from database import SessionLocal
        from learning.learning_models import UserEditDecisionTable
        with SessionLocal() as db:
            runs = db.query(UserEditDecisionTable).filter_by(decision_type="YOUTUBE_ROBOT_LEARN").all()
            stats = []
            for r in runs:
                stats.append({
                    "decision_id": r.decision_id,
                    "project_id": r.project_id,
                    "query": r.user_intent.get("query") if r.user_intent else "",
                    "url": r.user_intent.get("url") if r.user_intent else "",
                    "activated_patterns": r.selected_fragments,
                    "created_at": r.created_at.isoformat() if r.created_at else ""
                })
            return {"status": "SUCCESS", "stats": stats}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


# [STEP 16] Teacher Mentorship Coaching REST endpoints
class TeacherCoachingRequest(BaseModel):
    project_id: str
    prop_a: dict
    prop_b: dict

@app.post("/learning/teacher/coaching")
async def run_teacher_coaching(req: TeacherCoachingRequest):
    try:
        from learning.teacher_mentor import TeacherMentor
        res = TeacherMentor.coach_student_if_uncertain(req.project_id, req.prop_a, req.prop_b)
        return {"status": "SUCCESS", "data": res}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

@app.get("/learning/teacher/logs")
async def get_teacher_coaching_logs():
    try:
        from learning.teacher_mentor import TeacherMentor
        logs = TeacherMentor.get_coaching_logs()
        return {"status": "SUCCESS", "logs": logs}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


# [STEP 17] Success-Failure Contrastive Learning REST endpoints
class ContrastLearningRequest(BaseModel):
    query: str
    limit: int = 2

@app.post("/learning/contrast/run")
async def run_contrast_learning(req: ContrastLearningRequest):
    try:
        from learning.contrast_learner import ContrastLearner
        res = ContrastLearner.execute_contrast_learning_session(req.query, req.limit)
        return {"status": "SUCCESS", "data": res}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

@app.get("/learning/contrast/logs")
async def get_contrast_learning_logs():
    try:
        from learning.contrast_learner import ContrastLearner
        logs = ContrastLearner.get_contrast_logs()
        return {"status": "SUCCESS", "logs": logs}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)