"""
[PREVIEW_RENDER_ENGINE] proposal_preview_engine.py
목적: Proposal key_fragments → 하나의 preview mp4 렌더
구조:
  1. clips → 각 clip을 -ss/-to로 임시 re-encode (720p/30fps/veryfast)
  2. concat demuxer로 하나의 preview mp4 합성
  3. -movflags +faststart
  4. 이미 존재하면 재사용 (idempotent)
"""

import os
import uuid
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


BACKEND_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = Path(os.getenv("CCUT_STORAGE_DIR", str(BACKEND_DIR / ".." / "storage")))
PREVIEW_DIR = STORAGE_DIR / "proposal_previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

APP_BASE_URL = os.getenv("CCUT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _preview_filename(proposal_id: str, variant: str) -> str:
    """PREV_{proposal_id}_{variant}.mp4 — 특수문자 제거"""
    safe_id = proposal_id.replace("/", "_").replace("\\", "_").replace(":", "_")
    return f"PREV_{safe_id}_{variant}.mp4"


def ensure_proposal_preview(
    proposal_id: str,
    variant: str,        # "A" or "B"
    clips: list,         # [{"source_path": str, "start": float, "end": float}, ...]
) -> dict:
    """
    Proposal의 clip list를 하나의 preview mp4로 렌더한다.
    이미 존재하면 재사용 (idempotent).

    Args:
        proposal_id: proposal 고유 ID
        variant:     "A" or "B"
        clips:       [{"source_path": str, "start": float, "end": float}, ...]

    Returns:
        {
            "proposal_id": str,
            "variant": str,
            "preview_path": str,
            "preview_url": str,   # /static/proposal_previews/PREV_xxx_A.mp4
            "clip_count": int,
            "duration": float,
            "status": "READY" | "FAILED"
        }
    """
    filename = _preview_filename(proposal_id, variant)
    output_path = PREVIEW_DIR / filename
    preview_url = f"/static/proposal_previews/{filename}"

    # ── 이미 존재하면 재사용 ─────────────────────────────────────
    if output_path.exists() and output_path.stat().st_size > 10240:
        duration = _probe_duration(str(output_path))
        print(f"[PREVIEW_RENDER] CACHE HIT {filename} ({duration:.1f}s)")
        return {
            "proposal_id": proposal_id,
            "variant": variant,
            "preview_path": str(output_path),
            "preview_url": preview_url,
            "clip_count": len(clips),
            "duration": duration,
            "status": "READY"
        }

    # ── clips 검증 ───────────────────────────────────────────────
    valid_clips = []
    for c in clips:
        src = c.get("source_path") or c.get("file_path") or ""
        start = float(c.get("start") or c.get("start_sec") or 0)
        end   = float(c.get("end")   or c.get("end_sec")   or 0)
        if not src or not os.path.exists(src):
            print(f"[PREVIEW_RENDER] WARN: source_path 없음 → {src}")
            continue
        if end <= start:
            print(f"[PREVIEW_RENDER] WARN: end({end}) <= start({start}) → skip")
            continue
        valid_clips.append({"source_path": src, "start": start, "end": end})

    if not valid_clips:
        return _fail(proposal_id, variant, preview_url, "NO_VALID_CLIPS")

    # ── 임시 디렉터리에서 작업 ─────────────────────────────────────
    with tempfile.TemporaryDirectory(prefix="ccut_prev_") as tmpdir:
        temp_clips = []

        # STEP A: 각 clip 개별 re-encode
        for i, clip in enumerate(valid_clips):
            temp_out = os.path.join(tmpdir, f"clip_{i:04d}.mp4")
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(clip["start"]),
                "-to", str(clip["end"]),
                "-i",  clip["source_path"],
                "-vf", "scale=-2:720,fps=30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                "-c:a", "aac", "-b:a", "96k",
                "-movflags", "+faststart",
                temp_out
            ]
            print(f"[PREVIEW_RENDER] Clip {i+1}/{len(valid_clips)}: {clip['source_path']} [{clip['start']:.1f}~{clip['end']:.1f}s]")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0 or not os.path.exists(temp_out):
                print(f"[PREVIEW_RENDER] CLIP FAILED: {result.stderr[:300]}")
                continue
            temp_clips.append(temp_out)

        if not temp_clips:
            return _fail(proposal_id, variant, preview_url, "ALL_CLIPS_FAILED")

        # STEP B: concat demuxer로 합성
        concat_txt = os.path.join(tmpdir, "concat.txt")
        with open(concat_txt, "w", encoding="utf-8") as f:
            for tc in temp_clips:
                f.write(f"file '{tc.replace(chr(92), '/')}'\n")

        concat_out = os.path.join(tmpdir, "preview_raw.mp4")
        cmd_concat = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", concat_txt,
            "-c", "copy",
            "-movflags", "+faststart",
            concat_out
        ]
        print(f"[PREVIEW_RENDER] Concat {len(temp_clips)} clips → {filename}")
        res_concat = subprocess.run(cmd_concat, capture_output=True, text=True, timeout=300)

        if res_concat.returncode != 0 or not os.path.exists(concat_out):
            print(f"[PREVIEW_RENDER] CONCAT FAILED: {res_concat.stderr[:300]}")
            return _fail(proposal_id, variant, preview_url, "CONCAT_FAILED")

        # STEP C: 최종 파일로 이동
        import shutil
        shutil.move(concat_out, str(output_path))

    duration = _probe_duration(str(output_path))
    size_mb  = round(output_path.stat().st_size / 1024 / 1024, 1)
    print(f"[PREVIEW_RENDER] OK {filename} duration={duration:.1f}s size={size_mb}MB")

    return {
        "proposal_id": proposal_id,
        "variant": variant,
        "preview_path": str(output_path),
        "preview_url": preview_url,
        "clip_count": len(temp_clips),
        "duration": duration,
        "status": "READY"
    }


def _probe_duration(path: str) -> float:
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10
        )
        return float(res.stdout.strip()) if res.stdout.strip() else 0.0
    except Exception:
        return 0.0


def _fail(proposal_id: str, variant: str, preview_url: str, reason: str) -> dict:
    print(f"[PREVIEW_RENDER] FAILED proposal_id={proposal_id} variant={variant} reason={reason}")
    return {
        "proposal_id": proposal_id,
        "variant": variant,
        "preview_path": None,
        "preview_url": None,
        "clip_count": 0,
        "duration": 0.0,
        "status": "FAILED",
        "reason": reason
    }
