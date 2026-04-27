import os
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Any, List
from archive.manager import bams

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
        source_id = export_input["source_id"]
        source = self.bams.get_source(source_id)
        if not source:
            return {"ok": False, "reason": f"Source {source_id} not found in DB"}
        
        path = source.file_path
        if not os.path.exists(path):
            return {"ok": False, "reason": f"Source file not found at {path}"}
        
        return {"ok": True, "paths": {source_id: path}}

    def _render_with_ffmpeg(self, clips: List[Dict[str, Any]], source_paths: Dict[str, str], output_path: str) -> Dict[str, Any]:
        # Concat Demuxer 방식
        temp_list = Path(output_path).with_suffix(".txt")
        try:
            with open(temp_list, "w", encoding="utf-8") as f:
                # order 기준 정렬
                sorted_clips = sorted(clips, key=lambda x: x.get("order", 0))
                for clip in sorted_clips:
                    src_id = clip.get("source_id") or list(source_paths.keys())[0]
                    src_path = source_paths.get(src_id)
                    f.write(f"file '{src_path.replace('\\', '/')}'\n")
                    f.write(f"inpoint {clip['start']}\n")
                    f.write(f"outpoint {clip['end']}\n")
            
            # FFmpeg 실행 (Encoding for reliability)
            cmd = [
                "ffmpeg", "-y", 
                "-f", "concat", "-safe", "0", "-i", str(temp_list),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                output_path
            ]
            
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            if process.returncode != 0:
                print(f"[RENDER] FFmpeg Failed: {process.stderr}")
                return {
                    "success": False,
                    "stderr": process.stderr,
                    "command": " ".join(cmd),
                    "error_msg": "FFmpeg execution failed"
                }
            
            # ffprobe 검증
            probe_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", output_path
            ]
            probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
            duration = float(probe_res.stdout.strip()) if probe_res.stdout.strip() else 0.0
            
            return {
                "success": True,
                "duration": duration,
                "command": " ".join(cmd),
                "stderr": process.stderr
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error_msg": str(e)}
        finally:
            if temp_list.exists():
                temp_list.unlink()

    def _fail(self, code: str, msg: str) -> Dict[str, Any]:
        return {"success": False, "status": "RENDER_FAILED", "error_code": code, "message": msg}

render_engine = RenderEngine(bams=bams)
