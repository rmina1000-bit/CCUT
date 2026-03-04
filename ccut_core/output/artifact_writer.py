import json
import hashlib
from pathlib import Path
from .output_builder import build_minimal_output


ARTIFACT_DIR = Path("storage/artifacts")


def build_output_artifact() -> Path:
    """
    EngineOutput → JSON Artifact 파일 생성
    Deterministic 해야 한다.
    """
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    output = build_minimal_output()

    payload = {
        "version": output.version,
        "segments": [
            {
                "id": seg.segment_id,
                "start": seg.start,
                "end": seg.end,
                "label": seg.label,
            }
            for seg in output.segments
        ],
    }

    json_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":")
    ).encode("utf-8")

    file_hash = hashlib.sha256(json_bytes).hexdigest()

    artifact_path = ARTIFACT_DIR / f"output_v{output.version}.json"

    artifact_path.write_bytes(json_bytes)

    return artifact_path
