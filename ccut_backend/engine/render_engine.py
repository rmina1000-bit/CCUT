import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Any, List
from archive.manager import bams

AUDIO_SPLICE_FADE_SEC = 0.008
TECHNIQUES_CONFIG = Path(__file__).resolve().parents[1] / "config" / "editing_techniques.json"


def _flag_on(name: str) -> bool:
    return os.getenv(name, "").strip().upper() in ("1", "ON", "TRUE", "YES")


def _audio_fade_spec():
    """[LAB-18] 컷 연결부 오디오 페이드 길이(초). → (fade_in, fade_out, 게이트ON)

    게이트 OFF면 기존 splice 클릭 억제용 8ms 그대로다 — 현행 무변.
    ON이면 config/editing_techniques.json 의 audio_fade_30ms.engine_effect 를 쓴다.
    길이를 코드 상수로 박지 않는다 — 규칙 값은 config 하나에 둔다.
    """
    if not _flag_on("CCUT_TECHNIQUE_AUDIO_FADE"):
        return AUDIO_SPLICE_FADE_SEC, AUDIO_SPLICE_FADE_SEC, False
    try:
        with open(TECHNIQUES_CONFIG, "r", encoding="utf-8") as handle:
            techniques = json.load(handle)["techniques"]
        effect = next(
            item for item in techniques
            if item["technique_id"] == "audio_fade_30ms"
        )["engine_effect"]
        return (
            float(effect["fade_in_ms"]) / 1000.0,
            float(effect["fade_out_ms"]) / 1000.0,
            True,
        )
    except Exception as exc:
        print(f"[RENDER][AUDIO_FADE] config 읽기 실패 — 기본값 유지: {exc}")
        return AUDIO_SPLICE_FADE_SEC, AUDIO_SPLICE_FADE_SEC, False


