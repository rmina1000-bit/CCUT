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

import os
import shutil
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile

from fragment_generator.fragment_generator import generate_fragments
from edit_log.edit_log import append_event

router = APIRouter(tags=["fragments"])


@router.post("/generate-fragments")
async def generate(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename or ".mp4")[1] or ".mp4"

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(tmp_fd, "wb") as dst:
            shutil.copyfileobj(file.file, dst)

        fragments = generate_fragments(tmp_path)
    except Exception as exc:
        import traceback
        error_msg = f"Fragment generation failed: {str(exc)}\n{traceback.format_exc()}"
        print(error_msg)
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

    return {"fragments": fragments, "count": len(fragments)}
