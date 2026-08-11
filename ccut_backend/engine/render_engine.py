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


# ── [RENDER-1 2026-08-09] 규격을 소스에서 상속한다 ─────────────────────────
#   구판은 1920x1080 · 30fps · 48kHz 를 상수로 박았다. 그래서 세로 원본
#   (1080x1920)이 좌우 필러박스가 붙은 가로 영상이 되어 세로 유효 화소가
#   원본의 약 32% 로 떨어졌다(실측). 60fps 원본은 30fps 로 절반이 버려졌다.
#
#   왜 "통일" 자체는 남기나: concat 필터(`concat=n=N:v=1:a=1`)는 입력들의
#   w/h/SAR/pix_fmt/sample_rate 가 같기를 요구한다. 그래서 걷어내는 것은
#   "1920x1080 이라는 상수"뿐이고 "규격 통일"은 유지한다 —
#   통일 목표값을 상수에서 **소스에서 계산한 target spec** 으로 바꾼다.
#   단일 소스면 target == 원본이므로 scale/pad 가 항등이 되어 사라진다.
#
#   새 레이어를 만들지 않은 이유: 이 두 함수는 render_engine 안에 두고
#   proposal_preview_engine / scripts/render_probe.py 가 import 한다
#   (_audio_fade_spec 이 이미 그 방식이다). 규격 계산이 세 벌로 갈리면
#   미리보기와 결과물이 다른 프레임을 낸다.

_SPEC_PROBE_CACHE: Dict[str, Dict[str, Any]] = {}


def probe_source_spec(path: str) -> Dict[str, Any]:
    """소스의 **표시 규격**을 ffprobe 로 읽는다.

    ★rotation 은 저장 치수가 아니라 표시 치수로 접는다. ffmpeg 는 필터 앞에서
      autorotate 하므로(정찰 B) Display Matrix −90 인 1920x1080 소스는 필터
      입장에서 이미 1080x1920 이다. 여기서 미리 접어두지 않으면 scale/pad 가
      영원히 어긋난다.
    ★fps 는 DB 값(60.0)이 아니라 ffprobe r_frame_rate(60/1)를 쓴다 —
      DB 는 반올림된 float 라 `-r` 에 넣으면 격자가 틀어진다.
    """
    key = str(path)
    if key in _SPEC_PROBE_CACHE:
        return _SPEC_PROBE_CACHE[key]
    spec = {"w": 1920, "h": 1080, "fps": "30/1", "fps_val": 30.0,
            "sample_rate": 48000, "channels": 2, "rotation": 0, "ok": False}
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", key],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        data = json.loads(out.stdout or "{}")
        for st in data.get("streams", []):
            if st.get("codec_type") == "video" and not spec["ok"]:
                w = int(st.get("width") or 0)
                h = int(st.get("height") or 0)
                rot = 0
                for sd in st.get("side_data_list") or []:
                    if sd.get("rotation") is not None:
                        try:
                            rot = int(round(float(sd["rotation"])))
                        except Exception:
                            rot = 0
                try:
                    rot = int(round(float((st.get("tags") or {}).get("rotate", rot))))
                except Exception:
                    pass
                if abs(rot) % 180 == 90:
                    w, h = h, w          # 표시 치수로 접는다
                rate = str(st.get("r_frame_rate") or "30/1")
                num, _, den = rate.partition("/")
                try:
                    fps_val = float(num) / float(den or 1)
                except Exception:
                    rate, fps_val = "30/1", 30.0
                if w > 0 and h > 0 and fps_val > 0:
                    spec.update({"w": w, "h": h, "fps": rate,
                                 "fps_val": fps_val, "rotation": rot, "ok": True})
            elif st.get("codec_type") == "audio":
                try:
                    spec["sample_rate"] = int(st.get("sample_rate") or 48000)
                    spec["channels"] = int(st.get("channels") or 2)
                except Exception:
                    pass
    except Exception as exc:
        print(f"[RENDER][SPEC] ffprobe 실패 — 기본 규격 유지: {exc}")
    # yuv420p 는 짝수 치수를 요구한다. 실 소스 5/5 가 짝수라 도달하지 않지만,
    # 홀수가 오면 조용히 인코딩이 죽는 대신 한 화소를 깎고 남긴다.
    #
    # ★[RENDER-1 되돌아옴 2026-08-09 · 도달시켜 보니 안 먹던 방어]
    #   이 가드는 "존재는 하는데 작동은 안 하는" 모양이었다. 실측(합성 1081x1921):
    #     [RENDER][SPEC] 홀수 치수 1081x1921 → 짝수로 내림     ← 발동은 한다
    #     ...
    #     [enc:libx264] Could not open encoder before EOF      ← 그런데 그대로 죽는다
    #   원인: 여기서 깎는 것은 **믿음(spec)**이지 화소가 아니다. 그리고 뒤에서
    #   build_scale_pad_vf 가 "클립 규격 == target 이면 scale/pad 를 뺀다"를
    #   **깎은 뒤의 숫자끼리** 비교하니 1080x1920 == 1080x1920 이 되어 scale 이
    #   빠진다 → 1081x1921 프레임이 그대로 yuv420p 인코더로 들어가 죽는다.
    #   그래서 깎기 전의 실제 치수를 따로 남긴다. build_scale_pad_vf 는 이 값으로
    #   비교하므로, 홀수 소스에서는 scale/pad 가 반드시 붙는다(= 실제로 깎인다).
    #   실 소스 5/5 는 짝수라 평상시 도달 0이지만, 도달시켰을 때 실제로
    #   막아야 방어다(CLAUDE.md).
    spec["w_raw"], spec["h_raw"] = spec["w"], spec["h"]
    if spec["w"] % 2 or spec["h"] % 2:
        print(f"[RENDER][SPEC] 홀수 치수 {spec['w']}x{spec['h']} → 짝수로 내림 "
              f"(scale/pad 를 강제로 붙여 실제로 깎는다)")
        spec["w"] -= spec["w"] % 2
        spec["h"] -= spec["h"] % 2
    _SPEC_PROBE_CACHE[key] = spec
    return spec


