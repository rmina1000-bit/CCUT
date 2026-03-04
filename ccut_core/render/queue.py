import json
from pathlib import Path
from .render_models import RenderRequest


QUEUE_DIR = Path("storage/render_queue")


def enqueue_render(request: RenderRequest) -> Path:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    path = QUEUE_DIR / f"req_v{request.version}.json"

    payload = {
        "version": request.version,
        "artifact_hash": request.artifact_hash,
        "segments": [
            {
                "id": s.segment_id,
                "start": s.start,
                "end": s.end
            }
            for s in request.segments
        ]
    }

    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8"
    )

    try:
        from observability.render_trace import trace_render
        trace_render(request.version, "QUEUED")
    except Exception:
        pass

    return path
