import os
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# [ENV-FIX-01 2026-07-25] 게이트 환경값을 .env에 고정 — 재시작 휘발 차단.
# 왜 여기인가: 아래 import 사슬이 **모듈 로드 시점에** os.getenv를 읽는다
# (예: engine/hub.py `SPECULATIVE_DRAFT = os.getenv("CCUT_SPECULATIVE", ...)`).
# 그래서 어떤 import보다 먼저 실려야 한다.
# override=False: 이미 프로세스 환경에 있는 값이 이긴다 — 런처(run_backend*.ps1)나
# 수동 지정이 .env보다 우선. .env는 '아무도 안 정했을 때의 진실'이다.
# 로더가 없으면 조용히 넘어가지 않고 이유를 찍는다 (침묵 실패 금지, 헌장 §5).
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
try:
    from dotenv import load_dotenv
    _env_loaded = load_dotenv(_ENV_PATH, override=False)
    print(f"[ENV] .env {'loaded' if _env_loaded else 'not found'}: {_ENV_PATH}")
except Exception as _env_err:
    print(f"[ENV][WARN] .env 로드 실패 — 프로세스 환경변수만 사용: {_env_err}")

import time
import uuid
import logging
import re
import json
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import FastAPI, Depends, BackgroundTasks, UploadFile, File, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse  # [STORY-GATE P2] 403 응답용
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from archive.manager import bams
from archive.models import SourceVideo
from archive.db_models import PublishedTable, ProgramTable, FragmentTable, SourceTable, ProposalTable, ProjectSourceTable, ExportInputTable, ExportResultTable
from database import get_db

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
# [STORAGE-FIX] render_engine 등은 BACKEND_DIR/storage(__file__ 앵커)에 저장하지만
# STORAGE_DIR은 루트 storage를 가리킨다. serve 시 두 경로를 모두 탐색한다.
BACKEND_STORAGE_DIR = (BACKEND_DIR / "storage").resolve()
_STATIC_BASES = [STORAGE_DIR, BACKEND_STORAGE_DIR]


# ═══════════════════════════════════════════════════════════════════
#   [1-b-①] 파괴적 DB 작업 전 스냅샷 헬퍼 (정의만 · 호출 연결은 1-b-③)
# ═══════════════════════════════════════════════════════════════════
import shutil as _shutil
import time as _time
from pathlib import Path as _Path
_SNAPSHOT_DIR = _Path(__file__).resolve().parent / "db_snapshots"
_SNAPSHOT_KEEP = 10
def _snapshot_db_before_destructive(reason: str = "destructive") -> str:
    """파괴적 DB 작업 직전 스냅샷. WAL checkpoint 후 .db 복사. 실패해도 작업 진행(보조)."""
    try:
        from database import engine as _engine
        from sqlalchemy import text as _text
        with _engine.connect() as _c:
            _c.execute(_text("PRAGMA wal_checkpoint(TRUNCATE)"))
            _c.commit()
        _src = _Path(__file__).resolve().parent / "ccut_app.db"
        if not _src.exists():
            print(f"[SNAPSHOT] SKIP — db not found: {_src}")
            return ""
        _SNAPSHOT_DIR.mkdir(exist_ok=True)
        _ts = _time.strftime("%Y%m%d_%H%M%S")
        _dst = _SNAPSHOT_DIR / f"ccut_app_{_ts}_{reason}.db"
        _shutil.copy2(_src, _dst)
        print(f"[SNAPSHOT] created: {_dst.name} (reason={reason})")
        _snaps = sorted(_SNAPSHOT_DIR.glob("ccut_app_*.db"), key=lambda p: p.stat().st_mtime)
        for _old in _snaps[:-_SNAPSHOT_KEEP]:
            try: _old.unlink(); print(f"[SNAPSHOT] pruned: {_old.name}")
            except Exception as _pe: print(f"[SNAPSHOT] prune fail: {_pe}")
        return str(_dst)
    except Exception as _se:
        print(f"[SNAPSHOT] FAILED (non-blocking): {_se}")
        return ""


def get_silence_ratio(audio_path, start, end, threshold_db=-40.0):
    """무음 구간 비율 — 컷 포인트 적합성 신호"""
    try:
        import librosa, numpy as np
        y, sr = librosa.load(audio_path, sr=None, offset=start, duration=max(end-start,0.1))
        if len(y)==0: return 0.0
        rms = librosa.feature.rms(y=y)[0]
        rms_db = librosa.amplitude_to_db(rms, ref=np.max)
        silence_frames = np.sum(rms_db < threshold_db)
        return round(float(silence_frames)/max(len(rms_db),1), 4)
    except Exception:
        return 0.0


def get_motion_blur_score(keyframe_path):
    """카메라 흔들림 정도 — 조각 품질 신호(낮을수록 흐림)"""
    try:
        import cv2
        img = cv2.imread(str(keyframe_path))
        if img is None: return 1.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        score = cv2.Laplacian(gray, cv2.CV_64F).var()
        return round(min(float(score)/100.0, 1.0), 4)
    except Exception:
        return 1.0


def _resolve_static_path(path: str):
    """STORAGE_DIR과 BACKEND_DIR/storage 양쪽에서 파일을 찾는다. 경로탈출 방지."""
    for base in _STATIC_BASES:
        fp = (base / path).resolve()
        if str(fp).startswith(str(base)) and fp.exists() and fp.is_file():
            return fp
    return None


UPLOAD_DIR = STORAGE_DIR / "uploads"
APP_BASE_URL = os.getenv("CCUT_BASE_URL", "http://127.0.0.1:8011").rstrip("/")

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Global Engine Initialization with STORAGE_DIR
video_engine = VideoEngine(storage_path=STORAGE_DIR)
template_resolver = StoryTemplateResolver()


from urllib.parse import quote as _url_quote


def build_static_url(*parts: str) -> str:
    normalized = "/".join(str(p).strip("/\\") for p in parts if p)
    return f"{APP_BASE_URL}/static/{normalized}"


def build_upload_static_url(filename: str) -> str:
    return f"{APP_BASE_URL}/static/uploads/{_url_quote(filename, safe='')}"


def build_export_static_url(filename: str) -> str:
    return build_static_url("exports", filename)


def build_dubbing_static_url(filename: str) -> str:
    return build_static_url("dubbing", filename)


app = FastAPI()


@app.on_event("startup")
async def _startup_watchdog():
    # [A-4] 시작 시 파이프라인 자가진단
    try:
        from engine.pipeline_watchdog import run_watchdog
        run_watchdog()
    except Exception as _wd_e:
        print(f"[WATCHDOG] 초기 진단 실패 (non-blocking): {_wd_e}")


def _run_db_migrations():
    """export_results 테이블에 program_id/program_title 컬럼 추가 (SQLite ALTER TABLE)"""
    import sqlite3
    db_path = str(Path(__file__).parent / "ccut_app.db")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(export_results)")
        cols = {row[1] for row in cur.fetchall()}
        if "program_id" not in cols:
            cur.execute("ALTER TABLE export_results ADD COLUMN program_id TEXT")
            print("[MIGRATION] export_results.program_id 컬럼 추가")
        if "program_title" not in cols:
            cur.execute("ALTER TABLE export_results ADD COLUMN program_title TEXT")
            print("[MIGRATION] export_results.program_title 컬럼 추가")
        if "display_name" not in cols:
            # [EXPORT-NAME-SNAPSHOT] 제안 재생성으로 proposal_id가 사라져도
            # 이름이 유실되지 않게 — export 시점에 이름을 스냅샷으로 박아 넣는다
            # (조인 → 스냅샷). null 컬럼이면 하위호환 폴백(조인)으로 계속 동작.
            cur.execute("ALTER TABLE export_results ADD COLUMN display_name TEXT")
            print("[MIGRATION] export_results.display_name 컬럼 추가")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[MIGRATION] export_results 마이그레이션 실패: {e}")

_run_db_migrations()

# [ADMIN v0] 관리자 콘솔 테이블 — startup 자동 생성 (CREATE IF NOT EXISTS, 실패 비차단)
try:
    from admin import service as _admin_service
    _admin_service.ensure_schema()
    print("[ADMIN] admin tables ensured (audit_log/saved_queries/daily_metrics)")
except Exception as _admin_e:
    print(f"[ADMIN] schema ensure 실패 (non-blocking): {_admin_e}")

try:
    from learning.learning_models import init_learning_db
    init_learning_db()
    print("[LEARNING] learning tables ensured (weak_labels/user_edit_decisions 등 6종)")
except Exception as _learning_e:
    print(f"[LEARNING] schema ensure 실패 (non-blocking): {_learning_e}")

# [기초층 §8] DB 자동 순환 백업 — 최소 백업 단위는 DB 1파일(말의 원장·편성일지·
# 계보 전부 포함, MB급). 시작 시 sqlite backup API로 backups/에 7개 순환.
# 수동 .bak 난립(실측 39개)의 제도적 대체. 실패 비차단.
def _auto_db_backup(keep: int = 7):
    import sqlite3 as _s
    try:
        db_path = str(Path(__file__).parent / "ccut_app.db")
        bdir = Path(__file__).parent / "backups"
        bdir.mkdir(exist_ok=True)
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        dst_path = bdir / f"ccut_app.{stamp}.db"
        src = _s.connect(db_path)
        dst = _s.connect(str(dst_path))
        src.backup(dst)
        dst.close(); src.close()
        olds = sorted(bdir.glob("ccut_app.*.db"))
        for old in olds[:-keep]:
            old.unlink()
        print(f"[BACKUP] DB 순환 백업: {dst_path.name} (보관 {min(len(olds), keep)}개)")
    except Exception as e:
        print(f"[BACKUP] 자동 백업 실패 (non-blocking): {e}")

_auto_db_backup()

# [서사층 v2.1] 말의 원장·촬영일 스키마 보장 + 멱등 백필 (가볍게 — NULL만)
try:
    from engine import narrative_ledger as _nl
    import sqlite3 as _sq3
    _con0 = _sq3.connect(str(Path(__file__).parent / "ccut_app.db"))
    _nl.ensure_schema(_con0)
    _cols0 = {r[1] for r in _con0.execute("PRAGMA table_info(sources)").fetchall()}
    if "display_name" not in _cols0:
        _con0.execute("ALTER TABLE sources ADD COLUMN display_name TEXT")
        _con0.commit()
    _con0.close()
    _nl.backfill_shot_dates()
    _nl.backfill_intake_notes_from_timeline()
except Exception as _nl_e:
    print(f"[NARRATIVE] 초기화 실패 (non-blocking): {_nl_e}")

# [조각 금고 v2.2] 스키마 보장만 — 실제 적재는 조각화 완료 시점(증분 훅)에서만
# 일어난다. 전량 backfill을 부팅 동기 경로에 두면 sources가 커질수록(현재 68건)
# 시작 지연·DB 점유가 선형으로 자라 항상성 원칙과 충돌한다는 지적을 반영해 제거.
# 과거분 적재는 필요 시 tools/vault_backfill.py를 수동/스케줄 실행으로 분리.
try:
    from engine import fragment_vault as _fv
    _fv_con = __import__("sqlite3").connect(str(Path(__file__).parent / "ccut_app.db"))
    _fv.ensure_schema(_fv_con)
    _fv_con.close()
except Exception as _fv_e:
    print(f"[VAULT] 스키마 보장 실패 (non-blocking): {_fv_e}")

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
        # [CACHE-BUST] 같은 URL이라도 파일 변경 시 새로 받도록 재검증 강제
        "Cache-Control": "no-cache",
    }

    return StreamingResponse(
        range_generator(),
        status_code=206,
        headers=headers,
        media_type=content_type
    )

import re as _re_pano
_PANO_FRAME_RE = _re_pano.compile(r'thumbnails/P_.+_\d+\.jpg$')

async def _wait_for_panorama_frame(path: str, timeout: float = 6.0, interval: float = 0.15):
    """P_ 파노라마 프레임이 아직 추출 중이면 잠깐 기다렸다 제공 — 404 레이스 원천 차단(프론트 무관)."""
    if not _PANO_FRAME_RE.search(path):
        return None
    import asyncio
    waited = 0.0
    while waited < timeout:
        await asyncio.sleep(interval)
        waited += interval
        fp = _resolve_static_path(path)
        if fp is not None:
            return fp
    return None


@app.get("/static/{path:path}")
async def serve_static_range(path: str, request: Request):
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    full_path = _resolve_static_path(path)
    if full_path is None:
        full_path = await _wait_for_panorama_frame(path)
    if full_path is None:
        raise HTTPException(status_code=404, detail="File not found")

    ext = full_path.suffix.lower()
    if ext in (".mp4", ".webm", ".mov", ".ogg"):
        return get_video_range_response(full_path, request)
    return FileResponse(full_path)

@app.get("/api/static/{path:path}")
async def serve_api_static_range(path: str, request: Request):
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    full_path = _resolve_static_path(path)
    if full_path is None:
        full_path = await _wait_for_panorama_frame(path)
    if full_path is None:
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

from routers.health import router as health_router  # [REFACTOR] 저위험 health/debug 분리
app.include_router(health_router)

# [EDIT-CONTRACT-B0 IMPL-2] 공통 편집 계약 API — EDIT_CONTRACT_V2 게이트 OFF 시 쓰기 완전 0
from edit_contract.api import router as edit_contract_router
app.include_router(edit_contract_router)

# [STORY-GATE P2] 스토리 승인 관문 — CCUT_STORY_GATE OFF 시 쓰기 완전 0
from story_gate.api import router as story_gate_router
from story_gate import gate as story_gate
from story_gate import service as story_service
app.include_router(story_gate_router)

# [LEDGER-1] Text Ledger R0 — 스토리 원고 read API (읽기 전용, DB 무변)
from ledger_r0 import router as ledger_router
app.include_router(ledger_router)

# User-triggered fragment-only forced alignment. No background work and no DB writes.
from precision_alignment.api import router as precision_alignment_router
app.include_router(precision_alignment_router)

# [MIRROR Phase 2] Deterministic verdict notebook. Writes facts only.
from mirror_ledger import router as mirror_ledger_router, ensure_schema as _mirror_ledger_ensure_schema
app.include_router(mirror_ledger_router)
try:
    _mirror_ledger_ensure_schema()
    print("[MIRROR] mirror_ledger table ensured")
except Exception as _mirror_e:
    print(f"[MIRROR] schema ensure failed (non-blocking): {_mirror_e}")

# [PROPOSAL-AXIS-01 1-1] proposals.story_approval_id / technique_id 보장 (ADD COLUMN만).
# 기동 시점이어야 한다: ORM 모델에는 컬럼이 있는데 테이블에 없으면 **읽기(SELECT)부터**
# 깨진다 — 실측: GET /proposals/project/{id}/sources 가 500
# (sqlite3.OperationalError: no such column: proposals.story_approval_id).
try:
    from story_gate.proposal_axis import ensure_columns as _axis_ensure_columns
    _axis_added = _axis_ensure_columns()
    print(f"[PROPOSAL-AXIS] proposals columns ensured (added={_axis_added})")
except Exception as _axis_e:
    print(f"[PROPOSAL-AXIS] column ensure failed (non-blocking): {_axis_e}")

# [아카이브 채팅 MVP] read-only 자연어 조회 라우터 — proposal_engine/route-edit와 완전 분리
from archive_chat_router import router as archive_chat_router, ensure_schema as _archive_chat_ensure_schema
app.include_router(archive_chat_router)
try:
    _archive_chat_ensure_schema()
    print("[ARCHIVE-CHAT] archive_result_sets 테이블 보장")
except Exception as _ac_e:
    print(f"[ARCHIVE-CHAT] 스키마 보장 실패 (non-blocking): {_ac_e}")

# [아카이브 바구니 내보내기 MVP] 바구니 조각 → 표준 MP4 클립 export (파일 쓰기, proposal 무관)
from archive_export_router import router as archive_export_router
app.include_router(archive_export_router)

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


# [REFACTOR] /health · /pipeline/status · /system/diagnostics → routers/health.py


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
        original_name = Path(file.filename).name if file.filename else "upload.mp4"
        ext = Path(original_name).suffix.lower() or ".mp4"
        print(f"[DEBUG] /upload request received: filename={original_name}")

        # 임시 파일명으로 먼저 저장 (fingerprint 계산 후 source_id 기반으로 rename)
        tmp_name = f"_tmp_{uuid.uuid4().hex[:12]}{ext}"
        tmp_path = UPLOAD_DIR / tmp_name
        with open(tmp_path, "wb") as buf:
            while chunk := await file.read(1024 * 1024):
                buf.write(chunk)

        tmp_abs = str(tmp_path.resolve())

        # [STEP 1] Fingerprint 생성 및 중복 확인
        fingerprint = video_engine.generate_fingerprint(tmp_abs)

        existing = bams.get_source_by_hash(fingerprint)
        if existing and not existing.file_path:
            existing = None   # file_path=None 레코드 → 신규 저장 경로로 처리
        source_id = None
        if existing:
            # 중복 → 임시 파일 삭제, 기존 source 재사용
            try:
                tmp_path.unlink()
            except Exception:
                pass
            source_id = existing.source_id
            existing_name = Path(existing.file_path).name
            existing_url = f"/static/uploads/{_url_quote(existing_name, safe='')}"
            print(f"[UPLOAD] Fingerprint HIT: {fingerprint} -> source_id={source_id}")

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
                    background_tasks.add_task(_background_whisper, source_id, existing.file_path, fragments)
                    background_tasks.add_task(_background_signal_analysis, source_id, existing.file_path, fragments)
                    return {
                        "status": "SOURCE_REUSED_REANALYSIS_STARTED",
                        "file_name": original_name,
                        "source_id": source_id,
                        "hash_value": fingerprint,
                        "cache_hit": True,
                        "reused": True,
                        "reanalysis": True,
                        "quality": quality,
                        "static_url": existing_url,
                    }

            return {
                "status": "SOURCE_REUSED",
                "file_name": original_name,
                "source_id": source_id,
                "hash_value": fingerprint,
                "cache_hit": True,
                "reused": True,
                "static_url": existing_url,
            }

        # 신규 소스 — source_id 기반 파일명으로 rename (URL-safe 보장)
        source_id = f"SRC_{uuid.uuid4().hex[:8].upper()}"
        safe_filename = f"{source_id}{ext}"
        final_path = UPLOAD_DIR / safe_filename
        tmp_path.rename(final_path)
        abs_path = str(final_path.resolve())
        _upload_registry[source_id] = abs_path

        _fragment_job_registry[source_id] = {
            "status": "PENDING",
            "progress": 0,
            "source_id": source_id,
            "error": None,
            "timing": init_job_timing()
        }
        _fragment_job_registry[source_id]["timing"]["upload_start"] = time.time()

        source_data = {
            "source_id": source_id,
            "file_path": abs_path,
            "title": original_name,   # 원본 파일명은 title에만 보관
            "duration": 0.0,
            "hash_value": fingerprint
        }
        bams.register_source(source_data)

        print(f"[UPLOAD] 신규 저장 완료: {original_name} → {safe_filename} (source_id={source_id})")

        return {
            "status": "SOURCE_CREATED",
            "file_name": original_name,
            "source_id": source_id,
            "hash_value": fingerprint,
            "cache_hit": False,
            "reused": False,
            "static_url": f"/static/uploads/{safe_filename}",
        }
    except Exception as e:
        import traceback
        print(f"[CRITICAL] /upload error: {str(e)}")
        traceback.print_exc()
        return {"status": "ERROR", "message": str(e)}