def choose_target_spec(clips: List[Dict[str, Any]],
                       source_paths: Dict[str, str]) -> Dict[str, Any]:
    """여러 소스가 섞였을 때 어느 규격으로 통일할지 — 자동 결정.

    기준: **승인 원고 안 총 재생시간이 가장 긴 규격**, 동률이면 원고 첫 조각.
      · "최대 해상도"는 업스케일 = 없는 화소 발명이라 거부.
      · "첫 조각" 단독은 0.5초 인트로가 10분물 규격을 정하는 취약함이라 거부.
    질문 게이트를 새로 만들지 않는다(CLAUDE.md: 제약은 내부 계약에만).
    대신 mixed=True 와 note 를 돌려줘 결이 한 문장으로 통보한다.
    """
    tally: Dict[tuple, float] = {}
    order: Dict[tuple, int] = {}
    spec_of: Dict[tuple, Dict[str, Any]] = {}
    # [RENDER-1 되돌아옴 2026-08-09] 렌더 루프와 **같은 폴백**을 쓴다.
    #   실측한 구멍: 렌더 루프는 `clip.get("source_id") or list(source_paths)[0]`
    #   로 첫 소스에 폴백하는데 여기에는 폴백이 없어 그냥 continue 했다.
    #   그러면 tally 가 비고 아래 기본값(1920x1080)이 나간다 —
    #   세로 1080x1920 소스를 넣었는데 결과물 1920x1080 + 필러박스가 나왔고
    #   결은 "1920x1080" 이라고 말했다(읽은 적 없는 숫자). 이 언덕이 걷어낸
    #   바로 그 상수가 뒷문으로 돌아온 자리다.
    _first = next(iter(source_paths.values()), None)
    for pos, clip in enumerate(clips):
        path = source_paths.get(clip.get("source_id")) or _first
        if not path:
            continue
        sp = probe_source_spec(path)
        key = (sp["w"], sp["h"], sp["fps"])
        dur = max(0.0, float(clip.get("end", 0)) - float(clip.get("start", 0)))
        tally[key] = tally.get(key, 0.0) + dur
        order.setdefault(key, pos)
        spec_of.setdefault(key, sp)
    if not tally:
        # ★마른 경로 — 소스 경로가 하나도 없다. 아래 숫자는 **읽은 값이 아니라
        #   기본값**이다. unread 를 달아 결이 지어내지 않게 한다.
        print("[RENDER][SPEC][UNREAD] 소스 경로가 없어 원본 규격을 읽지 못했다 "
              "— 기본 1920x1080@30/1 로 진행(결에게 사실대로 알린다)")
        return {"w": 1920, "h": 1080, "fps": "30/1", "fps_val": 30.0,
                "sample_rate": 48000, "channels": 2,
                "mixed": False, "note": None, "ok": False, "unread": True}
    best = sorted(tally.items(), key=lambda kv: (-kv[1], order[kv[0]]))[0][0]
    target = dict(spec_of[best])
    target["mixed"] = len(tally) > 1
    target["note"] = None
    # ★probe_source_spec 이 ffprobe 실패로 기본값을 돌려준 경우도 마른 경로다.
    #   숫자는 있지만 읽은 숫자가 아니다 — 있는 척하지 않는다.
    target["unread"] = not bool(spec_of[best].get("ok"))
    if target["unread"]:
        print("[RENDER][SPEC][UNREAD] ffprobe 가 원본 규격을 못 냈다 "
              f"— 기본 {target['w']}x{target['h']}@{target['fps']} 로 진행")
        # ★여기서 숫자를 말하면 안 된다 — 실측(2026-08-09): 규격을 못 읽으면
        #   target 은 기본 1920x1080 이 되지만, build_scale_pad_vf 가 "클립 규격 ==
        #   target" 으로 착각해 scale/pad 를 빼는 바람에 **결과물은 원본 그대로
        #   1080x1920 으로 나왔다**. 기본값을 말해도 틀리고 원본을 말해도 못 읽었다.
        #   그래서 아는 것만 말한다: "읽지 못했다, 그래서 보장하지 못한다."
        target["note"] = (
            "원본 영상의 화면 규격을 읽지 못했어요(ffprobe 응답 없음). "
            "그래서 이번 결과물이 원본과 같은 화면 비율·프레임률인지 제가 "
            "보장하지 못해요 — 만들어진 파일을 한 번 확인해 주세요.")
        return target
    if target["mixed"]:
        others = sorted((k for k in tally if k != best), key=lambda k: order[k])
        target["note"] = (
            f"고른 조각들의 화면 규격이 서로 달라요"
            f"({', '.join(f'{w}x{h}' for w, h, _ in others)} 도 섞여 있어요). "
            f"영상 하나는 규격이 하나여야 해서, 가장 오래 나오는 "
            f"{target['w']}x{target['h']}({round(target['fps_val'], 2)}fps)로 맞췄어요 — "
            f"나머지는 잘리지 않게 여백을 넣어 담았어요.")
        print(f"[RENDER][SPEC][MIXED] {dict((f'{k[0]}x{k[1]}@{k[2]}', round(v, 2)) for k, v in tally.items())} "
              f"→ target {target['w']}x{target['h']}@{target['fps']}")
    else:
        print(f"[RENDER][SPEC] 단일 규격 상속: {target['w']}x{target['h']}@{target['fps']} "
              f"audio={target['sample_rate']}Hz/{target['channels']}ch")
    return target