def _concat_filter_with_audio_splice_fade(durations: List[float]) -> str:
    count = len(durations)
    fade_in_sec, fade_out_sec, gated = _audio_fade_spec()
    print(
        f"[RENDER][AUDIO_FADE] gate={'ON' if gated else 'OFF'} "
        f"fade_in={fade_in_sec * 1000:.1f}ms fade_out={fade_out_sec * 1000:.1f}ms "
        f"clips={count}"
    )
    # [LAB-22] 영상과 소리를 **하나의 concat**으로 잇는다.
    #   구판은 영상만 잇는 concat 과 소리만 잇는 concat 을 따로 돌렸다. 그러면 두 스트림이
    #   서로를 모른 채 각자 길이를 쌓아, 클립마다 생기는 미세한 차이가 그대로 누적된다.
    #   차이의 뿌리는 1단계 추출이다 — `-r 30 -fps_mode cfr` 이 영상 길이를 33.3ms 격자로
    #   올리는데 소리는 요청한 길이를 그대로 지킨다.
    #   실측(Merope 20클립): 추출 직후 누적차 650.7ms → 최종본 2780.0ms.
    #   국장 청감: 6번 클립부터 소리가 앞서 들림.
    #   concat 에 v=1:a=1 로 함께 넣으면 세그먼트마다 두 스트림의 시작을 맞추므로
    #   차이가 그 클립 안에서 끝나고 뒤로 넘어가지 않는다.
    parts = []
    segments = []
    for i, duration in enumerate(durations):
        half = max(0.0, duration) / 2.0
        fade_in = min(fade_in_sec, half)
        fade_out = min(fade_out_sec, half)
        fade_out_start = max(0.0, duration - fade_out)
        parts.append(
            f"[{i}:a:0]afade=t=in:st=0:d={fade_in:.6f},"
            f"afade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f}[aud{i}]"
        )
        segments.append(f"[{i}:v:0][aud{i}]")
    parts.append(f"{''.join(segments)}concat=n={count}:v=1:a=1[v][a]")
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
                # [LAB-19] mode → technique 는 technique_for_mode 가 결정한다.
                #   A=punch_in / B=word_boundary_snap(게이트 ON) 또는 as_is(OFF).
                "mode": row.mode,
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
        # [PUNCH-1 P4] mode → technique 는 순수 상수 사상. 미리보기도 같은 함수를 쓴다.
        from story_gate.proposal_axis import technique_for_mode
        _tech = technique_for_mode(export_input.get("mode"))
        print(f"[RENDER][PUNCH] mode={export_input.get('mode')} technique={_tech}")
        # [LAB-43] program_id 동반 — 없으면 경계 veto 가 영원히 UNKNOWN(도달 불가).
        from story_gate.proposal_axis import program_id_for_proposal
        result = self._render_with_ffmpeg(
            clips=clips,
            source_paths=source_map["paths"],
            output_path=str(output_path),
            technique=_tech,
            program_id=program_id_for_proposal(export_input.get("proposal_id")),
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

    def _render_with_ffmpeg(self, clips: List[Dict[str, Any]], source_paths: Dict[str, str], output_path: str, technique: str = None, program_id: str = None) -> Dict[str, Any]:
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
                # [PUNCH-1 P4] 미리보기(proposal_preview_engine)와 **같은 함수**를 부른다.
                #   해상도만 다르고(1920x1080 vs 1280x720) 줌 배율·시점은 동일하다.
                _vf = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
                       "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1")
                try:
                    from story_gate.proposal_axis import punch_filter
                    _pf = punch_filter(technique, clip.get("fragment_id"),
                                       float(clip["start"]), float(clip["end"]), 1920, 1080,
                                       program_id=program_id)
                    if _pf:
                        # [LAB-24] zoompan 앞에서 입력 프레임률을 30으로 고정한다.
                        #   zoompan 은 입력 1프레임당 1프레임을 내고 그 출력을 30fps 타임베이스에
                        #   놓는다. 그래서 출력 길이 = 입력 프레임 수 ÷ 30 이 되고,
                        #   원본 fps 가 30이 아니면 영상 길이와 속도가 그 비율로 뒤틀린다.
                        #   실측(Merope A): 59.94fps 원본 3.500s → 6.967s(+99%),
                        #                   14.98fps 원본 1.800s → 0.900s(-50%).
                        #   소리는 어느 쪽도 아니라 영상만 따로 놀았다(국장 청감: 영상이 느려짐).
                        #   입력을 미리 30fps 로 맞추면 zoompan 이 시간축에 대해 항등이 된다.
                        _vf += ",fps=30," + _pf
                        print(f"[RENDER][PUNCH] clip {i} {clip.get('fragment_id')} -> {_pf[:70]}...")
                except Exception as _pe:
                    print(f"[RENDER][PUNCH] 필터 생략 (비차단): {_pe}")
                cut_cmd = [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-ss", str(clip["start"]), "-to", str(clip["end"]),
                    "-i", src_path,
                    "-vf", _vf,
                    "-r", "30", "-fps_mode", "cfr",
                    # [STREAM-FIX] 1초마다 강제 keyframe — keyframe이 드물면 브라우저가
                    # 조각 경계 이후 디코드를 못 해 멈춘다(seek 불가).
                    "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                    # [LAB-23] 출력 길이를 조각 길이로 못 박는다.
                    #   -ss/-to 는 입력을 자를 뿐, 필터가 프레임 수를 바꾸면 출력 길이가 따라간다.
                    #   실측(Merope): punch_in 의 zoompan 이 선언 3.500s 를 6.967s 로(+99%),
                    #   1.800s 를 0.900s 로(-50%) 만들었다. 소리는 요청 길이를 지키므로
                    #   그만큼 영상과 소리가 어긋난다.
                    #   소리를 진실로 두고 영상을 거기에 맞춘다 — 소리는 변형하지 않는다.
                    "-t", f"{clip_duration:.6f}",
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