# ═══════════════════════════════════════════════════════════════════
#   Background jobs
# ═══════════════════════════════════════════════════════════════════

import threading
_ASR_SEMAPHORE = threading.Semaphore(2)  # ASR 동시 실행 제한 — 68개 동시 경합 폭발 방지

# ── [AUTO-REINDEX] 재조각화 → fragment_index 자동 재구축 훅 (env 가역) ──
#  근거: 재조각화가 SF fragment_id를 재발급하면 옛 id로 키잉된 fragment_index가
#  고아화 → hub judge(P3)에 scene 빈 값 도착 (2026-07-02 EVIDENCE 확정).
#  - CCUT_AUTO_REINDEX=1 일 때만 동작. 미설정/0 = 완전 무변(G-flag).
#  - SF (재)생성 완료 직후 백그라운드 스레드 발사 → 응답 블로킹 0(G-bg).
#  - 동일 source in-flight 가드: 중복 요청은 스킵 로그만 남긴다.
_auto_reindex_inflight = set()
_auto_reindex_lock = threading.Lock()


def _auto_reindex_fire(source_id: str):
    """SF (재)생성 완료 지점에서 호출. env off면 no-op."""
    if os.getenv("CCUT_AUTO_REINDEX", "0") not in ("1", "true", "True"):
        return
    with _auto_reindex_lock:
        if source_id in _auto_reindex_inflight:
            print(f"[AUTO-REINDEX] skip (in-flight): {source_id}")
            return
        _auto_reindex_inflight.add(source_id)

    def _worker():
        try:
            try:
                from engine.fragment_indexer import reindex_source
                reindex_source(source_id)
            except Exception as e:
                print(f"[AUTO-REINDEX][ERROR] source={source_id}: {e}")
                return
            # [PERSON-RELINK] 게이트 값 raw 출력 — 미발화가 침묵으로 묻히지 않게.
            _relink = os.getenv("CCUT_PERSON_RELINK", "0")
            print(f"[PERSON-RELINK] gate CCUT_PERSON_RELINK={_relink!r} source={source_id}", flush=True)
            if _relink in ("1", "true", "True"):
                from engine import face_palette as _fp
                # [C2 선행 재배선 2026-07-04] 재인덱싱이 지운 태그를 scan보다 먼저 복원.
                # 근거: worker 내 scan이 데드락으로 정지해 뒤에 있던 reinject까지 묻힌
                # RUNTIME 실증(:8011/:8012). scan 실패·정지·스킵이 태그 복원을 못 막게
                # 단계를 분리하고 각 단계에 start/done 로그를 남긴다.
                try:
                    print(f"[PERSON-RELINK] stage=reinject start source={source_id}", flush=True)
                    _n = _fp.reinject_names_for_source(source_id)
                    print(f"[PERSON-RELINK] stage=reinject done source={source_id} tagged={_n}", flush=True)
                except Exception as e:
                    print(f"[PERSON-RELINK][ERROR] stage=reinject source={source_id}: {e}", flush=True)
                # [C3 보조] 재조각화로 링크 자체가 끊긴 새 조각의 재링크(+C1 태그).
                # 정지·실패해도 위 reinject 결과는 이미 확보됨.
                try:
                    print(f"[PERSON-RELINK] stage=scan start source={source_id}", flush=True)
                    import sqlite3 as _sq3
                    _con = _sq3.connect(_fp.DB_PATH)
                    _pids = [r[0] for r in _con.execute(
                        "SELECT program_id FROM project_sources WHERE source_id=?",
                        (source_id,))]
                    _con.close()
                    for _pid in _pids:
                        print(f"[PERSON-RELINK] stage=scan project={_pid} start", flush=True)
                        _fp.scan_project(_pid)
                        print(f"[PERSON-RELINK] stage=scan project={_pid} done", flush=True)
                    # scan이 만든 신규 링크의 태그 보강 재주입 (append-only 멱등)
                    print(f"[PERSON-RELINK] stage=reinject2 start source={source_id}", flush=True)
                    _n2 = _fp.reinject_names_for_source(source_id)
                    print(f"[PERSON-RELINK] stage=reinject2 done source={source_id} tagged={_n2}", flush=True)
                except Exception as e:
                    print(f"[PERSON-RELINK][ERROR] stage=scan source={source_id}: {e}", flush=True)
        finally:
            with _auto_reindex_lock:
                _auto_reindex_inflight.discard(source_id)

    threading.Thread(target=_worker, daemon=True,
                     name=f"auto-reindex-{source_id}").start()

def _background_whisper(source_id: str, video_path: str, fragments: list):
    try:
        _background_whisper_impl(source_id, video_path, fragments)
    except Exception as outer_err:
        print(f"[ASR BG] Outer error occurred: {outer_err}")
        if source_id in _fragment_job_registry:
            _fragment_job_registry[source_id]["status"] = "FAILED"
            _fragment_job_registry[source_id]["error"] = str(outer_err)

def _background_whisper_impl(source_id: str, video_path: str, fragments: list):
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
        print(f"[ASR BG] {source_id} - 조각 없음")
        if source_id in _fragment_job_registry:
            _fragment_job_registry[source_id]["status"] = "FAILED"
            _fragment_job_registry[source_id]["error"] = "No fragments to analyze"
        return

    try:
        total_duration = max(float(f.get("end_time", 0)) for f in fragments)
        # [단계1] ASR 이전 사전 프로파일링 — ffmpeg 직접 측정 (DB 의존 없음)
        import os as _os
        from engine.signal_processor import (
            SignalProcessor as _SP,
            pre_profile_source as _pps,
            profile_source as _ps,
        )

        _total_dur = max(
            (float(f.get("end_time", 0) or 0) for f in fragments), default=0.0
        )
        try:
            _full_rms = float(_SP(video_path).get_rms_energy(0.0, _total_dur))
            _rms_list = [_full_rms]
        except Exception as _e:
            print(f"[PRE_PROFILE] RMS 측정 실패 — pending 처리: {_e}")
            _rms_list = []  # pre_profile이 pending 반환 (static 오판 금지)

        _scene_changes = []
        for _f in fragments:
            _sc = (_f.get("intelligence") or {}).get("scene_change")
            if _sc is None:
                _sc = _f.get("scene_change")
            if isinstance(_sc, list):
                _scene_changes.extend(_sc)

        _pre = _pps(
            audio_energies=_rms_list,
            scene_changes=_scene_changes,
            duration_sec=_total_dur,
        )
        print(f"[PRE_PROFILE] {source_id} -> {_pre}")

        _enforce = _os.getenv("CCUT_PROFILE_ENFORCE", "1") == "1"
        if _pre.get("profile") == "static" and _enforce:
            print(f"[PRE_PROFILE] {source_id} static 확정 — ASR 스킵 (ENFORCE)")
            _ps(
                source_id=source_id,
                all_words=[],
                scene_changes=_scene_changes,
                audio_energies=_rms_list,
                duration_sec=_total_dur,
                pre=_pre,
            )
            if source_id in _fragment_job_registry:
                _fragment_job_registry[source_id]["status"] = "DONE"
                _fragment_job_registry[source_id]["stage"] = "static_source"
            return
        elif _pre.get("profile") == "static":
            print(f"[PRE_PROFILE] {source_id} static 판정 — DRY-RUN: ASR 계속 진행")

        with _ASR_SEMAPHORE:
            whisper_res    = asr.transcribe_fragments(video_path, fragments)
        
        transcripts  = whisper_res.get("fragment_transcripts", {})
        all_segments = whisper_res.get("all_segments", [])
        fragment_words = whisper_res.get("fragment_words", {})
        provider = whisper_res.get("provider", "whisper")
        provider_error = whisper_res.get("provider_error")
        rejected_fragments = whisper_res.get("rejected_fragments", {})

        # [단계2] 경계 스냅 보정 — 발화 휴지 정렬 (기본 dry-run)
        _all_words = whisper_res.get("words", []) or []
        if _all_words:
            from engine.signal_processor import refine_boundaries_to_words

            def _recompute_overlap(_frag, _segments):
                _s = float(_frag.get("start_time", 0))
                _e = float(_frag.get("end_time", 0))
                _parts, _ws = [], []
                for _seg in _segments:
                    if float(_seg["end"]) <= _s or float(_seg["start"]) >= _e:
                        continue
                    _parts.append(_seg.get("text", ""))
                    _ws.extend(_seg.get("words", []) or [])
                return " ".join(_parts).strip(), _ws

            _props = refine_boundaries_to_words(fragments, _all_words)
            _snapped = [p for p in _props if p["snapped"]]
            if _snapped:
                _avg = sum(abs(p["shift"]) for p in _snapped) / len(_snapped)
                print(f"[BOUNDARY_SNAP] {source_id} 경계 {len(_props)}개 중 "
                      f"{len(_snapped)}개 스냅 가능, 평균 이동 {_avg:.2f}s")
                for _p in _snapped:
                    print(f"[BOUNDARY_SNAP]   {_p['left_id']} | "
                          f"{_p['old_boundary']} -> {_p['new_boundary']} "
                          f"(shift {_p['shift']:+.2f}s, gap {_p['gap_len']:.2f}s)")
            else:
                print(f"[BOUNDARY_SNAP] {source_id} 스냅 가능 경계 없음")

            if _os.getenv("CCUT_SNAP_ENFORCE", "0") == "1" and _snapped:
                _by_id = {f["fragment_id"]: f for f in fragments}
                _touched = set()
                for _p in _snapped:
                    _l = _by_id.get(_p["left_id"])
                    _r = _by_id.get(_p["right_id"])
                    if not _l or not _r:
                        continue
                    _nb = float(_p["new_boundary"])
                    _l["end_time"] = _nb
                    _l["duration"] = round(_nb - float(_l["start_time"]), 3)
                    _r["start_time"] = _nb
                    _r["duration"] = round(float(_r["end_time"]) - _nb, 3)
                    _touched.update([_p["left_id"], _p["right_id"]])

                try:
                    _fps = float(video_engine.get_metadata(video_path).get("fps", 30.0)) or 30.0
                except Exception:
                    _fps = 30.0

                for _fid in _touched:
                    _f = _by_id[_fid]
                    _f["start_frame"] = int(round(float(_f["start_time"]) * _fps))
                    _f["end_frame"] = int(round(float(_f["end_time"]) * _fps))
                    _t, _w = _recompute_overlap(_f, all_segments)
                    transcripts[_fid] = _t
                    fragment_words[_fid] = _w
                    bams.update_fragment_boundary(
                        _fid,
                        float(_f["start_time"]),
                        float(_f["end_time"]),
                    )
                print(f"[BOUNDARY_SNAP] {source_id} {len(_touched)}개 조각 "
                      f"적용 완료 (ENFORCE)")

        # [R14] Read current model_size from config.yaml for metadata persistence
        # [GPU-LIVE fix] 하드코딩 'whisper' → active.asr provider 참조 (whisper_vulkan 시 small 반영)
        import yaml as _yaml
        _config_path = os.path.join(os.path.dirname(__file__), "ai", "config.yaml")
        try:
            with open(_config_path, encoding="utf-8") as _f:
                _cfg = _yaml.safe_load(_f)
            _active_asr = _cfg.get("active", {}).get("asr", "whisper")
            current_model_size = (
                _cfg.get("providers", {})
                    .get(_active_asr, {})
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
            frag["intelligence"]["silence_ratio"] = get_silence_ratio(video_path, frag["start_time"], frag["end_time"])

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
        _auto_reindex_fire(source_id)  # [AUTO-REINDEX] SF 재생성 완료 → 인덱스 재구축 (env 가역, 비블로킹)

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
            
        # [A-2] subtitles 캐시 저장
        try:
            from archive.db_models import SubtitleTable
            from database import SessionLocal
            import json as _json
            with SessionLocal() as _db:
                _existing = _db.query(SubtitleTable).filter_by(
                    source_id=source_id).first()
                if not _existing:
                    _sub = SubtitleTable(
                        subtitle_id=f"SUB_{source_id}",
                        source_id=source_id,
                        language=provider or "unknown",
                        segments=_json.dumps(all_segments or []),
                        status="COMPLETE",
                    )
                    _db.add(_sub)
                    _db.commit()
                    print(f"[SUBTITLES] {source_id} 저장 완료 "
                          f"segments={len(all_segments or [])}")
                else:
                    print(f"[SUBTITLES] {source_id} 이미 존재 — skip")
        except Exception as _sub_e:
            print(f"[SUBTITLES] 저장 실패 (non-blocking): {_sub_e}")

        # [A-3] quick_scan 실행 (non-blocking)
        try:
            from engine.hypothesis_engine import HypothesisEngine
            _he = HypothesisEngine()
            _qs = _he.generate_quick_scan(source_id)
            print(f"[QUICK_SCAN] {source_id} 완료: "
                  f"{list(_qs.keys()) if _qs else 'empty'}")
        except Exception as _qs_e:
            print(f"[QUICK_SCAN] 실패 (non-blocking): {_qs_e}")

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
                existing_intelligence["motion_blur"] = get_motion_blur_score(thumb_path)

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

    # [SIGNAL-WAKE-1] 소스당 1회만 계산해 조각으로 접는다 (조각마다 재추출 금지).
    #   motion_score: 생산함수·저장컬럼·소비처가 이미 있는데 배선만 끊겨 256/256 전부 0이었다.
    #   audio_beat  : 저장은 기존 metadata_json JSON 컬럼 (스키마 변경 0).
    _src_end = max((f.get("start_time", 0.0) + f.get("duration", 0.0)) for f in fragments) if fragments else 0.0
    try:
        from engine.signal_processor import extract_motion_curve, motion_scores_for_spans, beat_times
        _curve = extract_motion_curve(video_path, _src_end)
        _spans = [(f["start_time"], f["start_time"] + f["duration"]) for f in fragments]
        _motions = motion_scores_for_spans(video_path, _src_end, _spans, curve=_curve)
        _beats = beat_times(video_path, _src_end)
        print(f"[SIGNAL BG] motion curve={len(_curve)} samples, beats={len(_beats)}")
    except Exception as _sw:
        print(f"[SIGNAL BG] motion/beat 추출 실패 (비차단): {_sw}")
        _motions = [None] * len(fragments)
        _beats = []

    for _i, frag in enumerate(fragments):
        fid = frag["fragment_id"]
        start = frag["start_time"]
        dur = frag["duration"]

        try:
            # 1. 오디오 에너지(RMS) 추출
            energy = sp.get_rms_energy(start, dur)

            # 2. Evidence Board 필드 병합 (Field-level merge)
            _payload = {
                "source_id": source_id,
                "worker_name": "audio",
                "start": start,
                "end": start + dur,
                "audio_energy": energy,
                "confidence": 0.8
            }
            # [SIGNAL-WAKE-1] 값이 있을 때만 싣는다 — None을 0으로 위장하지 않는다.
            _m = _motions[_i] if _i < len(_motions) else None
            if _m is not None:
                _payload["motion_score"] = _m
            _bin = [t for t in _beats if start <= t < start + dur]
            if _bin:
                _payload["metadata_json"] = {"audio_beat": _bin}
            bams.update_evidence(fid, _payload)
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
    force: bool = False,
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
        # [GHOST-CLEANUP 1호] 분석됨 판정의 진실원 = SF (VF는 파생 재료일 뿐 —
        # 옛 VF 지층만 남은 소스가 새 분석을 영구 차단하던 관문 절단)
        from archive.db_models import SemanticFragmentTable as _SFT
        existing_frags = bams.get_fragments_by_source(source_id)
        _has_sf = db.query(_SFT).filter_by(source_id=source_id).count() > 0
        is_new_source = not (existing_frags and _has_sf)
        if is_new_source and existing_frags:
            # 옛 VF 지층 제거 — 신규 경로의 VF 재생성(결정론 id)과 PK 충돌 방지
            db.query(FragmentTable).filter_by(source_id=source_id, status="VIRTUAL").delete()
            db.commit()

        # [DURATION-MISMATCH-FIX] DB duration과 실제 duration이 5초 이상 차이나거나
        # semantic_fragments가 없으면 → VIRTUAL fragments + semantic_fragments 초기화 후 재분석
        if not is_new_source and not meta.get("mock"):
            from archive.db_models import SemanticFragmentTable as _SFT
            src_row = db.query(SourceTable).filter_by(source_id=source_id).first()
            db_dur = float(src_row.duration or 0) if src_row else 0.0
            has_semantic = db.query(_SFT).filter_by(source_id=source_id).count() > 0
            need_reanalyze = force or abs(db_dur - total_duration) > 5.0 or not has_semantic
            if need_reanalyze:
                reason = f"duration_mismatch(db={db_dur:.1f}s actual={total_duration:.1f}s)" if abs(db_dur - total_duration) > 5.0 else "semantic_fragments_missing"
                print(f"[REANALYZE] source_id={source_id} reason={reason}")
                db.query(FragmentTable).filter_by(source_id=source_id, status="VIRTUAL").delete()
                db.query(_SFT).filter_by(source_id=source_id).delete()
                if src_row:
                    src_row.duration = total_duration
                db.commit()
                existing_frags = []
                is_new_source = True

    # [STEP 1] Proxy 생성 (분석용 저용량 영상)
    proxy_path = video_engine.create_proxy(resolved_path, source_id)
    # [FIX-HEVC-PLAYBACK] 업로드 시 playback sidecar 사전생성
    video_engine.create_playback_proxy(resolved_path)

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
            triggers = []
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
            "fragments": _inject_display_names(fragments, source_id),
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
                "fragments": _inject_display_names(safe_fragments, source_id),
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
        "fragments": _inject_display_names(safe_fragments, source_id),
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
        "fragments": _inject_display_names(fragments, source_id)
    }

class ChatSearchRequest(BaseModel):
    message: str
    top_k: Optional[int] = 12
    only_curated: Optional[bool] = False
    program_id: Optional[str] = None


@app.get("/fragment-search")
async def search_fragments(q: str, top_k: int = 12, only_curated: bool = False,
                           source_id: Optional[str] = None, role: Optional[str] = None):
    """[FRAGMENT-SEARCH] 조각 자연어 검색.
    "영국 비오는날 중년 아저씨" -> 관련 조각 목록 (시맨틱 + FTS5 하이브리드).
    경로는 /fragments/{source_id} 와의 충돌을 피하려 /fragment-search 사용.
    """
    from engine import fragment_search as fsx
    try:
        result = fsx.search(q, top_k=top_k, only_curated=only_curated,
                            source_id=source_id, role=role)
        return {"status": "SUCCESS", **result}
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "query": q, "count": 0, "results": []}