def build_scale_pad_vf(target: Dict[str, Any],
                       clip_spec: Dict[str, Any] = None) -> str:
    """클립 표시 치수가 target 과 같으면 scale/pad 를 아예 넣지 않는다.

    ★손 안 댄 구간의 화질이 원본과 같아야 한다는 요구가 여기서 지켜진다.
      scale 은 치수가 같아도 리샘플 필터를 태우고, pad 는 프레임을 다시 그린다.
      항등일 때 두 필터를 빼면 남는 손실은 인코딩 한 번뿐이다.
    """
    tw, th = int(target["w"]), int(target["h"])
    if clip_spec:
        # ★[RENDER-1 되돌아옴] 비교는 **깎기 전 실제 치수**로 한다(w_raw/h_raw).
        #   깎은 뒤 숫자끼리 비교하면 홀수 소스에서 1080x1920 == 1080x1920 이 되어
        #   scale 이 빠지고, 1081x1921 프레임이 그대로 yuv420p 인코더로 들어가 죽는다
        #   (실측 · 위 probe_source_spec 주석). w_raw 가 없는 옛 dict 는 w 로 되돌린다.
        cw = int(clip_spec.get("w_raw") or clip_spec.get("w") or 0)
        ch = int(clip_spec.get("h_raw") or clip_spec.get("h") or 0)
        if cw == tw and ch == th:
            return "setsar=1"
    return (f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
            f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1")


def preview_target_spec(target: Dict[str, Any], long_edge: int = 1280) -> Dict[str, Any]:
    """미리보기 규격 — 소스 종횡비 그대로 장변만 캡한다(세로면 720x1280).
    구판은 1280x720 상수여서 미리보기와 결과물의 기하가 서로 달랐다."""
    w, h = int(target["w"]), int(target["h"])
    scale = min(1.0, float(long_edge) / float(max(w, h)))
    pw = max(2, int(round(w * scale)) // 2 * 2)
    ph = max(2, int(round(h * scale)) // 2 * 2)
    out = dict(target)
    out["w"], out["h"] = pw, ph
    return out


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
        **소스에서 상속한 target 규격**(해상도·fps·오디오 rate)으로 CFR 정규화한 뒤
        concat 재인코딩으로 합친다.
        [RENDER-1 2026-08-09] 이 줄은 원래 "30fps CFR · 1920x1080 · 48kHz"였다.
        상수를 걷어냈으므로 문장도 같이 걷는다 — 남겨두면 다음 사람이 코드가
        아니라 이 문장을 믿는다. 통일 목표값은 choose_target_spec 이 정한다.
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

            # [RENDER-1] 규격을 상수가 아니라 소스에서 상속한다.
            #   "사용자가 건드리지 않은 것은 CCUT 도 건드리지 않는다."
            target = choose_target_spec(sorted_clips, source_paths)
            t_w, t_h = int(target["w"]), int(target["h"])
            t_fps = str(target["fps"])
            t_gop = max(1, int(round(float(target["fps_val"]))))   # 1초 = keyframe 1개
            t_ar = int(target["sample_rate"])
            t_ac = int(target["channels"])

            # 1. 각 클립 정밀 추출 + 정규화 (target 규격으로 통일 — concat 필터 요구)
            for i, clip in enumerate(sorted_clips):
                src_id = clip.get("source_id") or list(source_paths.keys())[0]
                src_path = source_paths.get(src_id)
                if not src_path:
                    continue
                clip_duration = max(0.0, float(clip["end"]) - float(clip["start"]))
                tmp = clip_dir / f"clip_{i:04d}.mp4"
                # [PUNCH-1 P4] 미리보기(proposal_preview_engine)와 **같은 함수**를 부른다.
                #   [RENDER-1] 이제 둘 다 소스 규격을 상속한다 — 차이는 미리보기가
                #   장변 1280 으로 캡한다는 것뿐이고(preview_target_spec),
                #   종횡비·줌 배율·시점은 같다. 옛 문장("1920x1080 vs 1280x720")은
                #   두 경로가 서로 다른 기하로 돌던 시절 것이라 지웠다.
                _vf = build_scale_pad_vf(target, probe_source_spec(src_path))
                try:
                    from story_gate.proposal_axis import punch_filter
                    _pf = punch_filter(technique, clip.get("fragment_id"),
                                       float(clip["start"]), float(clip["end"]), t_w, t_h,
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
                        #   [RENDER-1] 30 상수 → target fps. 60fps 원본에서 30 을
                        #   그대로 두면 zoompan 이 프레임을 절반으로 세어 길이가 2배가 된다.
                        _vf += f",fps={t_fps}," + _pf
                        print(f"[RENDER][PUNCH] clip {i} {clip.get('fragment_id')} -> {_pf[:70]}...")
                except Exception as _pe:
                    print(f"[RENDER][PUNCH] 필터 생략 (비차단): {_pe}")
                cut_cmd = [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-ss", str(clip["start"]), "-to", str(clip["end"]),
                    "-i", src_path,
                    "-vf", _vf,
                    # [RENDER-1] CFR 은 유지(1.357fps 사고는 디먹서 inpoint/outpoint
                    #   귀속이고 여기는 -ss/-to 다). 값만 소스 상속으로 바꾼다.
                    "-r", t_fps, "-fps_mode", "cfr",
                    # [STREAM-FIX] 1초마다 강제 keyframe — keyframe이 드물면 브라우저가
                    # 조각 경계 이후 디코드를 못 해 멈춘다(seek 불가).
                    "-g", str(t_gop), "-keyint_min", str(t_gop), "-sc_threshold", "0",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-ar", str(t_ar), "-ac", str(t_ac),
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
                # [RENDER-1 되돌아옴 2026-08-09 · 실측으로 걷어냄] 여기에 잠깐
                #   "-r t_fps" 를 넣었었다. 이유로 적어둔 두 문장이 **둘 다 측정으로
                #   틀렸다**:
                #   ① "항등이다" — 아니다. 같은 stage1 클립 3개(60·180·90프레임 =
                #      330)를 두 번 concat 한 격리 실측:
                #        -r 30/1 있음 → 331프레임 (마지막 프레임이 한 번 더 나온다)
                #        -r 없음      → 330프레임 (선언과 정확히 같다)
                #   ② "명시해야 r_frame_rate 를 원본과 같다고 말할 수 있다" — 아니다.
                #      -r 없이도 결과물 r_frame_rate 는 30/1 로 같다(ffprobe 확인).
                #   게다가 미리보기 경로(proposal_preview_engine)는 concat 단에 -r 이
                #   없어서 같은 조각으로 330프레임이 나왔다 — 즉 이 한 줄이 이 언덕이
                #   없애러 온 바로 그것("미리보기와 결과물이 다른 프레임")을 다시 만들고
                #   있었다. 없는 프레임을 CCUT 이 발명하지 않는다.
                #   격자(fps)는 stage1 의 `-r t_fps -fps_mode cfr` 이 이미 못 박는다.
                "-g", str(t_gop), "-keyint_min", str(t_gop), "-sc_threshold", "0",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-ar", str(t_ar), "-ac", str(t_ac),
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
                    # [RENDER-1] 결이 사용자에게 설명할 재료 — 마른 경로 문구.
                    #   spec_note 는 규격이 섞였을 때만 채워진다(평소 None).
                    "spec": {"width": t_w, "height": t_h, "fps": t_fps,
                             "sample_rate": t_ar, "channels": t_ac,
                             "mixed": bool(target.get("mixed")),
                             # ★읽은 숫자인지 기본값인지 — 결이 지어내지 않으려면
                             #   이 한 칸이 있어야 한다.
                             "unread": bool(target.get("unread"))},
                    "spec_note": target.get("note"),
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
