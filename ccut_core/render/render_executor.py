import json
import hashlib
from pathlib import Path
from .render_models import RenderRequest


RENDER_DIR = Path("storage/renders")


def execute_render(request: RenderRequest) -> Path:
    """
    RenderRequest를 받아 실제 실행 결과 파일 생성.
    Fail-Silent: 예외 발생 시 None 반환.
    """

    try:
        RENDER_DIR.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": request.version,
            "artifact_hash": request.artifact_hash,
            "segments": [
                {
                    "id": s.segment_id,
                    "start": s.start,
                    "end": s.end,
                }
                for s in request.segments
            ],
        }

        json_bytes = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":")
        ).encode("utf-8")

        render_hash = hashlib.sha256(json_bytes).hexdigest()

        output_path = RENDER_DIR / f"render_v{request.version}.json"
        output_path.write_bytes(json_bytes)

        return output_path

    except Exception:
        return None
