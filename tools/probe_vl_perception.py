"""[CCUT-CORE-PIPELINE-R1] Qwen3-VL Visual Worker Standalone Probe.

ccut_backend/storage/thumbnails/ 에서 .jpg 1개를 골라
QwenVLVisualWorker.analyze_image()를 직접 호출한 결과를
artifacts/vl_perception_probe/result.json 에 저장한다.

main.py / DB / ProposalEngine 은 건드리지 않는다.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "ccut_backend"

sys.path.insert(0, str(BACKEND_DIR))

from ai.vision.qwen_vl_visual_worker import QwenVLVisualWorker  # noqa: E402


THUMBNAIL_DIRS = [
    BACKEND_DIR / "storage" / "thumbnails",
    REPO_ROOT / "storage" / "thumbnails",
    BACKEND_DIR / "storage" / "panorama",
    REPO_ROOT / "storage" / "panorama",
]


def find_thumbnail() -> Optional[Path]:
    for d in THUMBNAIL_DIRS:
        if not d.exists() or not d.is_dir():
            continue
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            files = sorted(d.glob(ext))
            if files:
                return files[0]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Qwen3-VL Standalone Probe")
    parser.add_argument("--max-images", type=int, default=1)
    parser.add_argument("--resize-max", type=int, default=384)
    parser.add_argument("--timeout-sec", type=int, default=120)
    args = parser.parse_args()

    out_dir = REPO_ROOT / "artifacts" / "vl_perception_probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "result.json"

    img_path = find_thumbnail()
    if img_path is None:
        result = {
            "image": "",
            "status": "FAIL",
            "scene_type": "",
            "focus": "",
            "summary": "no_thumbnail_found",
            "latency_ms": 0,
        }
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[VL_PROBE] No thumbnail found. Wrote {out_path}")
        return 0

    print(
        f"[VL_PROBE] image={img_path.name} "
        f"resize_max={args.resize_max} timeout={args.timeout_sec}"
    )

    worker = QwenVLVisualWorker()
    raw = worker.analyze_image(
        str(img_path),
        resize_max=args.resize_max,
        timeout_sec=args.timeout_sec,
    )

    raw_status = raw.get("status", "UNKNOWN")
    is_ok = raw_status in ("OK", "OK_TRACE_VISUAL")
    evidence = raw.get("evidence") or {}

    summary = (
        evidence.get("visual_summary")
        or raw.get("error")
        or raw_status
    )

    result = {
        "image": img_path.name,
        "status": "OK" if is_ok else "FAIL",
        "scene_type": evidence.get("scene_type", ""),
        "focus": evidence.get("face_visibility", ""),
        "summary": summary,
        "latency_ms": raw.get("latency_ms", 0),
    }

    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[VL_PROBE] status={result['status']} "
        f"latency={result['latency_ms']}ms"
    )
    print(f"[VL_PROBE] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
