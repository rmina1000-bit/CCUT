"""
fragment_api.py
---------------
FastAPI router: POST /generate-fragments

Accepts a video file upload, runs the deterministic Fragment Generator,
and returns a FragmentIndex ready for UI consumption.

Fragment dict schema (matches fragment_generator output + UI expectations):
    {
        "id":        str          e.g. "frag_0"
        "start":     float        seconds
        "end":       float        seconds
        "duration":  float        end - start
        "editStack": list         always []
    }
"""

import logging
import os
import shutil
import tempfile
import time
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from fragment_generator.fragment_generator import generate_fragments
from edit_log.edit_log import append_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=["fragments"])

# Uploaded videos storage — survives request lifecycle for browser playback
_UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "ccut_uploads")
os.makedirs(_UPLOAD_DIR, exist_ok=True)


@router.post("/generate-fragments")
async def generate(file: UploadFile = File(...)):
    t0 = time.time()
    logger.info(f"[API] 파일 수신: {file.filename}")

    suffix = os.path.splitext(file.filename or ".mp4")[1] or ".mp4"
    video_id = uuid.uuid4().hex[:12]
    video_path = os.path.join(_UPLOAD_DIR, f"{video_id}{suffix}")

    try:
        with open(video_path, "wb") as dst:
            shutil.copyfileobj(file.file, dst)
        file_size = os.path.getsize(video_path)
        logger.info(f"[API] 영상 저장: {video_path} ({file_size} bytes, {time.time()-t0:.2f}s)")

        logger.info("[API] generate_fragments() 호출 시작")
        fragments = generate_fragments(video_path)
        logger.info(f"[API] 조각 생성 완료: {len(fragments)}개, {time.time()-t0:.2f}s")
    except Exception as exc:
        import traceback
        error_msg = f"Fragment generation failed: {str(exc)}\n{traceback.format_exc()}"
        logger.error(f"[API] 오류: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg) from exc

    # Enrich with duration + video_id for browser playback
    for frag in fragments:
        frag["duration"] = round(frag["end"] - frag["start"], 3)

    append_event("FRAGMENTS_GENERATED", {"count": len(fragments)})

    logger.info(f"[API] 응답 전송: {len(fragments)}개 조각, 총 {time.time()-t0:.2f}s")
    return {
        "fragments": fragments,
        "count": len(fragments),
        "video_id": video_id,
    }


@router.get("/video/{video_id}")
async def serve_video(video_id: str):
    """Serve uploaded video for browser playback."""
    # Sanitize: only allow hex chars
    if not video_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid video_id")

    # Find the file (could be .mp4, .mov, etc.)
    for fname in os.listdir(_UPLOAD_DIR):
        if fname.startswith(video_id):
            fpath = os.path.join(_UPLOAD_DIR, fname)
            return FileResponse(fpath, media_type="video/mp4")

    raise HTTPException(status_code=404, detail="Video not found")