@app.post("/chat/fragment-search")
async def chat_fragment_search(req: ChatSearchRequest):
    """[FRAGMENT-SEARCH] 채팅 메시지에서 검색 의도/쿼리 추출 후 조각 검색.
    검색 의도가 아니면 is_search=False 반환 (프론트가 기존 채팅 흐름으로 위임).
    """
    from engine import fragment_chat as fcx
    from engine import fragment_search as fsx
    intent = fcx.detect(req.message)
    if not intent["is_search"]:
        return {"status": "SUCCESS", "is_search": False, "query": "",
                "count": 0, "results": []}
    try:
        result = fsx.search(intent["query"], top_k=req.top_k or 12,
                            only_curated=bool(req.only_curated))
        return {"status": "SUCCESS", "is_search": True,
                "query": intent["query"], "confidence": intent["confidence"],
                "count": result["count"], "results": result["results"]}
    except Exception as e:
        return {"status": "ERROR", "is_search": True, "error": str(e),
                "query": intent["query"], "count": 0, "results": []}


@app.get("/fragment-search-status")
async def fragment_search_status():
    """[FRAGMENT-SEARCH] 인덱스 현황."""
    from engine import fragment_search as fsx
    return {"status": "SUCCESS", **fsx.index_status()}


@app.post("/proposals/{proposal_id}/preview")
async def make_proposal_preview(proposal_id: str, db: Session = Depends(get_db)):
    """[PROPOSAL-PREVIEW] 제안을 즉석 렌더(또는 캐시)하여 재생용 mp4 반환.
    제안 sequence -> clips -> ensure_proposal_preview(+faststart, 캐시).
    모든 제안 재생 가능 (내보내기 불필요).
    """
    import json as _j
    pr = db.query(ProposalTable).filter_by(proposal_id=proposal_id).first()
    if not pr:
        return {"status": "NOT_FOUND", "preview_url": None}
    seq = pr.sequence
    if isinstance(seq, str):
        try:
            seq = _j.loads(seq)
        except Exception:
            seq = []
    variant = (pr.mode or "A").upper()
    clips = []
    for frag in (seq or []):
        sid = frag.get("source_id") or ""
        start = float(frag.get("start") or frag.get("start_sec") or frag.get("start_time") or 0.0)
        end = float(frag.get("end") or frag.get("end_sec") or frag.get("end_time") or 0.0)
        if not sid or end <= start:
            continue
        sdata = bams.get_source(sid)
        spath = sdata.file_path if sdata else None
        if not spath or not os.path.exists(spath):
            continue
        clips.append({"source_path": spath, "start": start, "end": end})
    if not clips:
        return {"status": "NO_CLIPS", "preview_url": None}
    # [STORY-GATE P2 / I-1] 승인 없이는 렌더 산출물을 만들지 않는다.
    # 게이트 OFF면 이 검사 자체가 없다 (현행 무변).
    if story_gate.is_enabled() and pr.program_id and not story_service.is_render_allowed(pr.program_id):
        return JSONResponse(status_code=403, content={
            "status": "STORY_NOT_APPROVED", "preview_url": None,
            "error": "STORY_NOT_APPROVED", "program_id": pr.program_id,
            "message": "이야기가 아직 승인되지 않았습니다. 원고를 확인하고 승인해 주세요.",
        })
    from engine.proposal_preview_engine import ensure_proposal_preview
    result = ensure_proposal_preview(proposal_id=proposal_id, variant=variant, clips=clips)
    return {
        "status": result.get("status", "UNKNOWN"),
        "preview_url": result.get("preview_url"),
        "duration": result.get("duration", 0.0),
    }


@app.get("/punch/{program_id}")
async def get_punch_specs(program_id: str):
    """[PUNCH-1 R1] 승인 스냅샷 조각들의 펀치인 지점·배율 — **계산 결과, 저장하지 않는다**.

    화면 재생(조각맵 파생)은 렌더된 preview mp4를 쓰지 않는다(확정 후 previewUrl=null,
    CenterPanel.tsx:1015). 그래서 ffmpeg 줌 필터가 국장 화면에 도달하지 못했다.
    같은 punch_spec을 프론트에 그대로 넘겨 화면 변환으로 걸면 재생·렌더·export가
    같은 시각·같은 배율을 쓴다 — 기법 진실은 여전히 하나(proposal_axis.punch_spec).
    """
    try:
        from story_gate import proposal_axis as _axis
        _appr_id, _appr_fids = _axis.live_approval_snapshot(program_id)
        if _appr_id is None or not _appr_fids:
            return {"ok": True, "program_id": program_id, "approval_id": None, "specs": {}}
        _axis.reset_punch_caches()      # config가 바뀌었을 수 있다 — 매 요청 최신값을 읽는다
        _cfg = _axis.punch_config()
        specs, rules = {}, {}
        for _f in _appr_fids:
            sp = _axis.punch_spec(_f)
            if sp:
                specs[_f] = {"at": sp["at"], "zoom": sp["zoom"], "basis": sp["basis"]}
        return {
            "ok": True, "program_id": program_id, "approval_id": _appr_id,
            # [RULE-1 R4] 규칙 값의 출처는 config JSON 하나. 프론트도 그 값을 그대로 쓴다.
            "config": _cfg,
            "ramp_sec": (_cfg or {}).get("ramp_sec"),
            "mode_technique": _axis.MODE_TECHNIQUE,
            "count": len(specs), "specs": specs,
        }
    except Exception as e:
        print(f"[PUNCH][ERROR] {e}")
        return {"ok": False, "program_id": program_id, "error": str(e), "specs": {}}


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
                extract_sec = max(0, start_frame / fps)
                result_path = video_engine.extract_thumbnail(source_data.file_path, extract_sec, fid)
                if result_path:
                    url = f"/static/thumbnails/{sf_thumb_filename}"
                    f["thumbnail_url"] = url
                    if not isinstance(f.get("thumbnail"), dict): f["thumbnail"] = {}
                    f["thumbnail"]["thumbnail_url"] = url
                    if not isinstance(f.get("intelligence"), dict): f["intelligence"] = {}
                    f["intelligence"]["thumb_url"] = url
                    available_thumbs.add(sf_thumb_filename)
                    continue
                # result_path is None → fall through to VF parent fallback
                print(f"[R42] Thumbnail extraction returned None for {fid}, falling through to VF fallback")
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


def _inject_display_names(fragments: list, source_id: str, title: str = None):
    """[DISPLAY-NAME] 사용자용 조각 주이름 주입 — 단일 권위(fragment_show.display_name).
    조각 payload를 반환하는 API는 전부 이 헬퍼 하나를 거친다(이름을 두 번 만들지 않는다).
    title 미지정 시 sources에서 조회. 실패해도 조용히 통과(표시층 부가정보)."""
    if not fragments:
        return fragments
    if title is None:
        try:
            src = bams.get_source(source_id)
            title = (getattr(src, "title", None) if src else None) or source_id
        except Exception:
            title = source_id
    from engine.fragment_show import display_name as _dn
    for f in fragments:
        if not isinstance(f, dict):
            continue
        st = (f.get("start_sec") or f.get("start") or f.get("start_time")
              or (f.get("semantic") or {}).get("start_sec")
              or (f.get("structural") or {}).get("start_sec") or 0)
        en = (f.get("end_sec") or f.get("end") or f.get("end_time")
              or (f.get("semantic") or {}).get("end_sec")
              or (f.get("structural") or {}).get("end_sec") or st)
        f["display_name"] = _dn(title, st, en)
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


def inject_proposal_previews(proposals: list, edl_clips: list = None) -> list:
    """
    [PROPOSAL_PREVIEW_INJECT] proposals 배열의 각 제안에 preview_url을 주입.
    proposal.sequence -> clips -> ensure_proposal_preview -> preview_url.
    preview_url이 없으면 None (fallback 금지).

    [BOUNDARY-1 B3] edl_clips 가 오면 그것이 경계의 유일한 진실이다.
      구판은 proposal.sequence 의 anchor 좌표를 읽어, 사용자가 자른 trim 과 지운 말
      (excluded_ranges)이 미리보기에 전혀 반영되지 않았다(실측: 4/13 조각에서 갈림).
      EDL 은 재생·export 가 쓰는 바로 그 compile_spans 결과다 — 셋이 같은 값을 본다.
    """
    if not proposals:
        return proposals

    from engine.proposal_preview_engine import ensure_proposal_preview

    def _build_clips_from_edl(p):
        variant     = (p.get("mode") or "A").upper()
        proposal_id = p.get("proposal_id") or p.get("id") or "UNKNOWN"
        clips = []
        for c in edl_clips:
            sid = c.get("source_id") or ""
            source_data = bams.get_source(sid) if sid else None
            source_path = source_data.file_path if source_data else None
            if not source_path or not os.path.exists(source_path):
                print(f"[PROPOSAL_PREVIEW_INJECT] source_path missing for {sid}")
                continue
            s, e = float(c.get("start_sec") or 0.0), float(c.get("end_sec") or 0.0)
            if e <= s:
                continue
            clips.append({"source_path": source_path, "start": s, "end": e,
                          "fragment_id": c.get("fragment_id")})
        return variant, proposal_id, clips

    def _build_clips(p):
        if edl_clips:
            return _build_clips_from_edl(p)
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
            # [PUNCH-1 P4] fragment_id 동봉 — 기법은 조각 단위로 결정된다.
            #   구판은 여기서 조각 정체성이 사라져 미리보기가 기법을 알 수 없었다.
            clips.append({"source_path": source_path, "start": start, "end": end,
                          "fragment_id": frag.get("fragment_id")})
        return variant, proposal_id, clips

    def _apply_result(p, variant, proposal_id, result):
        p["preview_url"]      = result.get("preview_url")
        p["preview_duration"] = result.get("duration", 0.0)
        print(f"[PROPOSAL_PREVIEW_INJECT] {proposal_id}/{variant} status={result['status']} url={p['preview_url']}")

    _parallel = os.getenv("CCUT_PREVIEW_PARALLEL", "0").strip() not in ("", "0", "false", "False")

    if not _parallel:
        # ── 기존 직렬 경로 (동작 무변) ──
        for p in proposals:
            variant, proposal_id, clips = _build_clips(p)
            if not clips:
                p["preview_url"] = None
                print(f"[PROPOSAL_PREVIEW_INJECT] {proposal_id}/{variant}: clips 없음 -> preview_url=None")
                continue
            result = ensure_proposal_preview(proposal_id=proposal_id, variant=variant, clips=clips)
            _apply_result(p, variant, proposal_id, result)
        return proposals

    # ── [P5-2] A/B안 병렬 경로 (clips 빌드는 직렬 DB read, 렌더만 병렬) ──
    import concurrent.futures
    _jobs = []
    for p in proposals:
        variant, proposal_id, clips = _build_clips(p)
        if not clips:
            p["preview_url"] = None
            print(f"[PROPOSAL_PREVIEW_INJECT] {proposal_id}/{variant}: clips 없음 -> preview_url=None")
            continue
        _jobs.append((p, variant, proposal_id, clips))

    if not _jobs:
        return proposals

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(_jobs))) as _ex:
        _fut = {
            _ex.submit(ensure_proposal_preview, proposal_id=pid, variant=var, clips=cl): (p, var, pid)
            for (p, var, pid, cl) in _jobs
        }
        for _f in concurrent.futures.as_completed(_fut):
            _p, _var, _pid = _fut[_f]
            _apply_result(_p, _var, _pid, _f.result())

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
    _auto_reindex_fire(source_id)  # [AUTO-REINDEX] SF 재생성 완료 → 인덱스 재구축 (env 가역, 비블로킹)

    print(f"[SEMANTIC] /semantic-fragments/{source_id} called. Result count: {len(fragments)}")

    # [STEP 10-I.5.22-C] Inject thumbnails
    fragments = inject_semantic_thumbnails(fragments)
    fragments = _inject_display_names(fragments, source_id)  # [DISPLAY-NAME]

    # [조각 금고 v2.2] 재조각화 = 인지를 버리는 순간이었다 → 이제 금고가 이어받는
    # 순간이다. 새 세대 인지를 (hash, 구간) 앵커로 병합 — 옛 인지는 불멸. 비차단.
    try:
        from engine import fragment_vault as _fv2
        _r = _fv2.ingest_source(source_id)
        print(f"[VAULT] 재조각화 승계 {source_id}: +{_r.get('inserted', 0)} 병합 {_r.get('merged', 0)}")
    except Exception as _fv_e:
        print(f"[VAULT] 승계 실패 (비차단): {_fv_e}")

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
        "fragments": _inject_display_names(fragments, source_id)
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
            "mirror": result.mirror,
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
    # [STORY-GATE P1] 렌더 분리 — False면 preview 렌더를 건너뛰고 sequence만 반환한다.
    # 기본 True = 현행 동작 무변 (STORY_GATE_CONTRACT_V1 I-4).
    render_preview: bool = True



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
        # 1. [B-3b-3] 프로젝트 제안을 program_id 기준으로 조회 (신규 구조). 레거시 source_id=proj_ 행은 미조회(C=신규부터)
        props = db.query(ProposalTable).filter_by(program_id=project_id).all()
        # [FIX-RESTORE-SOURCES] project_sources 기반 전수 복원
        ps_rows = (
            db.query(ProjectSourceTable)
            .filter_by(program_id=project_id)
            .order_by(ProjectSourceTable.display_order)
            .all()
        )
        source_ids = [row.source_id for row in ps_rows]
        
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
            else:
                frags = inject_semantic_thumbnails(frags)

            # [DISPLAY-NAME] 단일 권위 주입 — 공용 헬퍼로 수렴 (커밋 A 인라인 대체)
            frags = _inject_display_names(frags, sid, title=src.title or sid)

            # 비디오 URL 변환 — 파일명을 URL 인코딩하여 한글/공백/특수문자 안전 보장
            video_name = os.path.basename(src.file_path) if src.file_path else f"{sid}.mp4"
            # [FIX-HEVC-PLAYBACK] playback sidecar 존재 시 우선 서빙
            _play_name = f"play_{os.path.splitext(video_name)[0]}.mp4"
            _play_full = os.path.join(video_engine.proxies_path, _play_name)
            if os.path.exists(_play_full):
                vurl = f"/static/proxies/{_url_quote(_play_name, safe='')}"
            else:
                vurl = f"/static/uploads/{_url_quote(video_name, safe='')}"

            # [UI-⑨] Label 순서대로 부여 — 엑셀식 (A..Z, AA, AB...) 26 초과 안전
            def _xl_label(n):
                s = ""
                while True:
                    s = chr(65 + (n % 26)) + s
                    n = n // 26 - 1
                    if n < 0:
                        return s
            label = _xl_label(idx)

            collected_sources.append({
                "source_id": sid,
                "label": label,
                "display_name": getattr(src, "display_name", None),
                "title": src.title,  # [DISPLAY-NAME] 라벨(A,B..)↔원본 제목 연결
                "video_url": vurl,
                "fragments": frags,
                "file_size_bytes": 0, # mock size
                "duration_sec": src.duration or 0.0
            })

        # [B-5-FIX] 저장된 프로젝트 제안도 함께 복원 (program_id 기준 props 재사용) — 돌아오면 A/B 그대로
        # [#57 REV 체인] mode별 최신 1건만 노출 — REV_* 수정본이 부모를 화면에서 대체한다.
        # 부모 행은 DB에 불변 보존(이력·거짓말 금지 §5). created_at 없으면 구행 취급.
        import datetime as _dt_rev
        _latest_by_mode = {}
        for _pp in props:
            _k = _pp.mode or "?"
            _cur = _latest_by_mode.get(_k)
            _t_new = _pp.created_at or _dt_rev.datetime.min
            _t_cur = (_cur.created_at or _dt_rev.datetime.min) if _cur else None
            if _cur is None or _t_new > _t_cur:
                _latest_by_mode[_k] = _pp
        if len(_latest_by_mode) < len(props):
            print(f"[#57 REV-RESTORE] {project_id}: {len(props)}행 -> mode별 최신 {len(_latest_by_mode)}건 "
                  f"({[(_k, _v.proposal_id) for _k, _v in _latest_by_mode.items()]})")
        props = list(_latest_by_mode.values())
        collected_proposals = [{
            "proposal_id": p.proposal_id,
            "mode": p.mode,
            "sequence": p.sequence,
            "duration": p.duration,
            "proposal_reason": p.proposal_reason,
            "confidence": p.confidence,
            "fallback_reason": p.fallback_reason,
        } for p in props]

    return {
        "status": "OK",
        "project_id": project_id,
        "sources": collected_sources,
        "proposals": collected_proposals
    }

