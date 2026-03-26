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

from fastapi import APIRouter, File, HTTPException, UploadFile

from fragment_generator.fragment_generator import generate_fragments
from edit_log.edit_log import append_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=["fragments"])


@router.post("/generate-fragments")
async def generate(file: UploadFile = File(...)):
    t0 = time.time()
    logger.info(f"[API] 파일 수신: {file.filename}")

    suffix = os.path.splitext(file.filename or ".mp4")[1] or ".mp4"

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(tmp_fd, "wb") as dst:
            shutil.copyfileobj(file.file, dst)
        file_size = os.path.getsize(tmp_path)
        logger.info(f"[API] 임시 파일 저장 완료: {file_size} bytes, {time.time()-t0:.2f}s")

        logger.info("[API] generate_fragments() 호출 시작")
        fragments = generate_fragments(tmp_path)
        logger.info(f"[API] 조각 생성 완료: {len(fragments)}개, {time.time()-t0:.2f}s")
    except Exception as exc:
        import traceback
        error_msg = f"Fragment generation failed: {str(exc)}\n{traceback.format_exc()}"
        logger.error(f"[API] 오류: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg) from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Enrich with duration field expected by the UI
    for frag in fragments:
        frag["duration"] = round(frag["end"] - frag["start"], 3)

    append_event("FRAGMENTS_GENERATED", {"count": len(fragments)})

    logger.info(f"[API] 응답 전송: {len(fragments)}개 조각, 총 {time.time()-t0:.2f}s")
    return {"fragments": fragments, "count": len(fragments)}
