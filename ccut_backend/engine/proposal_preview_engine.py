"""
[PREVIEW_RENDER_ENGINE] proposal_preview_engine.py
목적: Proposal key_fragments → 하나의 preview mp4 렌더
구조:
  1. clips → 각 clip을 -ss/-to로 임시 re-encode
     ([RENDER-1 2026-08-09] 규격은 소스 상속 — 장변만 1280 캡, fps·오디오 rate 상속.
      옛 문장 "720p/30fps" 는 1280x720 상수 시절 것이라 지웠다.
      계산은 render_engine.choose_target_spec / preview_target_spec 한 곳)
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
AUDIO_SPLICE_FADE_SEC = 0.008


def _concat_filter_with_audio_splice_fade(durations: list[float]) -> str:
    count = len(durations)
    # [LAB-53 D] 미리보기와 내보내기의 페이드 길이는 하나다.
    #   구판은 여기에 8ms를 박아 두어, 게이트 ON(.env CCUT_TECHNIQUE_AUDIO_FADE=ON)일 때
    #   내보내기만 30ms가 되고 미리보기는 8ms로 남았다 — 들은 소리와 나온 소리가 달랐다.
    #   길이의 진실원은 render_engine._audio_fade_spec 하나(게이트 OFF면 8ms 그대로).
    from engine.render_engine import _audio_fade_spec
    fade_in_sec, fade_out_sec, gated = _audio_fade_spec()
    print(
        f"[PREVIEW][AUDIO_FADE] gate={'ON' if gated else 'OFF'} "
        f"fade_in={fade_in_sec * 1000:.1f}ms fade_out={fade_out_sec * 1000:.1f}ms "
        f"clips={count}"
    )
    video_inputs = "".join(f"[{i}:v:0]" for i in range(count))
    parts = [f"{video_inputs}concat=n={count}:v=1:a=0[v]"]
    audio_inputs = []
    for i, duration in enumerate(durations):
        half = max(0.0, duration) / 2.0
        fade_in = min(fade_in_sec, half)
        fade_out = min(fade_out_sec, half)
        fade_out_start = max(0.0, duration - fade_out)
        parts.append(
            f"[{i}:a:0]afade=t=in:st=0:d={fade_in:.6f},"
            f"afade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f}[aud{i}]"
        )
        audio_inputs.append(f"[aud{i}]")
    parts.append(f"{''.join(audio_inputs)}concat=n={count}:v=0:a=1[a]")
    return ";".join(parts)


def _preview_filename(proposal_id: str, variant: str) -> str:
    """PREV_{proposal_id}_{variant}_{technique}.mp4 — 특수문자 제거

    [PUNCH-1 P4] 기법을 파일명에 넣는다. 넣지 않으면 기법이 바뀌어도 CACHE HIT가 나서
    화면에는 옛 기법의 미리보기가 계속 뜬다(조용한 거짓말).
    """
    safe_id = proposal_id.replace("/", "_").replace("\\", "_").replace(":", "_")
    try:
        from story_gate.proposal_axis import technique_for_mode
        tech = technique_for_mode(variant)
    except Exception:
        tech = "as_is"
    return f"PREV_{safe_id}_{variant}_{tech}.mp4"


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
        valid_clips.append({"source_path": src, "start": start, "end": end,
                            "fragment_id": c.get("fragment_id")})

    if not valid_clips:
        return _fail(proposal_id, variant, preview_url, "NO_VALID_CLIPS")

    # [RENDER-1] 미리보기 규격도 소스에서 상속한다 — 계산은 render_engine 한 곳.
    #   preview clip 은 source_id 대신 source_path 를 들고 다니므로 경로 자체를
    #   키로 넘긴다(choose_target_spec 은 {키: 경로} 이면 된다).
    from engine.render_engine import choose_target_spec as _cts
    _prev_target = _cts(
        [{"source_id": c["source_path"], "start": c["start"], "end": c["end"]}
         for c in valid_clips],
        {c["source_path"]: c["source_path"] for c in valid_clips})
    from engine.render_engine import preview_target_spec as _pts
    _pv = _pts(_prev_target)
    _pv_gop = max(1, int(round(float(_pv["fps_val"]))))
    print(f"[PREVIEW_RENDER][SPEC] {_pv['w']}x{_pv['h']}@{_pv['fps']} "
          f"(소스 {_prev_target['w']}x{_prev_target['h']})")

    # ── 임시 디렉터리에서 작업 ─────────────────────────────────────
    with tempfile.TemporaryDirectory(prefix="ccut_prev_") as tmpdir:
        temp_clips = []
        temp_durations = []

        # STEP A: 각 clip 개별 re-encode
        def _encode_clip(idx, clip):
            temp_out = os.path.join(tmpdir, f"clip_{idx:04d}.mp4")
            # [PUNCH-1 P4] 기법 필터. 렌더 경로(render_engine)와 **같은 함수**를 부른다 —
            #   기법 구현이 두 벌로 갈리면 미리보기와 내보내기가 달라진다(INV-3).
            # [RENDER-1 2026-08-09] 1280x720 상수 폐기 — 소스 종횡비를 상속하고
            #   장변만 1280 으로 캡한다(세로면 720x1280). 구판은 미리보기와
            #   결과물의 기하가 서로 달라 A/B 로 본 그림과 뽑은 mp4 가 달랐다.
            #   규격 계산은 render_engine 한 곳에서만 한다(두 벌로 갈리면 INV-3).
            from engine.render_engine import build_scale_pad_vf
            _vf = build_scale_pad_vf(_pv, None) + f",fps={_pv['fps']}"
            try:
                from story_gate.proposal_axis import punch_filter, technique_for_mode
                # [LAB-43] program_id 동반 — 없으면 경계 veto 가 영원히 UNKNOWN.
                from story_gate.proposal_axis import program_id_for_proposal as _pid
                _pf = punch_filter(technique_for_mode(variant), clip.get("fragment_id"),
                                   float(clip["start"]), float(clip["end"]),
                                   int(_pv["w"]), int(_pv["h"]),
                                   program_id=_pid(proposal_id))
                if _pf:
                    _vf += "," + _pf
                    print(f"[PREVIEW_RENDER][PUNCH] clip {idx} {clip.get('fragment_id')} -> {_pf[:70]}...")
            except Exception as _pe:
                print(f"[PREVIEW_RENDER][PUNCH] 필터 생략 (비차단): {_pe}")
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(clip["start"]),
                "-to", str(clip["end"]),
                "-i",  clip["source_path"],
                "-vf", _vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                # [RENDER-1 되돌아옴 2026-08-09 · 실측으로 잡은 갈림] 오디오 규격도
                #   내보내기와 같은 target 에서 상속한다. 구판 미리보기는 -ar/-ac 가
                #   아예 없어서 클립마다 소스 rate 를 그대로 물고 갔고, concat 필터가
                #   자동 협상으로 하나를 골랐다. 실측(3규격·44100/48000/44100 혼재):
                #     내보내기 48000  vs  미리보기 44100  — 들은 소리와 나온 소리가 달랐다.
                #   단일 규격 프로젝트에서는 상속값 == 소스값이라 항등(동작 무변).
                "-c:a", "aac", "-b:a", "96k",
                "-ar", str(int(_pv["sample_rate"])), "-ac", str(int(_pv["channels"])),
                "-movflags", "+faststart",
                temp_out
            ]
            print(f"[PREVIEW_RENDER] Clip {idx+1}/{len(valid_clips)}: {clip['source_path']} [{clip['start']:.1f}~{clip['end']:.1f}s]")
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            if result.returncode != 0 or not os.path.exists(temp_out):
                print(f"[PREVIEW_RENDER] CLIP FAILED: {result.stderr[:300]}")
                return None
            return temp_out

        _parallel = os.getenv("CCUT_PREVIEW_PARALLEL", "0").strip() not in ("", "0", "false", "False")
        if _parallel:
            # [P5-1] 클립 인코딩 병렬 (인덱스별 결과 후 순서 복원 — concat 순서 보존)
            import concurrent.futures
            _max_workers = int(os.getenv("CCUT_PREVIEW_WORKERS", "4") or "4")
            _ordered = [None] * len(valid_clips)
            with concurrent.futures.ThreadPoolExecutor(max_workers=_max_workers) as _ex:
                _futs = {_ex.submit(_encode_clip, i, c): i for i, c in enumerate(valid_clips)}
                for _f in concurrent.futures.as_completed(_futs):
                    _ordered[_futs[_f]] = _f.result()
            temp_clips = [r for r in _ordered if r]
            temp_durations = [
                c["end"] - c["start"]
                for i, c in enumerate(valid_clips)
                if i < len(_ordered) and _ordered[i]
            ]
        else:
            # 기존 직렬 경로 (동작 무변)
            for i, clip in enumerate(valid_clips):
                r = _encode_clip(i, clip)
                if r:
                    temp_clips.append(r)
                    temp_durations.append(clip["end"] - clip["start"])

        if not temp_clips:
            return _fail(proposal_id, variant, preview_url, "ALL_CLIPS_FAILED")

        # STEP B: re-encode concat 으로 단일 균질 mp4 생성
        # [-c copy 금지] source 간 fps/codec 차이로 Chrome boundary decode 멈춤 방지
        concat_out = os.path.join(tmpdir, "preview_raw.mp4")
        cmd_concat = [
            "ffmpeg", "-y", "-loglevel", "error",
        ]
        for tc in temp_clips:
            cmd_concat.extend(["-i", tc])
        cmd_concat.extend([
            "-filter_complex", _concat_filter_with_audio_splice_fade(temp_durations),
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            # [STREAM-FIX] 1초마다 keyframe — 긴 제안에서 조각 경계 멈춤 방지
            # [RENDER-1] 30 상수 → 미리보기 target fps(=소스 상속).
            "-g", str(_pv_gop), "-keyint_min", str(_pv_gop), "-sc_threshold", "0",
            "-pix_fmt", "yuv420p",
            # [RENDER-1 되돌아옴] 내보내기 concat 단과 같은 자리에 같은 값을 명시한다.
            "-c:a", "aac", "-b:a", "128k",
            "-ar", str(int(_pv["sample_rate"])), "-ac", str(int(_pv["channels"])),
            "-movflags", "+faststart",
            concat_out
        ])
        print(f"[PREVIEW_RENDER] Re-encode concat {len(temp_clips)} clips → {filename}")
        res_concat = subprocess.run(cmd_concat, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)

        if res_concat.returncode != 0 or not os.path.exists(concat_out):
            print(f"[PREVIEW_RENDER] CONCAT FAILED: {res_concat.stderr[:300]}")
            return _fail(proposal_id, variant, preview_url, "CONCAT_FAILED")

        # STEP C: 최종 파일로 이동
        import shutil
        shutil.move(concat_out, str(output_path))

    # STEP D: decode smoke test — 브라우저 decode 실패 사전 차단
    smoke = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output_path), "-f", "null", "NUL"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
    )
    if smoke.returncode != 0 or smoke.stderr.strip():
        err_snippet = smoke.stderr.strip()[:300]
        print(f"[PREVIEW_RENDER] SMOKE FAIL {filename}: {err_snippet}")
        output_path.unlink(missing_ok=True)
        return _fail(proposal_id, variant, preview_url, f"SMOKE_FAILED: {err_snippet}")

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
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
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
