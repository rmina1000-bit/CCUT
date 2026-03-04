import hashlib
import json
from pathlib import Path
from .render_models import RenderRequest, RenderSegment


def build_render_request() -> RenderRequest:
    """
    Artifact 기반 RenderRequest 생성.
    실제 렌더는 수행하지 않는다.
    """
    from output.artifact_writer import build_output_artifact

    artifact_path: Path = build_output_artifact()
    artifact_bytes = artifact_path.read_bytes()

    artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()

    payload = json.loads(artifact_bytes.decode("utf-8"))

    segments = tuple(
        RenderSegment(
            segment_id=s["id"],
            start=s["start"],
            end=s["end"]
        )
        for s in payload["segments"]
    )

    return RenderRequest(
        version=payload["version"],
        segments=segments,
        artifact_hash=artifact_hash
    )
