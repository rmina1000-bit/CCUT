import json
from pathlib import Path
from .render_executor import execute_render
from .render_models import RenderRequest, RenderSegment


QUEUE_DIR = Path("storage/render_queue")


def process_queue_once():
    if not QUEUE_DIR.exists():
        return None

    for file in sorted(QUEUE_DIR.glob("req_v*.json")):
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))

            req = RenderRequest(
                version=payload["version"],
                artifact_hash=payload["artifact_hash"],
                segments=tuple(
                    RenderSegment(
                        segment_id=s["id"],
                        start=s["start"],
                        end=s["end"]
                    )
                    for s in payload["segments"]
                )
            )

            try:
                from observability.render_trace import trace_render
                trace_render(req.version, "STARTED")
            except Exception:
                pass

            execute_render(req)
            file.unlink()

            try:
                from observability.render_trace import trace_render
                from observability.trace_buffer import flush_all
                trace_render(req.version, "COMPLETED")
                flush_all()
            except Exception:
                pass

        except Exception:
            try:
                from observability.render_trace import trace_render
                trace_render(payload.get("version", -1), "FAILED")
            except Exception:
                pass
            continue