@app.post("/proposals/project")
async def post_generate_project_proposals(req: ProjectProposalRequest):
    """
    [STEP 10-I.5.24-R1] Multi-Source Project Proposal 생성 (v0.1)

    [GATE-LOOP-01 2-1] 생성 게이트 — 승인 없으면 A/B를 만들지 않는다.
      제안은 '승인된 스토리를 어떻게 편집할지'다. 승인 전에 만들면 그게 스토리 대신
      진실이 되어버린다(오늘 정리한 병소의 뿌리). 스토리 씨앗은 분석 결과에서 나온다
      (story_gate.service.resolve_sequence 3순위) — 제안이 없어도 원고는 뜬다.
      사용자 이동은 막지 않는다: 거절은 '생성'뿐이고 화면 전환·조회는 그대로다.
    """
    import traceback
    from engine.proposal_engine import ProposalEngine

    project_id = req.project_id

    if story_gate.is_enabled():
        try:
            _st = story_service.story_state(project_id)
        except Exception as _e:
            _st = None
            print(f"[PROPOSAL][GATE] story_state 조회 실패 — 생성 계속: {_e}")
        if _st is not None and _st.get("story_state") != "story_approved":
            print(f"[PROPOSAL][GATE] 승인 전이라 A/B 생성 안 함 "
                  f"(project={project_id}, story_state={_st.get('story_state')})")
            return {
                "status": "STORY_NOT_APPROVED",
                "project_id": project_id,
                "story_state": _st.get("story_state"),
                "item_count": _st.get("item_count"),
                "proposals": [],
                "message": "원고를 먼저 승인해 주세요. 승인하면 편집안(A·B)을 만듭니다.",
            }
    
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
        # [SPEED-①] 무거운 생성/렌더를 executor로 — 생성 중에도 서버가 다른 요청에 응답
        # (기존: 이벤트 루프 점유 → 프로젝트 목록/썸네일까지 전부 마비)
        import asyncio as _aio
        _loop = _aio.get_event_loop()
        engine = ProposalEngine(bams)
        proposals = await _loop.run_in_executor(None, lambda: engine.generate_proposals_from_fragments(
            project_id=project_id,
            source_ids=source_ids,
            fragments=all_fragments,
            target_len=target_len,
            story_context=resolved_story_template # [STEP 10-K-B2]
        ))

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

        # [PROPOSAL_PREVIEW_INJECT] preview_url 주입 (렌더도 executor — 루프 비점유)
        # [STORY-GATE P1] render_preview=False면 렌더를 건너뛴다 — sequence는 그대로.
        # [STORY-GATE P2 / I-1] 게이트 ON + 미승인이면 요청이 True여도 렌더하지 않는다.
        _pv_render = req.render_preview
        if _pv_render and story_gate.is_enabled() and not story_service.is_render_allowed(project_id):
            _pv_render = False
            print(f"[STORY-GATE] {project_id} 미승인 -> render_preview 강제 False (I-1)")
        _pv_t0 = time.time()
        if _pv_render:
            # [BOUNDARY-1 B3] 미리보기 경계도 EDL 하나에서 받는다 — 재생·export 와 같은 값.
            _edl_clips = None
            try:
                from ledger_r0 import get_render_edl as _get_edl
                _edl = await _get_edl(project_id)
                if _edl.get("ok") and _edl.get("clips"):
                    _edl_clips = _edl["clips"]
                    print(f"[BOUNDARY] 미리보기 경계 출처=EDL clips={len(_edl_clips)} "
                          f"(구판: proposal.sequence anchor 좌표)")
                else:
                    print("[BOUNDARY] EDL 비어 있음 — 미리보기는 sequence 좌표로 폴백 (정직 표기)")
            except Exception as _be:
                print(f"[BOUNDARY] EDL 취득 실패 — sequence 좌표로 폴백 (비차단): {_be}")
            proposals = await _loop.run_in_executor(
                None, lambda: inject_proposal_previews(proposals, edl_clips=_edl_clips))
            print(f"[TIMING] preview_render={time.time() - _pv_t0:.1f}s")
        else:
            print("[STORY-GATE] render_preview=False -> preview 렌더 생략 (sequence만 반환)")

        # [STEP 14-D] Proposal Ranker integration
        try:
            from learning.proposal_ranker import ProposalRanker
            proposals = ProposalRanker.rerank_proposals(proposals)
        except Exception as rank_err:
            print(f"[RERANKER][ERROR] Failed to rerank project proposals: {rank_err}")

        # ── [PROPOSAL-AXIS-01 1-2] proposal = f(승인 스냅샷, 기법팩) ──────────────────
        #   여기가 계약이 성립하는 유일한 지점이다. 위의 엔진(선정 HRS)·guard·ranker가 만든
        #   조각·순서는 **채택하지 않고 덮는다** — 조각·순서의 출처는 승인 스냅샷 하나다.
        #   저장 직전에 두는 이유: guard/ranker/preview가 시퀀스를 만질 기회를 모두 지난 뒤라야
        #   'DB에 들어가는 값'이 승인과 같다고 말할 수 있다.
        #   실측 위반(Merope 승인 11 vs A 9 / B 15, A∩B=2)이 이 배선의 부재에서 나왔다.
        _axis_report = None
        try:
            from story_gate import proposal_axis as _axis
            _axis.ensure_columns()
            _appr_id, _appr_fids = _axis.live_approval_snapshot(project_id)
            if _appr_id is not None and _appr_fids:
                proposals, _rb = _axis.rebuild_from_approval(proposals, _appr_fids, all_fragments)
                # [2번 검산기] 저장 직전 최후 방어선 — 어긋나면 되돌리고 raw 로그를 남긴다.
                proposals, _violations = _axis.verify_or_restore(
                    proposals, _appr_fids, _appr_id, project_id)
                for _p in proposals:
                    _p["story_approval_id"] = _appr_id
                    # [PUNCH-1 P4] A/B가 갈리는 유일한 축. 조각·순서는 위 rebuild가 이미 동일하게 맞췄다.
                    _p["technique_id"] = _axis.technique_for_mode(_p.get("mode"))
                _axis_report = {
                    "story_approval_id": _appr_id,
                    "approval_item_count": len(_appr_fids),
                    "technique_id": {_p.get("mode"): _p.get("technique_id") for _p in proposals},
                    "unresolved_fids": _rb.get("unresolved_fids") or [],
                    "verify_violations": _violations,
                }
                print(f"[PROPOSAL-AXIS] approval_id={_appr_id} fids={len(_appr_fids)} "
                      f"technique={ {_p.get('mode'): _p.get('technique_id') for _p in proposals} } "
                      f"unresolved={len(_rb.get('unresolved_fids') or [])} "
                      f"violations={len(_violations)}")
            else:
                print(f"[PROPOSAL-AXIS][SKIP] 유효 승인 없음 — 제안 축 배선 미적용 "
                      f"(project={project_id}). 생성 게이트가 정상이면 도달하지 않는 경로.")
        except Exception as _axis_err:
            # 침묵 실패 금지: 축 배선이 깨지면 이유를 남긴다. 저장은 막지 않는다
            # (검산기 미통과 상태로 저장되지 않도록, 실패 시 축 정보는 붙지 않는다).
            print(f"[PROPOSAL-AXIS][ERROR] 승인 스냅샷 배선 실패 (비차단): {_axis_err}")

        # [B-3b-3] inject·rerank 후 program_id 기준 저장 — GET 복원(filter_by program_id)과 맞물림
        _save_result = bams.save_project_proposals(project_id, proposals)
        _proposal_save_guarded = bool(isinstance(_save_result, dict) and _save_result.get("guarded"))
        if _proposal_save_guarded:
            proposals = bams.get_project_proposals_latest(project_id)
            source_usage = {}
            for _p in proposals:
                for _s in (_p.get("sequence") or []):
                    sid = _s.get("source_id", "UNKNOWN")
                    source_usage[sid] = source_usage.get(sid, 0) + 1
            warnings.append({
                "reason": _save_result.get("reason", "EMPTY_PROJECT_PROPOSAL_WRITE_SKIPPED"),
                "message": "빈 제안 결과가 기존 프로젝트 제안을 덮지 않도록 저장을 건너뛰었습니다.",
                "preserved_count": _save_result.get("preserved_count"),
            })

        # [조각 이력] 채택(adopted) 사건 기록 — 제안이 나중에 교체·purge돼도
        # "이 조각이 이 프로젝트 제안에 채택됐다"는 사실은 스냅샷으로 영속. 비차단.
        if not _proposal_save_guarded:
            try:
                from engine import fragment_vault as _fvE
                from database import SessionLocal as _SLe
                with _SLe() as _dbe:
                    _pg = _dbe.query(ProgramTable).filter_by(program_id=project_id).first()
                    _pgname = _pg.name if _pg else None
                _pnames = None
                _events = []
                for _p in (proposals or []):
                    _pid = _p.get("proposal_id")
                    _mode = _p.get("mode")
                    for _s in (_p.get("sequence") or []):
                        _events.append({
                            "source_id": _s.get("source_id"),
                            "start": _s.get("start"), "end": _s.get("end"),
                            "fragment_id": _s.get("fragment_id"),
                            "event_kind": "adopted", "ref_id": _pid or f"{project_id}_{_mode}",
                            "program_id": project_id, "program_name": _pgname,
                            "proposal_id": _pid,
                            "proposal_name": (f"{_pgname} · {_mode}안" if _pgname and _mode else None),
                            "detail": {"mode": _mode},
                        })
                _n = _fvE.record_events(_events)
                print(f"[VAULT-EVENT] adopted 기록: +{_n} (제안 {len(proposals or [])}건)")
            except Exception as _ve:
                print(f"[VAULT-EVENT] adopted 기록 실패 (비차단): {_ve}")

        # [B-4] 프로젝트-소스 다대다 기록 (project_sources upsert, 멱등). 실패해도 응답엔 영향 없음
        try:
            from database import SessionLocal as _SL
            import datetime as _dt
            with _SL() as _db:
                for _i, _sid in enumerate(source_ids):
                    _ex = _db.query(ProjectSourceTable).filter_by(program_id=project_id, source_id=_sid).first()
                    if not _ex:
                        _db.add(ProjectSourceTable(program_id=project_id, source_id=_sid,
                                                   display_order=_i, added_at=_dt.datetime.now().isoformat()))
                _db.commit()
        except Exception as _e:
            print(f"[B-4][project_sources] upsert skip: {_e}")

        return {
            "status": "PROPOSAL_READY",
            "project_id": project_id,
            "source_ids": source_ids,
            "semantic_count": len(all_fragments),
            "proposals": proposals,
            "source_usage": source_usage,
            "resolved_story_template": resolved_story_template, # [STEP 10-K-B2-R1]
            # [PROPOSAL-AXIS-01] 조각·순서의 출처와 기법, 검산기 결과를 정직하게 실어 보낸다.
            "proposal_axis": _axis_report,
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
async def post_generate_proposals(source_id: str, render_preview: bool = True):
    """
    [STEP 6] Proposal 생성 트리거 (v3.2.1 정밀 진단 버전)

    [STORY-GATE P1] render_preview=False면 preview 렌더를 건너뛰고 sequence만 반환.
    기본 True = 현행 동작 무변.
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
        # [STORY-GATE P1] render_preview=False면 렌더를 건너뛴다 — sequence는 그대로.
        # [STORY-GATE P2 / I-1] 이 경로(단일 소스)는 program을 모른다 → 승인 확인 불가.
        # 게이트 ON이면 자동 렌더를 아예 하지 않는다. 렌더는 승인 뒤 /preview·/render로만.
        _pv_render = render_preview
        if _pv_render and story_gate.is_enabled():
            _pv_render = False
            print(f"[STORY-GATE] {source_id} source-level 자동 렌더 차단 (program 미상, I-1)")
        _pv_t0 = time.time()
        if _pv_render:
            proposals = inject_proposal_previews(proposals)
            print(f"[TIMING] preview_render={time.time() - _pv_t0:.1f}s")
        else:
            print("[STORY-GATE] render_preview=False -> preview 렌더 생략 (sequence만 반환)")

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
#   [P3-REV] Revision — 기존 제안에 대한 수정 명령 (CCUT_REVISION 게이트)
#   주의: /proposals/{source_id} 동적 라우트와의 충돌을 피해 별도 prefix 사용.
# ═══════════════════════════════════════════════════════════════════

@app.post("/revision/proposals")
async def post_proposal_revision(payload: dict):
    """확정/선택된 proposal에 '두 번째 문장'(수정 명령) 적용.
    감지·적용은 engine.revision (판단은 hub 재사용). 기본 OFF: CCUT_REVISION=1 필요.
    반환 시퀀스는 새 proposal_id(REV_*)로 저장 — 원본은 불변(비파괴)."""
    from engine import revision as _rev
    if not _rev.revision_enabled():
        return {"status": "DISABLED", "message": "CCUT_REVISION=1 필요 (기본 OFF)"}
    proposal_id = payload.get("proposal_id")
    instruction = (payload.get("instruction") or "").strip()
    if not proposal_id or not instruction:
        return {"status": "ERROR", "message": "proposal_id / instruction 필요"}

    from database import SessionLocal
    from archive.db_models import ProposalTable
    db = SessionLocal()
    try:
        p = db.query(ProposalTable).filter(ProposalTable.proposal_id == proposal_id).first()
        if not p:
            return {"status": "ERROR", "message": f"proposal not found: {proposal_id}"}
        # [#57] 종업원이 이미 이해한 op가 오면 재검증 후 그대로 집행(LLM 중복 호출 제거).
        # 없으면 서버가 감지(결정론 → 큐원 폴백). 어느 경로든 validate 통과 op만 집행.
        rev = _rev.validate_revision(payload.get("revision") or {})
        if not rev:
            rev = _rev.detect_revision_full(instruction, has_committed_proposal=True)
        if not rev:
            return {"status": "NOT_REVISION",
                    "message": "수정 명령으로 인식되지 않음 — 신규 제안 경로를 사용하세요"}
        new_seq, reason = _rev.apply_revision(rev, p.sequence or [],
                                              source_ids=payload.get("source_ids"))

        def _fdur(f):
            try:
                d = f.get("duration")
                if d:
                    return float(d)
                return float(f.get("end", f.get("end_time", 0)) or 0) - float(f.get("start", f.get("start_time", 0)) or 0)
            except Exception:
                return 0.0

        import uuid as _uuid
        new_id = f"REV_{_uuid.uuid4().hex[:6].upper()}_{p.proposal_id}"
        db.add(ProposalTable(
            proposal_id=new_id, source_id=p.source_id, mode=p.mode,
            sequence=new_seq,
            duration=round(sum(_fdur(f) for f in new_seq), 2),
            proposal_reason={"mode_reason": "revision", "revision": reason,
                             "parent": p.proposal_id, "instruction": instruction},
            confidence=p.confidence, program_id=p.program_id,
        ))
        db.commit()
        print(f"[P4-REV] saved {new_id} parent={proposal_id} seq={len(new_seq)}")
        return {"status": "OK", "proposal_id": new_id, "parent": proposal_id,
                "reason": reason, "count": len(new_seq), "sequence": new_seq}
    finally:
        db.close()

# ═══════════════════════════════════════════════════════════════════
#   [STEP 7] Export Input Generation
# ═══════════════════════════════════════════════════════════════════

@app.post("/export-input/{proposal_id:path}")
async def post_export_input(proposal_id: str, payload: dict = None):
    """
    [STEP 7] Proposal -> Export Input 변환
    해당 proposal_id의 시퀀스를 렌더링용 클립 리스트로 전환합니다.
    payload에 'clips'가 있으면 이를 직접 사용하여 Resolver 결과를 반영합니다.
    """
    from engine.export_engine import ExportEngine
    engine = ExportEngine(bams)
    
    custom_clips = payload.get("clips") if payload else None
    program_id = payload.get("program_id") if payload else None
    program_title = payload.get("program_title") if payload else None
    export_input = engine.create_export_input(proposal_id, custom_clips=custom_clips)
    if export_input and program_id:
        export_input["program_id"] = program_id
        export_input["program_title"] = program_title
    
    if not export_input:
        return {"status": "NOT_FOUND", "proposal_id": proposal_id}
        
    # [STEP 14-A] Log user proposal acceptance decision
    try:
        from learning.decision_logger import DecisionLogger
        from database import SessionLocal as _SL_log
        with _SL_log() as db_session:
            prop_row = db_session.query(ProposalTable).filter_by(proposal_id=proposal_id).first()
            if prop_row:
                src_id = prop_row.source_id
                prog_id = prop_row.program_id
                # Fetch sibling proposals under the same project (source 단건 또는 program 다중)
                if src_id:
                    siblings = db_session.query(ProposalTable).filter_by(source_id=src_id).filter(ProposalTable.program_id.is_(None)).all()
                elif prog_id:
                    siblings = db_session.query(ProposalTable).filter_by(program_id=prog_id).all()
                else:
                    siblings = []
                sibling_dicts = []
                for s in siblings:
                    sibling_dicts.append({
                        "proposal_id": s.proposal_id,
                        "mode": s.mode,
                        "sequence": s.sequence,
                        "duration": s.duration,
                        "original_reason": s.proposal_reason,
                        "human_reality_score_data": (s.proposal_reason if isinstance(s.proposal_reason, dict) else {}).get("human_reality_score", {})
                    })
                DecisionLogger.log_user_proposal_choice(
                    project_id=src_id or prog_id,
                    chosen_mode=prop_row.mode,
                    proposals=sibling_dicts
                )
    except Exception as log_err:
        import traceback as _tb
        print(f"[DECISION_LOGGER][ERROR] Failed to log user proposal choice: {log_err}")
        _tb.print_exc()

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
async def post_render(export_input_id: str, payload: dict = None, db: Session = Depends(get_db)):
    """
    [STEP 8] Render 실행
    ExportInput ID를 받아 실제 mp4 영상을 생성합니다.
    """
    from engine.render_engine import render_engine
    # program_id/title: payload 우선, 없으면 proposal → program 역추적
    program_id = (payload or {}).get("program_id")
    program_title = (payload or {}).get("program_title")
    if not program_id:
        ei = db.query(ExportInputTable).filter_by(export_id=export_input_id).first()
        if ei and ei.proposal_id:
            prop = db.query(ProposalTable).filter_by(proposal_id=ei.proposal_id).first()
            if prop and prop.program_id:
                program_id = prop.program_id
                pg = db.query(ProgramTable).filter_by(program_id=program_id).first()
                program_title = pg.name if pg else None
    # [STORY-GATE P2 / I-1] 승인 없이는 렌더하지 않는다. 게이트 OFF면 검사 없음(현행 무변).
    if story_gate.is_enabled() and program_id and not story_service.is_render_allowed(program_id):
        return JSONResponse(status_code=403, content={
            "status": "STORY_NOT_APPROVED", "error": "STORY_NOT_APPROVED",
            "program_id": program_id, "export_input_id": export_input_id,
            "message": "이야기가 아직 승인되지 않았습니다. 원고를 확인하고 승인해 주세요.",
        })
    result = render_engine.render_from_export_input(export_input_id)
    if result and result.get("success"):
        from archive.db_models import ExportResultTable as _ERT
        row = db.query(_ERT).filter_by(export_input_id=export_input_id).first()
        if row:
            if program_id:
                row.program_id = program_id
                row.program_title = program_title
            # [EXPORT-NAME-SNAPSHOT] 렌더 성공 시점에 이름을 스냅샷으로 고정 —
            # 이후 제안이 재생성되어 proposal_id가 사라져도 이 값은 불변으로 남는다
            # (조인 방식이던 옛 코드가 export display_name null 회귀를 냈던 원인 수리).
            names = _proposal_display_names(db)
            snap = names.get(row.proposal_id)
            if not snap and program_title:
                snap = f"{program_title} · 내보낸 영상"
            if snap:
                row.display_name = snap
            db.commit()
            # [송출층 §3.1] 크레딧 매니페스트 — 방송의 엔딩 크레딧처럼, 완성본이
            # DB 없이도 자기 정체(이름·회차·소재 계보·레시피)를 증언하는 사이드카.
            # 실패해도 렌더 흐름은 비차단.
            try:
                import json as _json
                ei2 = db.query(ExportInputTable).filter_by(export_id=export_input_id).first()
                clips = (ei2.clips if ei2 else None) or []
                src_ids = set()
                for c in clips:
                    fid = str(c.get("fragment_id", ""))
                    if "_SRC_" in fid:  # SF_XXXX_SRC_YYYY[_Pnnn] → SRC_YYYY
                        src_ids.add("SRC_" + fid.split("_SRC_")[-1].split("_")[0])
                src_ids = sorted(src_ids)
                src_rows = db.query(SourceTable).filter(SourceTable.source_id.in_(src_ids)).all() if src_ids else []
                manifest = {
                    "kind": "ccut_credit_manifest_v1",
                    "render_id": row.id,
                    "display_name": row.display_name,
                    "program": {"program_id": program_id, "name": program_title},
                    "proposal_id": row.proposal_id,
                    "rendered_at": str(row.created_at),
                    "output_url": row.output_url,
                    "clips": clips,
                    "sources": [{"source_id": s.source_id, "title": s.title,
                                 "shot_date": getattr(s, "shot_date", None),
                                 "hash": s.hash_value} for s in src_rows],
                }
                _adir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "storage", "archive")
                os.makedirs(_adir, exist_ok=True)
                with open(os.path.join(_adir, f"{row.id}.json"), "w", encoding="utf-8") as _f:
                    _json.dump(manifest, _f, ensure_ascii=False, indent=1)
                print(f"[CREDIT] 매니페스트 기록: storage/archive/{row.id}.json")
                # [조각 이력] 방송(exported) 사건 — 이 조각이 완성본에 실렸다는
                # 사실을 자연키+이름 스냅샷으로 영속. 비차단.
                try:
                    from engine import fragment_vault as _fvX
                    _xev = []
                    for _c in clips:
                        _fid = str(_c.get("fragment_id", ""))
                        _csid = ("SRC_" + _fid.split("_SRC_")[-1].split("_")[0]
                                 if "_SRC_" in _fid else None)
                        if not _csid:
                            continue
                        _xev.append({
                            "source_id": _csid,
                            "start": _c.get("start"), "end": _c.get("end"),
                            "fragment_id": _fid,
                            "event_kind": "exported", "ref_id": row.id,
                            "program_id": program_id, "program_name": program_title,
                            "proposal_id": row.proposal_id,
                            "proposal_name": row.display_name,
                        })
                    _nx = _fvX.record_events(_xev)
                    print(f"[VAULT-EVENT] exported 기록: +{_nx}")
                except Exception as _ve:
                    print(f"[VAULT-EVENT] exported 기록 실패 (비차단): {_ve}")
            except Exception as _cm_e:
                print(f"[CREDIT] 매니페스트 실패 (비차단): {_cm_e}")
    return result

@app.get("/render-result/{export_input_id}")
async def get_render_result(export_input_id: str):
    """[STEP 8] Render 결과 조회"""
    result = bams.get_render_result(export_input_id)
    if not result:
        return {"status": "NOT_FOUND", "export_input_id": export_input_id}
    return result

@app.get("/exports/list")
async def get_exports_list(db: Session = Depends(get_db)):
    """내보낸 영상 전체 목록 (아카이브/SNS 패널용)"""
    exports = bams.get_all_exports()
    # [EXPORT-NAME-SNAPSHOT] 렌더 시점 스냅샷(display_name 컬럼)이 우선 — 제안이
    # 재생성돼 proposal_id가 사라져도 이름이 유실되지 않는다. 스냅샷이 없는
    # 레거시 행(백필 전/실패)만 하위호환 조인으로 보충.
    names = _proposal_display_names(db)
    for e in exports or []:
        if isinstance(e, dict) and not e.get("display_name"):
            e["display_name"] = names.get(e.get("proposal_id"))
    return {"exports": exports}

@app.patch("/programs/{program_id}/name")
async def rename_program(program_id: str, payload: dict = None, db: Session = Depends(get_db)):
    """프로젝트 이름 변경 (LeftNav / SNS / Archive 어디서든 호출)"""
    new_name = ((payload or {}).get("name") or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="name is required")
    pg = db.query(ProgramTable).filter_by(program_id=program_id).first()
    if not pg:
        raise HTTPException(status_code=404, detail="Program not found")
    pg.name = new_name
    db.commit()
    return {"status": "SUCCESS", "program_id": program_id, "name": new_name}

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

    print(f"[BATCH] {batch_id} 시작 - {len(program_ids)}개 프로그램")
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

    print(f"[BATCH] {batch_id} 완료 - 최종 상태: {batch['status']}")


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

    print(f"[BATCH] 새 배치 생성: {batch_id} - {len(req.program_ids)}개 프로그램")
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

    print(f"[BATCH RETRY] {batch_id} - {len(retry_ids)}개 항목 재시도")
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
        "message": f"'{asset.title}' - 전 세계 송출 완료!",
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


_KO_ORD = ["첫", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열"]


def _ko_ordinal(n: int) -> str:
    return f"{_KO_ORD[n - 1]} 번째" if 1 <= n <= len(_KO_ORD) else f"{n}번째"


def _proposal_display_names(db) -> dict:
    """[DISPLAY-NAME] proposal_id → 사람 말 명칭 "{프로젝트명} · 첫 번째 제안 · A안".
    아카이브 목록·내보낸 영상이 같은 함수를 쓴다(이름을 두 번 만들지 않는다).
    N = 프로젝트 내 세대 순번(생성시각 오름차순, 10분 넘게 벌어지면 새 세대 —
    A/B 쌍은 같은 실행이라 한 세대). 이후 SNS 업로드 명칭의 뿌리."""
    import datetime as _dt
    proposals = db.query(ProposalTable).all()
    prog_name = {p.program_id: p.name
                 for p in db.query(ProgramTable).filter(ProgramTable.schema_version == 2).all()}
    src_prog: dict = {}
    for sid, pid in db.query(ProjectSourceTable.source_id, ProjectSourceTable.program_id) \
                      .order_by(ProjectSourceTable.added_at).all():
        src_prog.setdefault(sid, pid)

    def _pid(pr):
        return pr.program_id or src_prog.get(pr.source_id)

    by_prog: dict = {}
    for pr in proposals:
        by_prog.setdefault(_pid(pr) or "_none", []).append(pr)
    gen_of: dict = {}
    for _p, rows in by_prog.items():
        rows = sorted(rows, key=lambda r: (r.created_at or _dt.datetime.min, r.proposal_id))
        gen, prev = 0, None
        for r in rows:
            if prev is None or not r.created_at or (r.created_at - prev).total_seconds() > 600:
                gen += 1
            gen_of[r.proposal_id] = gen
            if r.created_at:
                prev = r.created_at

    out: dict = {}
    for pr in proposals:
        pname = prog_name.get(_pid(pr)) or "프로젝트 미상"
        mode = f" · {pr.mode}안" if pr.mode in ("A", "B") else ""
        seq = gen_of.get(pr.proposal_id)
        out[pr.proposal_id] = (f"{pname} · {_ko_ordinal(seq)} 제안{mode}"
                               if seq else f"{pname}{mode}")
    return out


@app.get("/vault/stats")
async def vault_stats():
    """[조각 금고] 인지조각 원장 현황 — 왕관 자산의 건강 지표."""
    from engine import fragment_vault as fv
    return {"status": "OK", **fv.stats()}


@app.get("/archive/source/{source_id}/fragments")
async def archive_source_fragments(source_id: str):
    """[조각 이력] 한 원본의 조각 자산 이력 — 조각 수·채택·편집·방송.
    프로젝트가 purge돼도 응답 불변(이름 스냅샷·자연키 기반)."""
    from engine import fragment_vault as fv
    return {"status": "OK", **fv.source_fragment_history(source_id)}


@app.post("/narrative/notes")
async def add_narrative_notes(payload: dict = None):
    """[서사층 §2.1] 말의 원장 적재 — 사용자의 말은 최상급 자산.
    body: {notes: [{target_kind, target_id, text, origin}]}"""
    from engine import narrative_ledger as nl
    n = nl.add_notes((payload or {}).get("notes") or [])
    return {"status": "OK", "added": n}


@app.get("/narrative/notes/{target_kind}/{target_id}")
async def get_narrative_notes(target_kind: str, target_id: str):
    from engine import narrative_ledger as nl
    return {"status": "OK", "notes": nl.notes_for(target_kind, target_id)}


def _archive_summary_payload(db: Session) -> dict:
    """[Archive 단계B] 아카이브 최소 summary — 구형 대형 응답 해체(국장 판정: 즉시 축소).
    목록/상세는 후속 read path(/archive/sources, /archive/source/{id})가 담당한다."""
    from sqlalchemy import func as _func

    source_count = db.query(_func.count(SourceTable.source_id)).scalar() or 0

    # 프로그램 수: 기존 목록과 동일 기준 — schema_version=2 & 원본 1개 이상
    src_count_rows = (
        db.query(ProjectSourceTable.program_id, _func.count().label("cnt"))
          .group_by(ProjectSourceTable.program_id).all()
    )
    valid_ids = {r.program_id for r in src_count_rows if r.cnt > 0}
    program_count = (
        db.query(_func.count(ProgramTable.program_id))
          .filter(ProgramTable.schema_version == 2,
                  ProgramTable.program_id.in_(valid_ids)).scalar() or 0
    ) if valid_ids else 0

    latest_shot_date = (
        db.query(_func.max(SourceTable.shot_date))
          .filter(SourceTable.shot_date.isnot(None)).scalar()
    )

    recent_source_ids = [
        r.source_id
        for r in db.query(SourceTable.source_id)
                    .order_by(SourceTable.created_at.desc()).limit(5).all()
    ]

    return {
        "source_count": source_count,
        "program_count": program_count,
        "latest_shot_date": latest_shot_date,
        "recent_source_ids": recent_source_ids,
    }


@app.get("/archive/list")
async def get_archive_list(db: Session = Depends(get_db)):
    """[Archive 단계B] 즉시 축소 — 구형 sources+programs+proposals 대형 응답 폐지.
    summary 수준만 반환한다(제거 아님, 축소 — 국장 판정)."""
    return _archive_summary_payload(db)


@app.get("/archive/summary")
async def get_archive_summary(db: Session = Depends(get_db)):
    """[Archive 단계B] 아카이브 최소 summary — 첫 진입 경량 로드용."""
    return _archive_summary_payload(db)


@app.get("/archive/sources")
async def get_archive_sources(
    cursor: str = None,
    limit: int = 20,
    sort: str = "shot_date_desc",
    q: str = None,
    db: Session = Depends(get_db),
):
    """[Archive 단계B] sources 목록 — cursor 기반 페이징(국장 판정: sources 먼저).
    기본 정렬 shot_date DESC, shot_date 없으면 created_at fallback(NULL last)."""
    from sqlalchemy import func as _func, tuple_ as _tuple
    from engine import fragment_vault as _fv

    limit = max(1, min(int(limit or 20), 50))
    sort = sort if sort in ("shot_date_desc", "created_desc") else "shot_date_desc"

    query = db.query(SourceTable)
    if q:
        query = query.filter(SourceTable.title.ilike(f"%{q}%"))

    if sort == "created_desc":
        order_cols = (SourceTable.created_at.desc(), SourceTable.source_id.desc())
        cursor_cols = (SourceTable.created_at, SourceTable.source_id)
    else:
        # shot_date 없으면 created_at 앞 10자(YYYY-MM-DD)로 대체 — NULL이 뒤로 밀리지 않게
        sort_key = _func.coalesce(SourceTable.shot_date, _func.substr(SourceTable.created_at, 1, 10))
        order_cols = (sort_key.desc(), SourceTable.created_at.desc(), SourceTable.source_id.desc())
        cursor_cols = (sort_key, SourceTable.created_at, SourceTable.source_id)

    if cursor:
        cur_row = db.query(*cursor_cols).filter(SourceTable.source_id == cursor).first()
        if cur_row:
            query = query.filter(_tuple(*cursor_cols) < _tuple(*cur_row))

    # [즉시 축소 원칙] 전량 .all() 금지 — 반드시 LIMIT. +1은 next_cursor 존재 판별용.
    rows = query.order_by(*order_cols).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    def _card(s):
        # [조각 이력 재사용] fv.source_fragment_history는 이미 검증된 함수(커밋 C/D) —
        # anchor_hash 기반 조각 목록·썸네일 경로를 다시 만들지 않고 그대로 재사용
        hist = _fv.source_fragment_history(s.source_id)
        frags = hist.get("fragments") or []
        return {
            "source_id": s.source_id,
            "title": s.title,
            "shot_date": s.shot_date,
            "shot_date_fallback": s.shot_date is None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "duration": s.duration,
            "thumbnail_url": frags[0]["thumbnail_url"] if frags else None,
            "fragment_count": hist.get("fragment_count", 0),
        }

    return {
        "sources": [_card(s) for s in rows],
        "next_cursor": rows[-1].source_id if (has_more and rows) else None,
    }


def _xl_label(n) -> str:
    """프로젝트 내 원본 라벨 (A..Z, AA..) — get_project_sources와 동일 규칙."""
    s = ""
    n = int(n or 0)
    while True:
        s = chr(65 + (n % 26)) + s
        n = n // 26 - 1
        if n < 0:
            return s


@app.get("/archive/source/{source_id}")
async def get_archive_source_detail(source_id: str, db: Session = Depends(get_db)):
    """[Archive 단계B] source 상세 — 카드 클릭 시 lazy hydrate.
    기본 메타 + 말의 원장(notes) + usage summary + export summary + 조각 이력."""
    from engine import narrative_ledger as _nl
    from engine import fragment_vault as _fv

    s = db.query(SourceTable).filter(SourceTable.source_id == source_id).first()
    if not s:
        return {"status": "ERROR", "message": "source not found"}

    ps_rows = (
        db.query(ProjectSourceTable.program_id, ProjectSourceTable.added_at,
                  ProjectSourceTable.display_order, ProgramTable.name,
                  ProgramTable.last_updated_at, ProgramTable.deleted_at)
          .join(ProgramTable, ProjectSourceTable.program_id == ProgramTable.program_id)
          .filter(ProjectSourceTable.source_id == source_id,
                  ProgramTable.schema_version == 2)
          .all()
    )
    usage = []
    for pid, added_at, disp_order, pname, lua, deleted_at in ps_rows:
        used_at = added_at or (lua.isoformat() if lua else None)
        usage.append({
            "program_id": pid, "name": pname, "used_at": used_at,
            "label": _xl_label(disp_order),
            "deleted_at": deleted_at.isoformat() if deleted_at else None,
        })
    usage.sort(key=lambda u: str(u["used_at"] or ""), reverse=True)

    from archive.db_models import ExportResultTable
    exp_rows = (
        db.query(ExportResultTable)
          .filter(ExportResultTable.source_id == source_id)
          .order_by(ExportResultTable.created_at.desc()).limit(20).all()
    )
    export_summary = [{
        "id": e.id, "program_id": e.program_id,
        "display_name": e.display_name or e.program_title,
        "output_url": e.output_url, "status": e.status,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in exp_rows]

    hist = _fv.source_fragment_history(source_id)

    return {
        "status": "OK",
        "source_id": s.source_id,
        "title": s.title,
        "duration": s.duration,
        "fps": s.fps,
        "hash_value": s.hash_value,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "shot_date": s.shot_date,
        "shot_date_fallback": s.shot_date is None,
        "play_url": (
            f"/static/uploads/{_url_quote(os.path.basename(s.file_path), safe='')}"
            if s.file_path and os.path.exists(s.file_path) else None
        ),
        "notes": _nl.notes_for("source", source_id),
        "usage": usage,
        "exports": export_summary,
        "fragment_count": hist.get("fragment_count", 0),
        "adopted_events": hist.get("adopted_events", 0),
        "edited_events": hist.get("edited_events", 0),
        "exported_events": hist.get("exported_events", 0),
        "fragments": hist.get("fragments", []),
    }


@app.get("/archive/timeline/days")
async def get_archive_timeline_days(before: str = None, limit: int = 20, db: Session = Depends(get_db)):
    """[Archive 단계B] 연대기 홈 — 날짜별 source 묶음(cursor 페이징).
    date_key = shot_date 우선, 없으면 created_at 앞 10자(YYYY-MM-DD) fallback."""
    from sqlalchemy import text as _text
    from engine import fragment_vault as _fv

    limit = max(1, min(int(limit or 20), 50))
    params: dict = {"limit": limit + 1}
    where = ""
    if before:
        where = "WHERE date_key < :before"
        params["before"] = before

    rows = db.execute(_text(f"""
        SELECT date_key, cnt, fallback_cnt FROM (
            SELECT COALESCE(shot_date, substr(created_at, 1, 10)) AS date_key,
                   COUNT(*) AS cnt,
                   SUM(CASE WHEN shot_date IS NULL THEN 1 ELSE 0 END) AS fallback_cnt
            FROM sources
            GROUP BY date_key
        )
        {where}
        ORDER BY date_key DESC
        LIMIT :limit
    """), params).fetchall()

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    days = []
    for date_key, cnt, fallback_cnt in page_rows:
        rep = db.execute(_text(
            "SELECT source_id FROM sources "
            "WHERE COALESCE(shot_date, substr(created_at, 1, 10)) = :dk "
            "ORDER BY created_at DESC LIMIT 1"), {"dk": date_key}).fetchone()
        thumb = None
        if rep:
            hist = _fv.source_fragment_history(rep[0])
            frags = hist.get("fragments") or []
            thumb = frags[0]["thumbnail_url"] if frags else None
        days.append({
            "date_key": date_key,
            "source_count": cnt,
            "thumbnail_url": thumb,
            "has_fallback": bool(fallback_cnt),
        })

    return {
        "days": days,
        "next_cursor": page_rows[-1][0] if (has_more and page_rows) else None,
    }


@app.get("/archive/timeline/day/{date_key}")
async def get_archive_timeline_day(date_key: str, db: Session = Depends(get_db)):
    """[Archive 단계B] 연대기 day 상세 — 해당 날짜(또는 fallback)의 source 목록."""
    from sqlalchemy import text as _text
    from engine import fragment_vault as _fv

    rows = db.execute(_text(
        "SELECT source_id, title, shot_date, created_at, duration FROM sources "
        "WHERE COALESCE(shot_date, substr(created_at, 1, 10)) = :dk "
        "ORDER BY created_at DESC"), {"dk": date_key}).fetchall()

    def _card(r):
        sid, title, shot_date, created_at, duration = r
        hist = _fv.source_fragment_history(sid)
        frags = hist.get("fragments") or []
        return {
            "source_id": sid,
            "title": title,
            "shot_date": shot_date,
            "shot_date_fallback": shot_date is None,
            "created_at": created_at,
            "duration": duration,
            "thumbnail_url": frags[0]["thumbnail_url"] if frags else None,
            "fragment_count": hist.get("fragment_count", 0),
        }

    return {"date_key": date_key, "sources": [_card(r) for r in rows]}


# ═══════════════════════════════════════════════════════════════════
#   [ADMIN v0] 중앙 관리자 콘솔 — read-mostly MVP (설계서 3편 SSOT)
#   전 KPI 실 DB 집계 · 관리자 행동 append-only 감사 · insights는 로컬 hub만
# ═══════════════════════════════════════════════════════════════════

@app.get("/admin/overview")
async def admin_overview():
    from admin import service as _adm
    return _adm.overview()


@app.get("/admin/situation")
async def admin_situation():
    """[War Room v1] 상황실 — 글로벌 상태등·KPI·경보·작전 큐."""
    from admin import service as _adm
    return _adm.situation()


@app.get("/admin/users")
async def admin_users():
    from admin import service as _adm
    return _adm.users_list()


@app.get("/admin/users/{user_id}")
async def admin_user_detail(user_id: str):
    from admin import service as _adm
    return _adm.user_detail(user_id)


@app.post("/admin/users/{user_id}/note")
async def admin_user_note(user_id: str, payload: dict = None):
    from admin import service as _adm
    note = ((payload or {}).get("note") or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="note is required")
    return _adm.add_user_note(user_id, note)


@app.get("/admin/revenue/summary")
async def admin_revenue_summary():
    from admin import service as _adm
    return _adm.revenue_summary()


@app.post("/admin/insights/query")
async def admin_insights_query(payload: dict = None):
    from admin import service as _adm
    query = ((payload or {}).get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    return _adm.insights_query(query)


@app.get("/admin/audit/logs")
async def admin_audit_logs(limit: int = 20, cursor: int = None):
    from admin import service as _adm
    return _adm.audit_logs(limit=limit, cursor=cursor)


@app.get("/admin/work-items")
async def admin_work_items(status: str = "open", limit: int = 50):
    from admin import service as _adm
    return _adm.work_items_list(status=status, limit=limit)


@app.post("/admin/work-items")
async def admin_work_item_create(payload: dict = None):
    from admin import service as _adm
    return _adm.work_item_create(payload or {})


@app.post("/admin/work-items/{item_id}/transition")
async def admin_work_item_transition(item_id: int, payload: dict = None):
    from admin import service as _adm
    p = payload or {}
    return _adm.work_item_transition(item_id, (p.get("status") or "").strip(), p.get("note"))


@app.get("/admin/support/cases")
async def admin_support_cases(status: str = "open", limit: int = 50):
    from admin import service as _adm
    return _adm.support_cases_list(status=status, limit=limit)


@app.post("/admin/support/cases")
async def admin_support_case_create(payload: dict = None):
    from admin import service as _adm
    return _adm.support_case_create(payload or {})


@app.post("/admin/support/cases/{case_id}/note")
async def admin_support_case_note(case_id: int, payload: dict = None):
    from admin import service as _adm
    note = ((payload or {}).get("note") or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="note is required")
    return _adm.support_case_note(case_id, note)


@app.post("/admin/support/cases/{case_id}/classify")
async def admin_support_case_classify(case_id: int):
    from admin import service as _adm
    return _adm.support_case_classify(case_id)


@app.get("/admin/security/events")
async def admin_security_events(status: str = "open", limit: int = 50):
    from admin import service as _adm
    return _adm.security_events_list(status=status, limit=limit)


@app.post("/admin/security/events")
async def admin_security_event_create(payload: dict = None):
    from admin import service as _adm
    return _adm.security_event_create(payload or {})


@app.post("/admin/security/events/{event_id}/status")
async def admin_security_event_status(event_id: int, payload: dict = None):
    from admin import service as _adm
    return _adm.security_event_status(event_id, ((payload or {}).get("status") or "").strip())


@app.get("/admin/revenue/products")
async def admin_revenue_products():
    from admin import service as _adm
    return _adm.products_list()


@app.post("/admin/revenue/products")
async def admin_revenue_product_create(payload: dict = None):
    from admin import service as _adm
    return _adm.product_create(payload or {})


@app.post("/admin/revenue/products/{product_id}/status")
async def admin_revenue_product_status(product_id: str, payload: dict = None):
    from admin import service as _adm
    return _adm.product_status(product_id, ((payload or {}).get("status") or "").strip())


@app.get("/admin/revenue/points")
async def admin_revenue_points():
    from admin import service as _adm
    return _adm.points_summary()


@app.get("/admin/design/configs")
async def admin_design_configs():
    from admin import service as _adm
    return _adm.design_configs_list()


@app.post("/admin/design/configs")
async def admin_design_config_create(payload: dict = None):
    from admin import service as _adm
    return _adm.design_config_create(payload or {})


@app.post("/admin/design/configs/{config_id}/status")
async def admin_design_config_status(config_id: int, payload: dict = None):
    from admin import service as _adm
    return _adm.design_config_status(config_id, ((payload or {}).get("status") or "").strip())


@app.get("/admin/ai/status")
async def admin_ai_status():
    from admin import service as _adm
    return _adm.ai_status()


@app.get("/admin/ai/runs")
async def admin_ai_runs(limit: int = 50):
    from admin import service as _adm
    return _adm.ai_runs(limit=limit)


@app.post("/admin/ai/query")
async def admin_ai_query(payload: dict = None):
    from admin import service as _adm
    p = payload or {}
    query = (p.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    return _adm.ai_query((p.get("role") or "ops_brief").strip(), query)


@app.get("/admin/analytics/activity")
async def admin_analytics_activity(days: int = 14):
    from admin import service as _adm
    return _adm.analytics_activity(days=days)


@app.get("/admin/legal/requests")
async def admin_legal_requests():
    from admin import service as _adm
    return _adm.legal_requests_list()


@app.post("/admin/legal/requests")
async def admin_legal_request_create(payload: dict = None):
    from admin import service as _adm
    return _adm.legal_request_create(payload or {})


@app.post("/admin/legal/requests/{req_id}/status")
async def admin_legal_request_status(req_id: int, payload: dict = None):
    from admin import service as _adm
    return _adm.legal_request_status(req_id, ((payload or {}).get("status") or "").strip())


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


class EditOverlayRequest(BaseModel):
    source_id: str
    fragment_id: str
    effective_start_sec: float
    effective_end_sec: float
    excluded: bool = False
    edit_type: str = "TRIM"
    root_fragment_id: str | None = None
    parent_fragment_id: str | None = None
    overlay_id: str | None = None
    metadata_json: dict | None = None
    # [조각 이력] 어느 프로젝트에서의 정밀조정인지 — 실측: 기존 44행 전부 None이던 결함
    program_id: str | None = None


@app.post("/edit-overlay")
async def upsert_edit_overlay(req: EditOverlayRequest, db: Session = Depends(get_db)):
    from archive.db_models import EditOverlayTable
    import datetime as _dt
    oid = req.overlay_id or f"OVL_{req.source_id}_{req.fragment_id}"
    row = db.query(EditOverlayTable).filter_by(overlay_id=oid).first()
    if row:
        row.effective_start_sec = req.effective_start_sec
        row.effective_end_sec = req.effective_end_sec
        row.excluded = req.excluded
        row.edit_type = req.edit_type
        row.root_fragment_id = req.root_fragment_id
        row.parent_fragment_id = req.parent_fragment_id
        row.metadata_json = req.metadata_json or {}
        if req.program_id:
            row.program_id = req.program_id
        row.updated_at = _dt.datetime.now()
    else:
        row = EditOverlayTable(
            overlay_id=oid,
            source_id=req.source_id,
            fragment_id=req.fragment_id,
            effective_start_sec=req.effective_start_sec,
            effective_end_sec=req.effective_end_sec,
            excluded=req.excluded,
            edit_type=req.edit_type,
            root_fragment_id=req.root_fragment_id,
            parent_fragment_id=req.parent_fragment_id,
            metadata_json=req.metadata_json or {},
            program_id=req.program_id,
        )
        db.add(row)
    db.commit()
    # [조각 이력] 편집(edited) 사건 기록 — 사용자가 이 조각의 경계를 직접
    # 만졌다는 사실은 원본의 자산 이력. 조각(원 경계)은 semantic_fragments에서
    # 역조회해 자연키를 정확히 잡는다(overlay 좌표는 수정 후 값이므로). 비차단.
    try:
        from engine import fragment_vault as _fvO
        from archive.db_models import SemanticFragmentTable as _SFT
        _sf = db.query(_SFT).filter_by(fragment_id=req.fragment_id).first()
        _st, _en = (_sf.start, _sf.end) if _sf else (req.effective_start_sec, req.effective_end_sec)
        _pgname = None
        if req.program_id:
            _pg2 = db.query(ProgramTable).filter_by(program_id=req.program_id).first()
            _pgname = _pg2.name if _pg2 else None
        _n = _fvO.record_events([{
            "source_id": req.source_id, "start": _st, "end": _en,
            "fragment_id": req.fragment_id,
            "event_kind": "edited", "ref_id": oid,
            "program_id": req.program_id, "program_name": _pgname,
            "detail": {"edit_type": req.edit_type,
                       "after": [req.effective_start_sec, req.effective_end_sec],
                       "excluded": req.excluded},
        }])
        if _n:
            print(f"[VAULT-EVENT] edited 기록: {oid}")
    except Exception as _ve:
        print(f"[VAULT-EVENT] edited 기록 실패 (비차단): {_ve}")
    return {"ok": True, "overlay_id": oid}


@app.get("/edit-overlay/{source_id}")
async def get_edit_overlay(source_id: str, db: Session = Depends(get_db)):
    from archive.db_models import EditOverlayTable
    rows = db.query(EditOverlayTable).filter_by(source_id=source_id).all()
    return [
        {
            "overlay_id": r.overlay_id,
            "source_id": r.source_id,
            "fragment_id": r.fragment_id,
            "effective_start_sec": r.effective_start_sec,
            "effective_end_sec": r.effective_end_sec,
            "excluded": r.excluded,
            "edit_type": r.edit_type,
            "root_fragment_id": r.root_fragment_id,
            "parent_fragment_id": r.parent_fragment_id,
            "metadata_json": r.metadata_json,
        }
        for r in rows
    ]


# ── PBE 라우트 ──────────────────────────────────────────────────────
# [GHOST 소각] ContextRequest(구 2조각 seam 문맥 요청 모델) 제거 — /pbe/context 라우트 소각과 동반.

class PanoramaExtractRequest(BaseModel):
    fragments: list[dict]
    # [PBE-DENSITY] 파노라마 프레임 수 (기본 12). 12가 아니면 P_{fid}_d{n}_{i}.jpg 로 캐시 분리.
    num_frames: int = 12


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
        
    # ffmpeg batch panorama 추출을 동기 실행(완료까지 대기) 후 응답 — 404 레이스 근원 제거
    import asyncio
    loop = asyncio.get_event_loop()
    _n = max(4, min(int(req.num_frames or 12), 48))  # [PBE-DENSITY] 폭주 방지 상한
    await loop.run_in_executor(None, video_engine.batch_extract_panoramas, None, enriched_fragments, 4, _n)
    return {"status": "COMPLETED", "count": len(enriched_fragments), "num_frames": _n}


# [GHOST 소각 — 구 2조각 PBE 백엔드] /pbe/context·apply·suggest·analyze 라우트 4개와
# 전용 모델(BoundaryChange·SmartSuggest·PBEChat Request), engine/boundary_editor.py·pbe_logic.py 제거.
# 근거: STEP C 대장 #1·2·3 (프로덕션 도달 경로 0 증명), 헌장 §6·§10. 복원은 git 이력.

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


# ── [B-4] 프로젝트 생애주기 라우트 (1급 독립체: 생성/목록/작업상태) ──────────────

class ProjectCreateRequest(BaseModel):
    name: Optional[str] = None
    source_ids: Optional[list[str]] = None

_PROJECT_NAMES = [
    # 별 (Stars)
    "Sirius", "Vega", "Rigel", "Antares", "Deneb", "Betelgeuse", "Aldebaran",
    "Arcturus", "Spica", "Pollux", "Castor", "Procyon", "Achernar", "Fomalhaut",
    "Capella", "Altair", "Regulus", "Canopus", "Acrux", "Mimosa", "Hadar",
    "Adhara", "Shaula", "Gacrux", "Avior", "Sargas", "Atria", "Alnilam",
    "Alioth", "Dubhe", "Mirach", "Alnitak", "Mizar", "Merak", "Thuban",
    "Kochab", "Schedar", "Caph", "Tarazed", "Alcyone", "Celaeno", "Merope",
    "Electra", "Maia", "Sterope", "Pleione", "Atlas", "Alderamin", "Alphecca",
    "Unukalhai",
    # 꽃 (Flowers)
    "Rose", "Dahlia", "Lavender", "Cosmos", "Camellia", "Peony", "Iris",
    "Lotus", "Magnolia", "Jasmine", "Violet", "Lily", "Orchid", "Tulip",
    "Poppy", "Zinnia", "Marigold", "Hyacinth", "Freesia", "Gardenia",
    "Begonia", "Azalea", "Wisteria", "Clover", "Primrose", "Aster",
    "Narcissus", "Anemone", "Cyclamen", "Verbena", "Delphinium", "Foxglove",
    "Hollyhock", "Columbine", "Larkspur", "Echinacea", "Lobelia", "Salvia",
    "Chamomile", "Heather", "Valerian", "Yarrow", "Amaranth", "Bluebell",
    "Buttercup", "Carnation", "Chrysanthemum", "Daffodil", "Forget-me-not",
    "Sunflower",
]

@app.post("/projects")
async def create_project(req: ProjectCreateRequest, db: Session = Depends(get_db)):
    """[B-4] '+' 버튼이 부르는 진짜 새 프로젝트 생성. 빈 그릇(schema_version=2)을 만들고 program_id 반환."""
    import uuid, datetime
    program_id = f"proj_{uuid.uuid4().hex[:12]}"
    if req.name:
        name = req.name
    else:
        import random
        existing = {p.name for p in db.query(ProgramTable).filter_by(schema_version=2).all()}
        available = [n for n in _PROJECT_NAMES if n not in existing]
        if not available:
            available = [f"{n} 2" for n in _PROJECT_NAMES if f"{n} 2" not in existing]
        name = random.choice(available) if available else f"Project {uuid.uuid4().hex[:6]}"
    now = datetime.datetime.now()
    pg = ProgramTable(program_id=program_id, name=name, status="DRAFT",
                      schema_version=2, last_updated_at=now, created_at=now)
    db.add(pg)
    # [FIX-PROJECT-SOURCES-PERSIST] 프로젝트 생성 시 업로드된 source_id를 즉시 연결
    for idx, sid in enumerate(req.source_ids or []):
        if not sid:
            continue
        existing_link = db.query(ProjectSourceTable).filter_by(program_id=program_id, source_id=sid).first()
        if not existing_link:
            db.add(ProjectSourceTable(
                program_id=program_id,
                source_id=sid,
                display_order=idx,
                added_at=now.isoformat(),
            ))
    db.commit()
    return {"status": "SUCCESS", "program_id": program_id, "name": name}


class ProjectSourcesEditRequest(BaseModel):
    source_ids: list[str]


@app.post("/projects/{program_id}/sources")
async def add_project_sources(program_id: str, req: ProjectSourcesEditRequest, db: Session = Depends(get_db)):
    """[UI-②] 기존 프로젝트에 소스 추가 연결 (멱등). display_order는 기존 뒤로 이어붙임."""
    import datetime
    from sqlalchemy import func as _f
    now = datetime.datetime.now()
    base = db.query(_f.max(ProjectSourceTable.display_order)).filter_by(program_id=program_id).scalar()
    order = (base + 1) if base is not None else 0
    added = []
    for sid in (req.source_ids or []):
        if not sid:
            continue
        if db.query(ProjectSourceTable).filter_by(program_id=program_id, source_id=sid).first():
            continue
        db.add(ProjectSourceTable(program_id=program_id, source_id=sid,
                                  display_order=order, added_at=now.isoformat()))
        order += 1
        added.append(sid)
    db.commit()
    print(f"[UI-②] project {program_id} sources added: {added}")
    return {"status": "OK", "added": added}


@app.delete("/projects/{program_id}/sources/{source_id}")
async def remove_project_source(program_id: str, source_id: str, db: Session = Depends(get_db)):
    """[UI-②] 프로젝트에서 소스 연결 해제 (소스 원본/조각은 보존 — 다른 프로젝트 공유 안전)."""
    row = db.query(ProjectSourceTable).filter_by(program_id=program_id, source_id=source_id).first()
    if not row:
        return {"status": "NOT_FOUND"}
    db.delete(row)
    db.commit()
    print(f"[UI-②] project {program_id} source unlinked: {source_id}")
    return {"status": "REMOVED", "source_id": source_id}


# ═══════════════════════════════════════════════════════════════════
#   [SNS-YT] YouTube 실업로드 / [SETTINGS] 저장공간 / [ACCOUNT] 통계
# ═══════════════════════════════════════════════════════════════════

@app.get("/sns/youtube/status")
async def sns_yt_status():
    from engine import sns_youtube
    return sns_youtube.status()


@app.post("/sns/youtube/connect")
async def sns_yt_connect():
    """브라우저 OAuth (이 PC 화면에 구글 로그인 창이 열림)."""
    import asyncio
    from engine import sns_youtube
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sns_youtube.connect)


@app.delete("/sns/youtube/connect")
async def sns_yt_disconnect():
    from engine import sns_youtube
    return sns_youtube.disconnect()


class YtUploadRequest(BaseModel):
    export_id: str
    title: str
    description: str = ""
    privacy: str = "private"


@app.post("/sns/youtube/upload")
async def sns_yt_upload(req: YtUploadRequest, db: Session = Depends(get_db)):
    import asyncio
    from engine import sns_youtube
    row = db.query(ExportResultTable).filter(ExportResultTable.id == req.export_id).first()
    if not row:
        return {"status": "ERROR", "message": f"export 없음: {req.export_id}"}
    fpath = row.output_path_internal
    if not fpath or not os.path.exists(fpath):
        # output_url(/static/...)로 폴백 해석
        rel = (row.output_url or "").replace("/static/", "")
        fpath = str(STORAGE_DIR / rel)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: sns_youtube.upload(fpath, req.title, req.description, req.privacy))
    if result.get("status") == "OK":
        db.add(PublishedTable(
            publish_id=f"PUB_{uuid.uuid4().hex[:8].upper()}",
            program_id=row.program_id, platform="youtube",
            final_video_path=result.get("url"), title=req.title,
            published_at=datetime.datetime.now()))
        db.commit()
    return result


@app.get("/settings/storage")
async def settings_storage():
    """실측 저장공간 사용량 (폴더별)."""
    def dir_size(p):
        total = 0
        try:
            for root, _, files in os.walk(p):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        except Exception:
            pass
        return total
    targets = {
        "원본 영상": STORAGE_DIR / "uploads",
        "제안 미리보기": STORAGE_DIR / "proposal_previews",
        "미리보기 클립": STORAGE_DIR / "preview_clips",
        "썸네일/파노라마": STORAGE_DIR / "thumbnails",
        "내보낸 영상": STORAGE_DIR / "exports",
        "재생 프록시": STORAGE_DIR / "proxies",
        "얼굴 팔레트": STORAGE_DIR / "faces",
        "검색 키프레임": BACKEND_STORAGE_DIR / "search_keyframes",
    }
    items = [{"label": k, "bytes": dir_size(v)} for k, v in targets.items()]
    import shutil as _sh
    free = None
    try:
        free = _sh.disk_usage(str(STORAGE_DIR)).free
    except Exception:
        pass
    return {"status": "OK", "items": items, "disk_free_bytes": free}


class CleanupRequest(BaseModel):
    target: str  # previews | panorama


@app.post("/settings/cleanup")
async def settings_cleanup(req: CleanupRequest):
    """재생성 가능한 캐시만 안전 삭제. previews=제안/클립 미리보기, panorama=P_* 프레임."""
    removed = 0
    freed = 0
    if req.target == "previews":
        for d in (STORAGE_DIR / "proposal_previews", STORAGE_DIR / "preview_clips"):
            if d.is_dir():
                for f in d.iterdir():
                    try:
                        freed += f.stat().st_size
                        f.unlink()
                        removed += 1
                    except OSError:
                        pass
    elif req.target == "panorama":
        d = STORAGE_DIR / "thumbnails"
        if d.is_dir():
            for f in d.glob("P_*.jpg"):
                try:
                    freed += f.stat().st_size
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
    else:
        return {"status": "ERROR", "message": "unknown target"}
    print(f"[SETTINGS] cleanup {req.target}: {removed} files, {freed//1024//1024}MB freed")
    return {"status": "OK", "removed": removed, "freed_bytes": freed}


@app.get("/settings/gates")
async def settings_gates():
    """검증 게이트 현재 상태 (읽기 전용)."""
    keys = ["CCUT_HUB_PLAN", "CCUT_AUTO_REINDEX", "CCUT_SINGLE_CACHE",
            "CCUT_LEGACY_NARRATIVE", "CCUT_REVISION", "CCUT_QUALITY_LOG",
            "CCUT_PERSON_REQUERY", "CCUT_LEDGER_KEEP", "MIRROR_ENABLED",
            "CCUT_COMPOUND_INTENT", "EDIT_CONTRACT_V2", "CCUT_STORY_GATE",
            "CCUT_RUBRIC_ENABLED", "CCUT_MODE_GATE"]
    return {"status": "OK", "gates": {k: os.getenv(k) or "" for k in keys}}


@app.get("/account/stats")
async def account_stats(db: Session = Depends(get_db)):
    """실데이터 사용 통계."""
    from sqlalchemy import func as _f
    projects = db.query(_f.count(ProgramTable.program_id)).filter(
        ProgramTable.schema_version == 2, ProgramTable.deleted_at.is_(None)).scalar() or 0
    sources = db.query(_f.count(SourceTable.source_id)).scalar() or 0
    total_dur = db.query(_f.sum(SourceTable.duration)).scalar() or 0
    exports = db.query(_f.count(ExportResultTable.id)).scalar() or 0
    published = db.query(_f.count(PublishedTable.publish_id)).scalar() or 0
    import sqlite3 as _sq
    con = _sq.connect(str(BACKEND_DIR / "ccut_app.db"))
    frags = con.execute("SELECT COUNT(*) FROM semantic_fragments").fetchone()[0]
    try:
        persons = con.execute("SELECT COUNT(*) FROM persons WHERE status='named'").fetchone()[0]
        person_names = [r[0] for r in con.execute("SELECT name FROM persons WHERE status='named'")]
    except Exception:
        persons, person_names = 0, []
    con.close()
    return {"status": "OK", "stats": {
        "projects": projects, "sources": sources,
        "total_video_sec": round(total_dur or 0),
        "fragments": frags, "exports": exports, "published": published,
        "named_persons": persons, "person_names": person_names,
    }}


# ═══════════════════════════════════════════════════════════════════
#   [PERSON-PALETTE] 사람 팔레트 — 얼굴 군집 스캔 / 이름 저장 / 거부
# ═══════════════════════════════════════════════════════════════════

@app.post("/persons/scan/{project_id}")
async def persons_scan(project_id: str):
    """프로젝트 키프레임에서 얼굴 검출·군집 (YuNet+SFace, CPU). 멱등."""
    import asyncio
    from engine import face_palette
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, face_palette.scan_project, project_id)


@app.get("/persons/pending")
async def persons_pending(project_id: str = None):
    from engine import face_palette
    return {"status": "OK", "persons": face_palette.list_pending(project_id)}


@app.get("/persons/names")
async def persons_names():
    """저장된 인물 이름 목록 — 프론트 편집 명령 문지기의 동적 어휘."""
    from engine.hub import _named_persons
    return {"status": "OK", "names": _named_persons()}


class PersonNameRequest(BaseModel):
    name: str
    aliases: list = None  # [PERSON-ALIAS] 애칭(옵션). rename 시 옛 이름은 자동 보존.


@app.post("/persons/{person_id}/name")
async def persons_name(person_id: str, req: PersonNameRequest):
    from engine import face_palette
    return face_palette.set_name(person_id, req.name, aliases=req.aliases)


@app.delete("/persons/{person_id}")
async def persons_reject(person_id: str):
    from engine import face_palette
    return face_palette.reject(person_id)


class EditIntentRouteRequest(BaseModel):
    # [422 사건 2026-07-06] `str = None`은 pydantic v2에서 null 입력을 거부한다 —
    # 제안 미선택 상태의 프론트가 selected_proposal_id: null을 보내면 422 →
    # 프론트가 구 메뉴판 폴백("자유롭게 대화하는 AI는 아니에요")으로 강등되던 원인.
    project_id: Optional[str] = None
    source_ids: list = []
    input_text: str
    recent_messages: list = []
    selected_proposal_id: Optional[str] = None
    # [조각 라벨 지정 편집] 프론트 조각맵 타일 라벨 -> 조각ID 매핑 ("K1" -> "SF_xxx")
    fragment_labels: dict = {}


def _xl_source_label(n: int) -> str:
    s = ""
    while True:
        s = chr(65 + (n % 26)) + s
        n = n // 26 - 1
        if n < 0:
            return s


def _project_fragment_labels(project_id: str | None) -> dict:
    if not project_id:
        return {}
    try:
        from database import SessionLocal
        with SessionLocal() as db:
            links = (
                db.query(ProjectSourceTable)
                .filter_by(program_id=project_id)
                .order_by(ProjectSourceTable.display_order)
                .all()
            )
            out = {}
            for idx, link in enumerate(links):
                src_label = _xl_source_label(idx)
                frags = bams.get_semantic_fragments(link.source_id)
                if not frags:
                    frags = bams.get_fragments_by_source(link.source_id)
                roots = []
                for f in sorted(frags or [], key=lambda x: float(x.get("start") or x.get("start_sec") or x.get("start_time") or 0)):
                    fid = str(f.get("fragment_id") or "").replace("_L", "").replace("_R", "")
                    fid = re.sub(r"_M\d*$", "", fid)
                    if fid and fid not in roots:
                        roots.append(fid)
                for pos, fid in enumerate(roots, 1):
                    out[f"{src_label}{pos}"] = fid
            return out
    except Exception as e:
        print(f"[ROUTE-EDIT][WARN] project fragment label gauge failed ({e})")
        return {}


def _merged_fragment_labels(req: EditIntentRouteRequest) -> dict:
    project_labels = _project_fragment_labels(req.project_id)
    client_labels = {str(k).upper(): v for k, v in (req.fragment_labels or {}).items() if v}
    return {**project_labels, **client_labels}


def _unknown_fragment_label_route(input_text: str, labels: dict) -> dict | None:
    t = (input_text or "").strip()
    hits = re.findall(r"[A-Za-z]{1,2}\d{1,3}", t)
    if not hits or not labels:
        return None
    known = {str(k).upper() for k in labels.keys()}
    unknown = []
    for h in hits:
        u = h.upper()
        if u not in known and re.match(r"^[A-Z]\d{1,3}$", u):
            unknown.append(u)
    label_only = any(re.search(re.escape(u) + r"\s*(?:들|번)?만", t, re.IGNORECASE) for u in unknown)
    if not unknown or not label_only:
        return None
    avail = ", ".join(sorted(known)[:12])
    return {
        "status": "OK",
        "action": "ask_clarification",
        "normalized_instruction": None,
        "reply": f"{', '.join(unknown)}은 지금 조각맵에 없는 번호예요. 현재 있는 조각: {avail}{'…' if len(known) > 12 else ''}. 다시 지정해 주시겠어요?",
        "confidence": 0.9,
        "matched": {"kind": "fragment_labels_unknown", "unknown": unknown},
        "via": "deterministic",
    }


def _rubric_direct_route(input_text: str) -> dict | None:
    try:
        from engine import converse as _cv
        direct = _cv.rubric_direct_decision(input_text)
    except Exception as e:
        print(f"[ROUTE-EDIT][WARN] rubric_direct failed ({e})")
        return None
    if not direct:
        return None
    params = direct.get("params") or {}
    r = {
        "status": "OK",
        "action": "run_proposal",
        "normalized_instruction": params.get("instruction"),
        "reply": direct.get("say") or "네, 그 조건으로 골라볼게요.",
        "confidence": 0.95,
        "matched": direct.get("matched") or {"kind": "rubric_direct"},
        "via": "rubric_direct",
        "params": params,
    }
    if params.get("rubric"):
        r["rubric"] = params.get("rubric")
    if params.get("count"):
        r["count"] = params.get("count")
    return r


@app.post("/intent/route-edit")
async def route_edit_intent_api(req: EditIntentRouteRequest):
    """[INTENT-ROUTER] 종업원 — 프론트 메뉴판 정규식을 대체. 프론트는 말을 거의
    그대로 보내고, 실행/되묻기/안내 판단은 여기서 한다 (결정론 사다리 → Qwen 폴백).
    read-only — proposal 실행은 프론트가 응답의 action을 보고 별도 호출."""
    import asyncio
    from engine.intent_router import route_edit_intent

    def _run():
        labels = _merged_fragment_labels(req)
        r = (
            _unknown_fragment_label_route(req.input_text, labels)
            or _rubric_direct_route(req.input_text)
            or route_edit_intent(
                source_ids=req.source_ids, input_text=req.input_text,
                recent_messages=req.recent_messages,
                selected_proposal_id=req.selected_proposal_id,
                fragment_labels=labels, project_id=req.project_id)
        )
        # [관문D 2026-07-21 국장승인] 라벨교정 실행 시 조각 판단근거(scene·speech·context)를
        #   route 응답에 노출 — chat이 쓰는 엔드포인트가 route-edit이므로 여기 실어야 화면 도달.
        if isinstance(r, dict) and r.get("candidate_fragment_ids"):
            try:
                from engine.converse import _candidate_evidence
                r["candidate_evidence"] = _candidate_evidence(r["candidate_fragment_ids"])
            except Exception as _e:
                print(f"[ROUTE-EDIT][WARN] candidate_evidence 실패 ({_e})")
        return r

    return await asyncio.get_event_loop().run_in_executor(None, _run)


@app.post("/intent/route-edit/stream")
async def route_edit_intent_stream_api(req: EditIntentRouteRequest):
    """[F2 스트리밍 — 헌장 §3-부칙] 허브 대화 reply를 토큰 단위 SSE로 흘린다.
    결정론 사다리/편집 분류 응답은 즉답 final 1건(스트리밍 불요 경로 유지),
    자유대화(answer_only)만 stream_smalltalk 토큰 스트림. 응답 내용·구조는
    일괄 엔드포인트와 동일(final.result = 기존 계약 그대로) — F6 후퇴 없음.
    TTFT는 dev 로그([F2-TTFT])로 계측. 위생 위반·실패는 고정문구 강등(무언 실패 금지)."""
    import json as _json
    import time as _time
    from fastapi.responses import StreamingResponse
    from engine.intent_router import (
        route_edit_intent,
        stream_smalltalk,
        smalltalk_retry_max,
        validate_smalltalk_reply,
    )

    def _sse(obj):
        return "data: " + _json.dumps(obj, ensure_ascii=False) + "\n\n"

    def gen():
        t0 = _time.time()
        labels = _merged_fragment_labels(req)
        r = (
            _unknown_fragment_label_route(req.input_text, labels)
            or _rubric_direct_route(req.input_text)
            or route_edit_intent(
                source_ids=req.source_ids, input_text=req.input_text,
                recent_messages=req.recent_messages,
                selected_proposal_id=req.selected_proposal_id,
                fragment_labels=labels, defer_chat=True, project_id=req.project_id)
        )
        # [관문D 2026-07-21 국장승인] 라벨교정 실행 시 조각 판단근거(scene·speech·context)를
        #   route 응답에 노출 — chat이 쓰는 엔드포인트가 route-edit이므로 여기 실어야 화면 도달.
        if isinstance(r, dict) and r.get("candidate_fragment_ids"):
            try:
                from engine.converse import _candidate_evidence
                r["candidate_evidence"] = _candidate_evidence(r["candidate_fragment_ids"])
            except Exception as _e:
                print(f"[ROUTE-EDIT][WARN] candidate_evidence 실패 ({_e})")
        sc = r.pop("_stream_chat", None)
        if not sc:
            # 결정론/편집 분류 — 완성 응답이 이미 있다. 즉답 1건 (스트리밍 불요 경로)
            print(f"[F2-TTFT] path=direct first_out_ms={int((_time.time() - t0) * 1000)} "
                  f"action={r.get('action')}")
            yield _sse({"type": "final", "result": r})
            return
        yield _sse({"type": "meta", "action": "answer_only"})
        first_ms = None
        final_text = None
        partial_text = ""
        aborted = False
        for kind, payload in stream_smalltalk(req.input_text, req.recent_messages,
                                              facts=sc.get("facts") or ""):
            if kind == "token":
                if first_ms is None:
                    first_ms = int((_time.time() - t0) * 1000)
                    print(f"[F2-TTFT] path=stream first_token_ms={first_ms}")
                partial_text += payload
            elif kind == "done":
                final_text = payload
            elif kind == "abort":
                aborted = True
        stream_text = validate_smalltalk_reply(final_text or partial_text)
        if not stream_text and smalltalk_retry_max() > 0:
            retry_text = ""
            retry_aborted = False
            for kind, payload in stream_smalltalk(req.input_text, req.recent_messages,
                                                  facts=sc.get("facts") or ""):
                if kind == "token":
                    retry_text += payload
                elif kind == "done":
                    retry_text = payload
                elif kind == "abort":
                    retry_aborted = True
            if not retry_aborted:
                stream_text = validate_smalltalk_reply(retry_text)
        if stream_text:
            yield _sse({"type": "token", "text": stream_text})
        final_text = stream_text or "네, 듣고 있어요. 편하게 이야기해 주세요."
        r["reply"] = final_text
        if stream_text:
            r["stream_text"] = stream_text
            r["stream_complete"] = True
        else:
            r["stream_complete"] = False
        print(f"[F2-TTFT] path=stream total_ms={int((_time.time() - t0) * 1000)} "
              f"reply_len={len(final_text)} aborted={aborted} valid={bool(stream_text)}")
        yield _sse({"type": "final", "result": r})

    return StreamingResponse(gen(), media_type="text/event-stream")


class ConverseRequest(BaseModel):
    project_id: Optional[str] = None
    source_ids: list = []
    input_text: str
    selected_proposal_id: Optional[str] = None
    fragment_labels: dict = {}
    # [R2-2 D+E] 현재 화면 조각맵 라이브 요약 {mode,count,duration,proposal_id} —
    # 스냅샷의 '지금 안'을 DB 최신이 아니라 이 값(화면 진실)으로 채운다.
    current_view: dict = {}


# [QWEN-R2 C] det 사다리 '확실 매칭'만 즉답 채택 — 나머지(open_theme·되묻기·자유그물)는
# 큐원 판단으로. 고지/사실 계열은 det 문구 그대로(숫자 정확성·보안), 편집 계열은 발화권 이전.
# [S-5] pace("길게/짧게/템포")는 det 채택 제외 — 분량은 큐원 ⑤(count·target_length
# 숫자화)가 담당한다. det pace가 params 없이 재제안만 돌려 분량이 불변하던 우회 절단.
_DET_FINAL_KINDS = {
    "intent_clear", "retrigger", "show", "fragment_labels",
    "fragment_labels_unavailable", "fragment_labels_empty", "fragment_labels_unknown",
    "honest_no_frame_trim", "honest_restore_hint", "self_intro",
    "revision", "person", "person_alias", "vocab", "confirm"}
_DET_EDIT_KINDS = {"intent_clear", "retrigger", "revision", "person", "person_alias",
                   "vocab", "confirm"}
_NEW_TO_OLD_ACTION = {"revise": "revise_current", "clear_intent": "intent_clear",
                      "answer": "answer_only", "clarify": "ask_clarification"}


@app.post("/chat/converse/stream")
async def chat_converse_stream(req: ConverseRequest):
    """[QWEN-R2 왕복 계약] 발화 → (det 확실 매칭 즉답 | 큐원 {action,params,say})
    → 검증 → say 스트림. SSE: meta → token* → final. final.result는 구 route-edit
    계약과 동형(action 구명칭) — 프론트 소비부 호환."""
    import json as _json
    from fastapi.responses import StreamingResponse
    from engine.intent_router import route_edit_intent
    from engine import converse as _cv

    def _sse(obj):
        return "data: " + _json.dumps(obj, ensure_ascii=False) + "\n\n"

    def gen():
        import time as _time
        t0 = _time.time()
        pid = req.project_id or "default_project"
        direct = _cv.rubric_direct_decision(req.input_text)
        if direct:
            action = direct["action"]
            params = direct["params"]
            old = _NEW_TO_OLD_ACTION.get(action, action)
            r = {"status": "OK", "action": old,
                 "reply": direct["say"], "confidence": 0.95,
                 "via": "rubric_direct",
                 "matched": direct.get("matched") or {"kind": "rubric_direct"},
                 "normalized_instruction": params.get("instruction"),
                 "params": params}
            _cv.persist_decision(pid, action, params)
            print(f"[F2-TTFT] path=rubric-direct first_out_ms={int((_time.time() - t0) * 1000)} "
                  f"action={action} params={_json.dumps(params, ensure_ascii=False)}")
            yield _sse({"type": "meta", "action": old,
                        "params": params, "via": "rubric_direct"})
            yield _sse({"type": "token", "text": direct["say"]})
            yield _sse({"type": "final", "result": r})
            return
        # ── 결정론 프리패스 (회귀 금지선: 확실 매칭 즉답 생존) ──
        det = route_edit_intent(
            source_ids=req.source_ids, input_text=req.input_text,
            recent_messages=None, selected_proposal_id=req.selected_proposal_id,
            fragment_labels=req.fragment_labels, allow_llm=False, project_id=pid)
        kind = str((det.get("matched") or {}).get("kind") or "")
        is_person_composite = (det.get("matched") or {}).get("type") == "person"
        adopt = (kind in _DET_FINAL_KINDS or is_person_composite
                 or det.get("action") in ("show_fragments", "ask_include_archive"))
        # [D12 결함 절단] 의문문·긴 복합문 속 부분매칭("왜 3개만...?"의 '3개'→count)은
        # det 확신이 아니다 — 편집 계열 채택을 물리고 큐원이 뜻을 읽는다.
        # 앵커 정규식 계열(intent_clear·retrigger)과 고지/사실 계열은 가드 밖.
        _t = (req.input_text or "").strip()
        if adopt and (("?" in _t or "？" in _t or len(_t) > 40)
                      and (kind in ("revision", "person", "person_alias",
                                    "vocab", "pace", "confirm")
                           or is_person_composite)):
            print(f"[QWEN-R2] det 오채택 가드: kind={kind} q/long -> 큐원 위임")
            adopt = False
        if adopt:
            r = dict(det)
            # [R2-3 다] det vocab이 잡은 조각 수(matched.count)를 params.count로 표면화 —
            # 평문 "8개로"가 det 경로로 가도 프론트 requested_count로 이어져 A·B 대칭 적용.
            _mc = (det.get("matched") or {}).get("count")
            if isinstance(_mc, int) and 1 <= _mc <= 40:
                r.setdefault("params", {})["count"] = _mc
            print(f"[F2-TTFT] path=det-final first_out_ms={int((_time.time() - t0) * 1000)} "
                  f"action={r.get('action')} kind={kind}")
            if kind in _DET_EDIT_KINDS:
                # [④ 발화권 이전] 결정은 규칙 즉답, 접수 발화는 모델 스트림 (실패=det 문구)
                yield _sse({"type": "meta", "action": r.get("action"), "via": "det"})
                say = None
                for ev, payload in _cv.ack_say_stream(req.input_text, r.get("reply") or "", kind):
                    if ev == "token":
                        yield _sse({"type": "token", "text": payload})
                    elif ev == "done":
                        say = payload
                if say:
                    r["reply"] = say
                yield _sse({"type": "final", "result": r})
            else:
                yield _sse({"type": "final", "result": r})
            return
        # ── 큐원 판단 (이력+상태 주입, 헤더 검증, say 스트림) ──
        final = None
        first_ms = None
        for ev, payload in _cv.decide_stream(pid, req.input_text,
                                             current_view=req.current_view,
                                             fragment_labels=req.fragment_labels):
            if ev == "meta":
                old = _NEW_TO_OLD_ACTION.get(payload["action"], payload["action"])
                yield _sse({"type": "meta", "action": old,
                            "params": payload["params"],
                            "via": payload.get("via") or "qwen"})
            elif ev == "token":
                if first_ms is None:
                    first_ms = int((_time.time() - t0) * 1000)
                    print(f"[F2-TTFT] path=converse first_token_ms={first_ms}")
                yield _sse({"type": "token", "text": payload})
            else:
                final = payload
        action = final["action"]
        params = final["params"]
        r = {"status": "OK", "action": _NEW_TO_OLD_ACTION.get(action, action),
             "reply": final["say"], "confidence": 0.8, "via": "qwen",
             "matched": {"kind": f"converse_{action}"},
             "normalized_instruction": (params.get("instruction") or None)
             if action == "run_proposal" else None,
             "params": params}
        # [관문C 2026-07-20 stash이식] 라벨 교정 후보를 프론트로 흘려 실행층이 keep.
        if params.get("candidate_fragment_ids"):
            r["candidate_fragment_ids"] = params.get("candidate_fragment_ids")
        # [관문D 2026-07-20] candidate 판단 근거(scene·speech·context)를 응답에 노출.
        if params.get("candidate_evidence"):
            r["candidate_evidence"] = params.get("candidate_evidence")
        if action == "revise":
            r["revision"] = params
        print(f"[F2-TTFT] path=converse total_ms={int((_time.time() - t0) * 1000)} "
              f"action={action} params={_json.dumps(params, ensure_ascii=False)}")
        yield _sse({"type": "final", "result": r})

    return StreamingResponse(gen(), media_type="text/event-stream")


class ResultSayRequest(BaseModel):
    project_id: str
    facts: str


@app.post("/chat/result-say/stream")
async def chat_result_say_stream(req: ResultSayRequest):
    """[QWEN-R2 결과 재주입] 집행 결과 사실 → 큐원 완료 발화 스트림.
    숫자는 주입 사실만 — 위생 위반·실패 시 abort(프론트가 사실 문구 폴백)."""
    import json as _json
    from fastapi.responses import StreamingResponse
    from engine import converse as _cv

    def _sse(obj):
        return "data: " + _json.dumps(obj, ensure_ascii=False) + "\n\n"

    def gen():
        say = None
        for ev, payload in _cv.result_say_stream(req.project_id, req.facts):
            if ev == "token":
                yield _sse({"type": "token", "text": payload})
            elif ev == "done":
                say = payload
        yield _sse({"type": "final", "say": say})

    return StreamingResponse(gen(), media_type="text/event-stream")


class HubKeepRequest(BaseModel):
    source_ids: list
    instruction: str


@app.post("/hub/keep")
async def hub_keep(req: HubKeepRequest):
    """[L2-SPEED] 외부 도구(골든 러너)용 keep 조회. 서버 인프로세스 plan 캐시를
    재사용해 같은 명령의 중복 full-judge를 제거한다 — CCUT_SINGLE_CACHE=1이면
    /proposals/project 직후 호출 시 PLAN-CACHE 히트(0 LLM콜). 캐시 미스면 서버가
    판정 1회 수행. 조회 전용 — DB 쓰기 없음."""
    import asyncio
    from engine import hub

    def _run():
        return hub.plan_edit(list(req.source_ids), req.instruction, verbose=False)

    plan = await asyncio.get_event_loop().run_in_executor(None, _run)
    keep = sorted({k.get("fid") for k in (plan.get("keep") or []) if k.get("fid")})
    return {"status": "OK", "keep_fids": keep, "reason": plan.get("reason"),
            "intent": plan.get("intent"),
            "self_check_status": (plan.get("self_check") or {}).get("status")}


@app.get("/projects")
async def list_projects(db: Session = Depends(get_db)):
    """[B-4] 신규 구조(schema_version=2) 프로젝트 목록. project_sources 있는 것만 반환 (빈 프로젝트 숨김)."""
    import datetime
    from sqlalchemy import func
    source_counts = {
        r.program_id: r.cnt
        for r in db.query(ProjectSourceTable.program_id, func.count().label("cnt"))
                    .group_by(ProjectSourceTable.program_id).all()
    }
    used_ids = set(source_counts.keys())
    if not used_ids:
        return {"projects": []}

    # [SOFT-DELETE] 30일 경과한 휴지통 프로젝트는 자동 완전삭제(인과응보).
    import datetime as _dtp
    cutoff = _dtp.datetime.now() - _dtp.timedelta(days=30)
    expired = db.query(ProgramTable).filter(
        ProgramTable.deleted_at.isnot(None),
        ProgramTable.deleted_at < cutoff,
    ).all()
    for ex in expired:
        db.query(ProjectSourceTable).filter_by(program_id=ex.program_id).delete()
        db.delete(ex)
    if expired:
        db.commit()

    # 활성(deleted_at IS NULL) 프로젝트만 목록에 노출
    rows = db.query(ProgramTable).filter(
        ProgramTable.schema_version == 2,
        ProgramTable.program_id.in_(used_ids),
        ProgramTable.deleted_at.is_(None),
    ).all()
    rows = sorted(rows, key=lambda p: (p.last_updated_at or p.created_at or datetime.datetime.min), reverse=True)
    return {"projects": [{
        "program_id": p.program_id,
        "name": p.name,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "last_updated_at": p.last_updated_at.isoformat() if p.last_updated_at else None,
        "source_count": source_counts.get(p.program_id, 0),
    } for p in rows]}

class ProjectStateRequest(BaseModel):
    active_mode: Optional[str] = None
    chat_state: Optional[str] = None
    reserve_state: Optional[str] = None
    ui_state: Optional[str] = None

_DEAD_UI_KEYS = ("storyOrder", "proposalsIds")


def _strip_dead_ui_keys(raw):
    """[TRUTH-SINGLE-01] ui_state에서 폐기된 사본 키를 제거해 돌려준다.
    파싱 실패하면 원문 그대로 — 저장을 막지 않는다(모르는 것을 지우지 않는다)."""
    if not isinstance(raw, str):
        return raw
    try:
        obj = json.loads(raw)
    except Exception:
        return raw
    if not isinstance(obj, dict):
        return raw
    removed = [k for k in _DEAD_UI_KEYS if k in obj]
    if not removed:
        return raw
    for k in removed:
        obj.pop(k, None)
    try:
        print(f"[TRUTH-SINGLE] ui_state dead keys removed: {removed}")
    except Exception:
        pass
    return json.dumps(obj, ensure_ascii=False)


@app.post("/projects/{program_id}/state")
async def save_project_state(program_id: str, req: ProjectStateRequest, db: Session = Depends(get_db)):
    """[B-4] 작업상태 영속(A=전부): active_mode/chat/reserve/ui. None인 필드는 미변경."""
    import datetime
    # [GATE-LOOP-01 1번] 승인 후 스토리 변경을 409로 막던 가드 제거.
    #   구판: 승인 상태에서 story/보류/휴지통이 바뀌면 저장을 거절했다(story_approved_edit_locked).
    #         사용자의 조작을 차단하는 설계였고, 프론트 잠금(modeEditLocked)과 한 쌍이었다.
    #   신판: 저장을 받는다. 저장되면 sequence_hash가 승인 지문과 달라지고, story_state가
    #         approved → review로 내려가 화면이 스토리 단계로 복귀한다(복귀 루프).
    #         제안(proposals)은 지우지 않는다 — stale로 물러날 뿐이다.
    pg = db.query(ProgramTable).filter_by(program_id=program_id).first()
    if not pg:
        return {"status": "NOT_FOUND", "program_id": program_id}
    if req.active_mode is not None: pg.active_mode = req.active_mode
    if req.chat_state is not None: pg.chat_state = req.chat_state
    if req.reserve_state is not None: pg.reserve_state = req.reserve_state
    if req.ui_state is not None:
        # [TRUTH-SINGLE-01] 죽은 사본 키는 저장 시점에 걷어낸다 — 진실을 둘로 두지 않는다.
        #   storyOrder   : 표시 순서는 story.fids에서 파생 (ledger_r0._ordered_stringout_fids)
        #   proposalsIds : DB proposals가 진실. 읽는 곳 0건(전수)이고 실제로 낡아 있었다
        #                  (ui_state PROP_A_E737A9… vs DB PROP_A_79716E…).
        pg.ui_state = _strip_dead_ui_keys(req.ui_state)
    # [FIX-LIST-ORDER] 순수 UI 스냅샷(ui_state만) 저장은 '프로젝트 열람/전환'에 따른 보존일 뿐
    # 실제 작업 활동이 아니므로 recency(last_updated_at)를 갱신하지 않는다.
    # (목록이 클릭만으로 맨 위로 튀는 현상 제거 — Claude 채팅 사이드바 방식)
    is_pure_ui_snapshot = (
        req.active_mode is None and req.chat_state is None
        and req.reserve_state is None and req.ui_state is not None
    )
    if not is_pure_ui_snapshot:
        pg.last_updated_at = datetime.datetime.now()
    db.commit()
    return {"status": "SAVED", "program_id": program_id}

@app.get("/projects/{program_id}/state")
async def get_project_state(program_id: str, db: Session = Depends(get_db)):
    """[B-4] 작업상태 복원."""
    pg = db.query(ProgramTable).filter_by(program_id=program_id).first()
    if not pg:
        return {"status": "NOT_FOUND", "program_id": program_id}
    return {
        "status": "OK",
        "program_id": program_id,
        "name": pg.name,
        "active_mode": pg.active_mode,
        "chat_state": pg.chat_state,
        "reserve_state": pg.reserve_state,
        "ui_state": pg.ui_state,
    }

class TimelineAppendRequest(BaseModel):
    entries: list = []


@app.post("/projects/{program_id}/timeline")
async def timeline_append(program_id: str, req: TimelineAppendRequest):
    """[TIMELINE] append-only 이벤트 로그 — 사건 발생 즉시 기록.
    client_id 멱등이라 재전송·멀티탭에 안전. 과거 행 불변 = 역사 파괴 불가."""
    from engine import timeline_store
    added = timeline_store.append_entries(program_id, req.entries)
    return {"status": "OK", "added": added}


@app.get("/projects/{program_id}/timeline")
async def timeline_fetch(program_id: str, limit: int = 300, before: int = None,
                         db: Session = Depends(get_db)):
    """[TIMELINE] 최근 limit개(시간순) + before 커서 페이지네이션.
    v1 chat_state blob은 첫 조회 때 행으로 자동 이관 후 비운다."""
    from engine import timeline_store
    pg = db.query(ProgramTable).filter_by(program_id=program_id).first()
    if pg is not None and pg.chat_state:
        n = timeline_store.migrate_from_blob(program_id, pg.chat_state)
        pg.chat_state = None
        db.commit()
        print(f"[TIMELINE] chat_state blob -> 행 자동 이관: {program_id} {n}건")
    entries = timeline_store.fetch(program_id, limit=limit, before=before)
    return {"status": "OK", "entries": entries,
            "has_more": len(entries) == int(limit)}


@app.delete("/projects/{program_id}")
async def delete_project(program_id: str, db: Session = Depends(get_db)):
    """[SOFT-DELETE] 프로젝트를 휴지통으로 이동(status='DELETED' + deleted_at).
    원본/제안/내보낸영상 연결은 보존 — 30일간 복원 가능, 이후 자동 완전삭제.
    """
    import datetime as _dtd
    pg = db.query(ProgramTable).filter_by(program_id=program_id).first()
    if not pg:
        return {"status": "NOT_FOUND", "program_id": program_id}
    try:
        pg.status = "DELETED"
        pg.deleted_at = _dtd.datetime.now()
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"프로젝트 소프트삭제 실패: {e}")
    purge_at = pg.deleted_at + _dtd.timedelta(days=30)
    return {
        "status": "SOFT_DELETED",
        "program_id": program_id,
        "deleted_at": pg.deleted_at.isoformat(),
        "purge_at": purge_at.isoformat(),
    }


@app.post("/projects/{program_id}/restore")
async def restore_project(program_id: str, db: Session = Depends(get_db)):
    """[SOFT-DELETE] 휴지통 프로젝트를 복원(deleted_at=NULL)."""
    pg = db.query(ProgramTable).filter_by(program_id=program_id).first()
    if not pg:
        return {"status": "NOT_FOUND", "program_id": program_id}
    try:
        pg.deleted_at = None
        pg.status = "DRAFT"
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"프로젝트 복원 실패: {e}")
    return {"status": "RESTORED", "program_id": program_id, "name": pg.name}


@app.delete("/projects/{program_id}/purge")
async def purge_project(program_id: str, db: Session = Depends(get_db)):
    """[SOFT-DELETE] 즉시 완전삭제(인과응보). 복원 불가."""
    pg = db.query(ProgramTable).filter_by(program_id=program_id).first()
    if not pg:
        return {"status": "NOT_FOUND", "program_id": program_id}
    _snapshot_db_before_destructive("purge")
    try:
        db.query(ProjectSourceTable).filter_by(program_id=program_id).delete()
        db.delete(pg)
        db.commit()
    except Exception as _e:
        db.rollback()
        print(f"[DELETE-GUARD] purge rollback: {_e}")
        raise
    return {"status": "PURGED", "program_id": program_id}


class SourceNameRequest(BaseModel):
    name: str


@app.patch("/sources/{source_id}/name")
async def rename_source(source_id: str, req: SourceNameRequest, db: Session = Depends(get_db)):
    """[SOURCE] 원본 영상 표시 이름(display_name) 변경."""
    s = db.query(SourceTable).filter_by(source_id=source_id).first()
    if not s:
        return {"status": "NOT_FOUND", "source_id": source_id}
    s.display_name = (req.name or "").strip() or None
    db.commit()
    return {"status": "SUCCESS", "source_id": source_id, "title": s.title, "display_name": s.display_name}


@app.delete("/sources/{source_id}")
async def delete_source(source_id: str, mode: str = "source_only", db: Session = Depends(get_db)):
    """[SOURCE] 원본 삭제.
    - mode='source_only': 원본 mp4 파일만 디스크에서 제거(노출 위험 영상). 조각/편집 메타는 보존.
    - mode='full': 원본 파일 + 그 source의 모든 조각 데이터 + source 레코드 완전 삭제.
    proposals/export_results는 프로젝트(program) 단위이므로 건드리지 않는다.
    """
    s = db.query(SourceTable).filter_by(source_id=source_id).first()
    if not s:
        return {"status": "NOT_FOUND", "source_id": source_id}

    # 1. 원본 mp4 파일 삭제 (양쪽 mode 공통)
    file_removed = False
    if s.file_path and os.path.exists(s.file_path):
        try:
            # 영구삭제 대신 trash로 이동 (복원 가능)
            _trash_dir = STORAGE_DIR / "trash"
            _trash_dir.mkdir(parents=True, exist_ok=True)
            _ts = time.strftime("%Y%m%d_%H%M%S")
            _base = os.path.basename(s.file_path)
            _dst = _trash_dir / f"{_base}_{_ts}"
            _shutil.move(s.file_path, str(_dst))
            print(f"[SOURCE-DELETE] trash로 이동: {_dst.name}")
            file_removed = True
        except Exception as e:
            print(f"[SOURCE-DELETE] 파일 삭제 실패: {e}")

    if mode == "full":
        _snapshot_db_before_destructive("delete_source_full")
        from archive.db_models import (EvidenceTable, SemanticFragmentTable,
                                        QuickScanTable, SubtitleTable, UserIntentTable)
        import sqlite3 as _sq
        # 조각/메타 데이터 삭제 (source_id 참조)
        try:
            for T in [FragmentTable, EvidenceTable, SemanticFragmentTable,
                      QuickScanTable, SubtitleTable, UserIntentTable]:
                db.query(T).filter_by(source_id=source_id).delete()
            # fragment_index (raw, FTS 트리거 동반)
            db.execute(__import__("sqlalchemy").text(
                "DELETE FROM fragment_index WHERE source_id = :sid"), {"sid": source_id})
            db.delete(s)
            db.commit()
        except Exception as _e:
            db.rollback()
            print(f"[DELETE-GUARD] delete_source full rollback: {_e}")
            raise
        # [조각 금고] source row 자체가 사라지는 시점 — vault의 source_alive를
        # 즉시 갱신(주기 작업이 아니라 삭제 이벤트에 훅). 비차단.
        try:
            from engine import fragment_vault as _fv3
            _fv3.mark_source_alive()
        except Exception as _fv_e:
            print(f"[VAULT] source_alive 갱신 실패 (비차단): {_fv_e}")
        return {"status": "DELETED_FULL", "source_id": source_id, "file_removed": file_removed}
    else:
        # source_only: 파일만 제거, 레코드는 원본 부재 표시
        try:
            s.file_path = None
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"원본 삭제 실패: {e}")
        try:
            from engine import fragment_vault as _fv3
            _fv3.mark_source_alive()
        except Exception as _fv_e:
            print(f"[VAULT] source_alive 갱신 실패 (비차단): {_fv_e}")
        return {"status": "DELETED_SOURCE_ONLY", "source_id": source_id, "file_removed": file_removed}


@app.get("/projects/trash")
async def list_trash(db: Session = Depends(get_db)):
    """[SOFT-DELETE] 휴지통 목록 (deleted_at 있는 프로젝트, 30일 보관)."""
    import datetime as _dtt
    rows = db.query(ProgramTable).filter(ProgramTable.deleted_at.isnot(None)).all()
    out = []
    for p in rows:
        purge_at = (p.deleted_at + _dtt.timedelta(days=30)) if p.deleted_at else None
        days_left = None
        if p.deleted_at:
            days_left = max(0, 30 - (_dtt.datetime.now() - p.deleted_at).days)
        out.append({
            "program_id": p.program_id,
            "name": p.name,
            "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None,
            "purge_at": purge_at.isoformat() if purge_at else None,
            "days_left": days_left,
        })
    out.sort(key=lambda x: x["deleted_at"] or "", reverse=True)
    return {"status": "SUCCESS", "count": len(out), "trash": out}


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


# [STEP 18] Temporal Narrative Flow Learning REST endpoints
class TemporalFlowRequest(BaseModel):
    project_id: str
    proposal: dict
    success: bool

@app.post("/learning/temporal/flow")
async def run_temporal_flow_learning(req: TemporalFlowRequest):
    try:
        from learning.temporal_flow_learner import TemporalFlowLearner
        res = TemporalFlowLearner.analyze_and_learn_proposal_flow(req.project_id, req.proposal, req.success)
        return {"status": "SUCCESS", "data": res}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

@app.get("/learning/temporal/logs")
async def get_temporal_flow_logs():
    try:
        from learning.temporal_flow_learner import TemporalFlowLearner
        logs = TemporalFlowLearner.get_flow_logs()
        return {"status": "SUCCESS", "logs": logs}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


# [STEP 19] Human Watch Session REST endpoints
class HumanWatchSessionRequest(BaseModel):
    project_id: str
    viewer_id: str
    playback_actions: list
    retention_map: dict

@app.post("/learning/watch/session")
async def log_human_watch_session(req: HumanWatchSessionRequest):
    try:
        from learning.human_watch_session import HumanWatchSession
        res = HumanWatchSession.log_watch_session(
            req.project_id,
            req.viewer_id,
            req.playback_actions,
            req.retention_map
        )
        return {"status": "SUCCESS", "data": res}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

@app.get("/learning/watch/logs")
async def get_human_watch_logs():
    try:
        from learning.human_watch_session import HumanWatchSession
        logs = HumanWatchSession.get_watch_logs()
        return {"status": "SUCCESS", "logs": logs}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8011)
