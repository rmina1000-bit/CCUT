import os
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Any, List
from archive.manager import bams

AUDIO_SPLICE_FADE_SEC = 0.008


def _concat_filter_with_audio_splice_fade(durations: List[float]) -> str:
    count = len(durations)
    video_inputs = "".join(f"[{i}:v:0]" for i in range(count))
    parts = [f"{video_inputs}concat=n={count}:v=1:a=0[v]"]
    audio_inputs = []
    for i, duration in enumerate(durations):
        fade_dur = min(AUDIO_SPLICE_FADE_SEC, max(0.0, duration) / 2.0)
        fade_out_start = max(0.0, duration - fade_dur)
        parts.append(
            f"[{i}:a:0]afade=t=in:st=0:d={fade_dur:.6f},"
            f"afade=t=out:st={fade_out_start:.6f}:d={fade_dur:.6f}[aud{i}]"
        )
        audio_inputs.append(f"[aud{i}]")
    parts.append(f"{''.join(audio_inputs)}concat=n={count}:v=0:a=1[a]")
    return ";".join(parts)

class RenderEngine:
    def __init__(self, bams):
        self.bams = bams
        self.backend_dir = Path(__file__).resolve().parents[1]
        self.export_dir = self.backend_dir / "storage" / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def render_from_export_input(self, export_input_id: str) -> Dict[str, Any]:
        """
        [STEP 8] Render Engine (v3.2.1)
        ExportInput 기준으로만 렌더링을 실행합니다.
        """
        from database import SessionLocal
        from archive.db_models import ExportInputTable
        
        # 1. ExportInput 로드
        with SessionLocal() as db:
            row = db.query(ExportInputTable).filter_by(export_id=export_input_id).first()
            if not row:
                return self._fail("EXPORT_INPUT_NOT_FOUND", "ExportInput 없음")
            
            export_input = {
                "export_id": row.export_id,
                "source_id": row.source_id,
                "proposal_id": row.proposal_id,
                "clips": row.clips,
                "total_duration": row.total_duration,
                "status": row.status
            }

        if export_input.get("status") != "EXPORT_INPUT_READY":
            return self._fail(
                "EXPORT_INPUT_NOT_READY",
                f"ExportInput status 불일치: {export_input.get('status')}"
            )

        clips = export_input.get("clips") or []
        if not clips:
            return self._fail("CLIPS_EMPTY", "clips 없음")

        # 2. Clips 검증
        validation = self._validate_clips(clips, export_input)
        if not validation["ok"]:
            return self._fail("CLIPS_INVALID", validation["reason"])

        # 3. Source 경로 조회 (하드코딩 금지)
        source_map = self._resolve_source_paths(clips, export_input)
        if not source_map["ok"]:
            return self._fail("SOURCE_NOT_FOUND", source_map["reason"])

        # 4. 출력 경로 설정
        output_filename = f"EXP_{uuid.uuid4().hex[:8].upper()}.mp4"
        output_path = self.export_dir / output_filename

        # 5. FFmpeg 실행
        result = self._render_with_ffmpeg(
            clips=clips,
            source_paths=source_map["paths"],
            output_path=str(output_path)
        )

        # 6. Render Result 저장
        render_data = {
            "id": f"RND_{uuid.uuid4().hex[:8].upper()}",
            "export_input_id": export_input_id,
            "proposal_id": export_input["proposal_id"],
            "source_id": export_input["source_id"],
            "output_path_internal": str(output_path),
            "output_url": f"/static/exports/{output_filename}",
            "status": "RENDER_SUCCESS" if result["success"] else "RENDER_FAILED",
            "file_size": os.path.getsize(output_path) if result["success"] and os.path.exists(output_path) else 0,
            "duration": result.get("duration", 0.0),
            "ffmpeg_command_summary": result.get("command"),
            "ffmpeg_stderr": result.get("stderr")
        }
        
        self.bams.save_render_result(render_data)
        
        return {
            "success": result["success"],
            "status": render_data["status"],
            "export_input_id": export_input_id,
            "output_url": render_data["output_url"],
            "file_size": render_data["file_size"],
            "duration": render_data["duration"],
            "message": result.get("error_msg")
        }

    def _validate_clips(self, clips: List[Dict[str, Any]], export_input: Dict[str, Any]) -> Dict[str, Any]:
        total = 0.0
        for i, clip in enumerate(clips):
            start = float(clip.get("start", -1))
            end = float(clip.get("end", -1))
            duration = float(clip.get("duration", end - start))

            if start < 0:
                return {"ok": False, "reason": f"clip[{i}] start < 0"}
            if end <= start:
                return {"ok": False, "reason": f"clip[{i}] end <= start"}
            if abs(duration - (end - start)) > 0.05:
                return {"ok": False, "reason": f"clip[{i}] duration mismatch"}
            total += duration

        expected_total = float(export_input.get("total_duration", total))
        if abs(total - expected_total) > 0.1:
            return {"ok": False, "reason": f"total_duration mismatch: sum={total}, expected={expected_total}"}
        
        return {"ok": True, "reason": None}

    def _resolve_source_paths(self, clips: List[Dict[str, Any]], export_input: Dict[str, Any]) -> Dict[str, Any]:
        paths = {}
        unique_source_ids = set()
        for clip in clips:
            s_id = clip.get("source_id")
            if s_id:
                unique_source_ids.add(s_id)
                
        top_sid = export_input.get("source_id")
        if top_sid:
            unique_source_ids.add(top_sid)
            
        for sid in unique_source_ids:
            if sid.startswith("proj_calib_"):
                continue
            source = self.bams.get_source(sid)
            if not source:
                if sid == top_sid and len(paths) > 0:
                    continue
                return {"ok": False, "reason": f"Source {sid} not found in DB"}
            
            path = source.file_path
            if not os.path.exists(path):
                # [R3-FIX] DB file_path가 원본 경로(Downloads 등) → storage/uploads/에서 동명 파일 탐색
                uploads_dir = self.backend_dir.parent / "storage" / "uploads"
                alt = uploads_dir / os.path.basename(path)
                if alt.exists():
                    path = str(alt)
                else:
                    return {"ok": False, "reason": f"Source file not found at {path}"}
            paths[sid] = path
            
        if not paths:
            return {"ok": False, "reason": "No valid source paths resolved"}
            
        return {"ok": True, "paths": paths}

    def _render_with_ffmpeg(self, clips: List[Dict[str, Any]], source_paths: Dict[str, str], output_path: str) -> Dict[str, Any]:
        """[STREAM-FIX] concat inpoint/outpoint는 timestamp를 손상시켜 실제 fps가
        1~2fps로 떨어진다(프레임당 1초 재생). 각 클립을 -ss/-to로 정밀 추출하면서
        30fps CFR · 1920x1080 · 48kHz로 정규화한 뒤 concat copy로 합친다.
        """
        import shutil
        out_p = Path(output_path)
        clip_dir = out_p.parent / f"_tmp_{out_p.stem}"
        clip_dir.mkdir(parents=True, exist_ok=True)
        temp_list = out_p.with_suffix(".txt")
        temp_clips: List[Path] = []
        temp_durations: List[float] = []
        try:
            sorted_clips = sorted(clips, key=lambda x: x.get("order", 0))

            # 1. 각 클립 정밀 추출 + 정규화 (가변 fps/해상도/오디오 통일)
            for i, clip in enumerate(sorted_clips):
                src_id = clip.get("source_id") or list(source_paths.keys())[0]
                src_path = source_paths.get(src_id)
                if not src_path:
                    continue
                clip_duration = max(0.0, float(clip["end"]) - float(clip["start"]))
                tmp = clip_dir / f"clip_{i:04d}.mp4"
                cut_cmd = [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-ss", str(clip["start"]), "-to", str(clip["end"]),
                    "-i", src_path,
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                           "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1",
                    "-r", "30", "-fps_mode", "cfr",
                    # [STREAM-FIX] 1초마다 강제 keyframe — keyframe이 드물면 브라우저가
                    # 조각 경계 이후 디코드를 못 해 멈춘다(seek 불가).
                    "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                    str(tmp),
                ]
                r = subprocess.run(cut_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
                    temp_clips.append(tmp)
                    temp_durations.append(clip_duration)
                else:
                    print(f"[RENDER] clip {i} 추출 실패: {r.stderr[:200]}")

            if not temp_clips:
                return {"success": False, "error_msg": "모든 클립 추출 실패",
                        "command": "", "stderr": ""}

            # 2. concat 재인코딩 (단일 SPS/PPS·단일 stream).
            # [-c copy 금지] 각 클립이 따로 인코딩돼 SPS/PPS가 경계마다 바뀌면
            # Chrome 디코더가 조각 경계에서 멈춘다. 재인코딩으로 단일 stream 보장.
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
            ]
            for t in temp_clips:
                cmd.extend(["-i", str(t)])
            cmd.extend([
                "-filter_complex", _concat_filter_with_audio_splice_fade(temp_durations),
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", output_path,
            ])
            process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

            if process.returncode != 0:
                print(f"[RENDER] FFmpeg Failed: {process.stderr}")
                return {"success": False, "stderr": process.stderr,
                        "command": " ".join(cmd), "error_msg": "FFmpeg execution failed"}

            probe_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", output_path,
            ]
            probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            duration = float(probe_res.stdout.strip()) if probe_res.stdout.strip() else 0.0

            return {"success": True, "duration": duration,
                    "command": " ".join(cmd), "stderr": process.stderr}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error_msg": str(e)}
        finally:
            if temp_list.exists():
                temp_list.unlink()
            if clip_dir.exists():
                shutil.rmtree(clip_dir, ignore_errors=True)

    def _fail(self, code: str, msg: str) -> Dict[str, Any]:
        return {"success": False, "status": "RENDER_FAILED", "error_code": code, "message": msg}

render_engine = RenderEngine(bams=bams)
