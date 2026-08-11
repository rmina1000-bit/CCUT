"""[LAB-18] 렌더 산출물 계측기 — 렌더 단계 기법은 제안 해시로 잡히지 않는다.

렌더 기법(오디오 페이드·자막 순서 등)은 조각 집합·순서·대사를 바꾸지 않으므로
제안 해시·조각수·순서 해시로는 어떤 차이도 나타나지 않는다. 산출물 자체를 재야 한다.

지표 3종:
  (가) 컷 지점 목록 — 승인 스냅샷(export_input.clips)의 duration 누적에서 유도. 추측 없음.
  (나) 각 컷 전후 오디오 진폭·불연속 — 해당 구간만 wav로 뽑아 실측.
  (다) 실제 실행된 ffmpeg 필터그래프 문자열 원문 — 파싱 결과가 아니라 원문.

이 계측기는 다음 렌더 기법에도 그대로 쓴다. 일회용 아님.

사용:
  python scripts/render_probe.py <export_input_id> <mp4> [--label OFF] [--win-ms 60]
  python scripts/render_probe.py --diff <probe_a.json> <probe_b.json>
"""
import argparse
import array
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

EDGE_GUARD_MS = 10.0     # 컷 순간으로 볼 반폭
NEAR_CUT_MS = 120.0      # 이웃 경계가 이보다 가까우면 창이 겹친다 — 간섭으로 표시


def _db():
    import sqlite3
    con = sqlite3.connect(f"file:{BACKEND_DIR / 'ccut_app.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def cut_points(export_input_id):
    """(가) 컷 지점 — DB의 clip duration 누적. 마지막 경계(=파일 끝)는 제외."""
    con = _db()
    try:
        row = con.execute(
            "SELECT clips, proposal_id, source_id, mode, total_duration "
            "FROM export_input WHERE export_id=?", (export_input_id,)
        ).fetchone()
        if row is None:
            raise SystemExit(f"export_input 없음: {export_input_id}")
        clips = row["clips"]
        if isinstance(clips, str):
            clips = json.loads(clips)
        clips = sorted(clips, key=lambda c: c.get("order", 0))
        cuts, elapsed = [], 0.0
        for clip in clips[:-1]:
            elapsed += float(clip["duration"])
            cuts.append(round(elapsed, 6))
        return {
            "export_input_id": export_input_id,
            "proposal_id": row["proposal_id"],
            "mode": row["mode"],
            "clip_count": len(clips),
            "total_duration": row["total_duration"],
            "fragment_ids": [c["fragment_id"] for c in clips],
            "spans": [[c["fragment_id"], c["start"], c["end"]] for c in clips],
            "cuts_sec": cuts,
        }
    finally:
        con.close()


def encoded_cut_points(export_input_id, workdir=None):
    """(가·정밀) 실제 인코딩된 클립 길이 누적으로 컷 위치를 구한다.

    DB duration 누적은 출력과 어긋난다 — 각 클립이 30fps CFR로 재인코딩되면서
    길이가 프레임 격자에 맞춰 미세하게 달라진다(실측: 합계 104.63 → 출력 104.80).
    어긋난 좌표로 ±60ms 창을 잡으면 엉뚱한 구간을 재게 된다.
    그래서 render_engine._render_with_ffmpeg 의 추출 명령을 그대로 재현해
    ffprobe 로 실제 길이를 잰다. 원본·DB는 읽기만 한다.

    주의: technique=as_is 기준 추출을 재현한다. punch_in 처럼 클립 단계 필터가
    붙는 기법은 길이에 영향이 없지만, 길이를 바꾸는 기법이 생기면 여기도 따라야 한다.
    """
    con = _db()
    try:
        row = con.execute(
            "SELECT clips FROM export_input WHERE export_id=?", (export_input_id,)
        ).fetchone()
        clips = row["clips"]
        if isinstance(clips, str):
            clips = json.loads(clips)
        clips = sorted(clips, key=lambda c: c.get("order", 0))
        paths = {}
        for sid in {c["source_id"] for c in clips}:
            src = con.execute(
                "SELECT file_path FROM sources WHERE source_id=?", (sid,)
            ).fetchone()
            paths[sid] = src["file_path"] if src else None
    finally:
        con.close()

    workdir = Path(workdir or (BACKEND_DIR / "storage" / "_probe_tmp" / "encode"))
    workdir.mkdir(parents=True, exist_ok=True)
    # [RENDER-1 2026-08-09] 옛 1920x1080/30fps 상수는 본선과 어긋나 오판을 낸다.
    #   본선과 **같은 함수**로 규격을 계산한다.
    from engine.render_engine import (choose_target_spec, build_scale_pad_vf,
                                      probe_source_spec)
    _target = choose_target_spec(clips, paths)
    _t_fps = str(_target["fps"])
    _t_gop = str(max(1, int(round(float(_target["fps_val"])))))
    _t_ar = str(int(_target["sample_rate"]))
    _t_ac = str(int(_target["channels"]))
    durations, elapsed, cuts = [], 0.0, []
    for i, clip in enumerate(clips):
        tmp = workdir / f"probe_clip_{i:04d}.mp4"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(clip["start"]), "-to", str(clip["end"]),
            "-i", paths[clip["source_id"]],
            "-vf", build_scale_pad_vf(
                _target, probe_source_spec(paths[clip["source_id"]])),
            "-r", _t_fps, "-fps_mode", "cfr",
            "-g", _t_gop, "-keyint_min", _t_gop, "-sc_threshold", "0",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-ar", _t_ar, "-ac", _t_ac,
            str(tmp),
        ]
        subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
        # 오디오 이음매를 재는 것이므로 컨테이너 길이가 아니라 오디오 스트림 길이를 쓴다.
        # AAC는 1024샘플(48kHz에서 21.3ms) 프레임 단위라 영상 길이와 어긋난다 —
        # 실측: 클립 0~2 컨테이너 합 36.000 vs 실제 오디오 이음매 36.040.
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(tmp)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        actual = float(out.stdout.strip() or 0.0)
        durations.append(round(actual, 6))
        tmp.unlink(missing_ok=True)
        if i < len(clips) - 1:
            elapsed += actual
            cuts.append(round(elapsed, 6))
    return {
        "db_durations": [float(c["duration"]) for c in clips],
        "encoded_durations": durations,
        "db_total": round(sum(float(c["duration"]) for c in clips), 3),
        "encoded_total": round(sum(durations), 3),
        "cuts_sec": cuts,
    }


def filtergraph(export_input_id, mp4=None):
    """(다) 실제 실행된 ffmpeg 명령 원문 — export_results에 저장된 값을 그대로 읽는다.

    export_results 는 export_input_id 하나당 1행만 유지(upsert)한다. 같은
    export_input 을 두 번 렌더하면 앞 행이 덮인다. 그래서 mp4 를 주면
    output_path_internal 이 그 파일인 행만 채택하고, 아니면 못 찾았다고 말한다.
    렌더 직후에 부르지 않으면 다른 회차의 명령을 읽을 수 있다.
    """
    con = _db()
    try:
        row = con.execute(
            "SELECT ffmpeg_command_summary, output_path_internal, status, id "
            "FROM export_results WHERE export_input_id=? ORDER BY rowid DESC LIMIT 1",
            (export_input_id,),
        ).fetchone()
        if row is None:
            return {"found": False}
        if mp4 is not None:
            stored = os.path.basename(row["output_path_internal"] or "")
            if stored != os.path.basename(str(mp4)):
                return {"found": False, "reason": "STALE_ROW",
                        "stored_output": stored,
                        "asked_output": os.path.basename(str(mp4))}
        command = row["ffmpeg_command_summary"] or ""
        graph = None
        if "-filter_complex" in command:
            tail = command.split("-filter_complex", 1)[1].strip()
            graph = tail.split(" -map", 1)[0].strip()
        return {
            "found": True,
            "render_id": row["id"],
            "status": row["status"],
            "output_path": row["output_path_internal"],
            "command_raw": command,
            "filter_complex_raw": graph,
        }
    finally:
        con.close()


def _slice_wav(mp4, start, duration, out_wav):
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{max(0.0, start):.6f}", "-t", f"{duration:.6f}",
        "-i", str(mp4), "-vn", "-ac", "1", "-ar", "48000",
        "-c:a", "pcm_s16le", str(out_wav),
    ]
    run = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    return run.returncode == 0 and Path(out_wav).exists(), " ".join(cmd), run.stderr


def _read_samples(path):
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    samples = array.array("h")
    samples.frombytes(raw)
    return rate, samples


def refine_cuts(mp4, predicted, search_ms=200.0, workdir=None):
    """예측 좌표 근처에서 실제 이음매(무음 노치)를 찾아 확정한다.

    클립 길이 누적으로는 실제 오디오 이음매를 맞힐 수 없다. 각 클립이 AAC로
    재인코딩되면서 디코더 지연이 클립마다 누적되기 때문이다
    (실측: 예측 36.000 vs 실제 36.040, 클립당 약 20ms).
    이음매에는 페이드 때문에 반드시 진폭 최소점이 생기므로 그것을 찾는다.
    OFF본(좁은 페이드)에서 찾은 좌표를 두 본에 똑같이 적용해야 비교가 공정하다.
    """
    workdir = Path(workdir or (BACKEND_DIR / "storage" / "_probe_tmp"))
    workdir.mkdir(parents=True, exist_ok=True)
    refined = []
    for index, cut in enumerate(predicted):
        # 이웃이 가까우면 탐색창을 좁힌다 — 아니면 여러 이음매가 한 점으로 몰린다.
        gaps = [abs(cut - other) for j, other in enumerate(predicted) if j != index]
        span = min(search_ms / 1000.0, 0.45 * min(gaps)) if gaps else search_ms / 1000.0
        tmp = workdir / f"refine_{index:03d}.wav"
        ok, _, _ = _slice_wav(mp4, cut - span, span * 2, tmp)
        if not ok:
            refined.append({"predicted": cut, "refined": cut, "offset_ms": 0.0,
                            "min_peak": None, "ok": False})
            continue
        rate, samples = _read_samples(tmp)
        step = max(1, rate // 1000)          # 1ms 해상도
        best_i, best_v = 0, None
        for i in range(0, len(samples) - step, step):
            peak = max((abs(v) for v in samples[i:i + step]), default=0)
            if best_v is None or peak < best_v:
                best_v, best_i = peak, i
        found = cut - span + best_i / rate
        refined.append({
            "predicted": round(cut, 6),
            "refined": round(found, 6),
            "offset_ms": round((found - cut) * 1000.0, 1),
            "min_peak": round(best_v / 32768.0, 6),
            "ok": True,
        })
        tmp.unlink(missing_ok=True)
    return refined


def audio_at_cuts(mp4, cuts, win_ms=60.0, workdir=None):
    """(나) 컷 전후 진폭·기울기. 실측값을 그대로 싣는다 — 판정선은 보고에서 따진다."""
    workdir = Path(workdir or (BACKEND_DIR / "storage" / "_probe_tmp"))
    workdir.mkdir(parents=True, exist_ok=True)
    win = win_ms / 1000.0
    guard = EDGE_GUARD_MS / 1000.0
    out = []
    for index, cut in enumerate(cuts):
        neighbours = [abs(cut - other) for j, other in enumerate(cuts) if j != index]
        nearest = min(neighbours) if neighbours else None
        tmp = workdir / f"cut_{index:03d}.wav"
        ok, cmd, err = _slice_wav(mp4, cut - win, win * 2, tmp)
        if not ok:
            out.append({"index": index, "cut_sec": cut, "ok": False,
                        "error": err[:200], "cmd": cmd})
            continue
        rate, samples = _read_samples(tmp)
        total = len(samples)
        if total == 0:
            out.append({"index": index, "cut_sec": cut, "ok": False,
                        "error": "빈 wav", "cmd": cmd})
            continue

        def band(a_sec, b_sec):
            lo = max(0, int((a_sec + win) * rate))
            hi = min(total, int((b_sec + win) * rate))
            return samples[lo:hi] if hi > lo else array.array("h")

        def peak(chunk):
            return max((abs(v) for v in chunk), default=0) / 32768.0

        def max_step(chunk):
            return max(
                (abs(chunk[i + 1] - chunk[i]) for i in range(len(chunk) - 1)),
                default=0,
            ) / 32768.0

        pre = band(-win, -guard)
        at = band(-guard, guard)
        post = band(guard, win)
        out.append({
            "index": index,
            "cut_sec": cut,
            "ok": True,
            "nearest_other_cut_ms": round(nearest * 1000.0, 1) if nearest is not None else None,
            "neighbour_interference": bool(nearest is not None and nearest * 1000.0 < NEAR_CUT_MS),
            "peak_pre": round(peak(pre), 4),
            "peak_at_cut": round(peak(at), 4),
            "peak_post": round(peak(post), 4),
            "max_step_at_cut": round(max_step(at), 5),
            "dip_ratio": round(peak(at) / max(peak(pre), peak(post), 1e-6), 4),
            "samples": {"rate": rate, "pre": len(pre), "at": len(at), "post": len(post)},
        })
        tmp.unlink(missing_ok=True)
    return out


def probe(export_input_id, mp4, label, win_ms, cuts_override=None):
    points = cut_points(export_input_id)
    if cuts_override is not None:
        points["cuts_sec_db"] = points["cuts_sec"]
        points["cuts_sec"] = cuts_override["cuts_sec"]
        points["encoded"] = cuts_override
    mp4_path = Path(mp4)
    graph = filtergraph(export_input_id, mp4_path)
    probe_cmd = ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration,size", "-of", "json", str(mp4_path)]
    probe_run = subprocess.run(probe_cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    return {
        "label": label,
        "mp4": str(mp4_path.resolve()),
        "mp4_size": mp4_path.stat().st_size if mp4_path.exists() else 0,
        "ffprobe": probe_run.stdout.strip(),
        "story": points,
        "filtergraph": graph,
        "win_ms": win_ms,
        "cuts": audio_at_cuts(mp4_path, points["cuts_sec"], win_ms),
    }


def diff(a, b):
    story_same = (
        a["story"]["fragment_ids"] == b["story"]["fragment_ids"]
        and a["story"]["spans"] == b["story"]["spans"]
        and a["story"]["cuts_sec"] == b["story"]["cuts_sec"]
    )
    rows = []
    for left, right in zip(a["cuts"], b["cuts"]):
        if not (left.get("ok") and right.get("ok")):
            continue
        rows.append({
            "cut_sec": left["cut_sec"],
            "interference": left["neighbour_interference"],
            f"peak_at_{a['label']}": left["peak_at_cut"],
            f"peak_at_{b['label']}": right["peak_at_cut"],
            f"step_{a['label']}": left["max_step_at_cut"],
            f"step_{b['label']}": right["max_step_at_cut"],
            f"dip_{a['label']}": left["dip_ratio"],
            f"dip_{b['label']}": right["dip_ratio"],
        })
    return {
        "story_same": story_same,
        "filtergraph_same": (a["filtergraph"].get("filter_complex_raw")
                             == b["filtergraph"].get("filter_complex_raw")),
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export_input_id", nargs="?")
    parser.add_argument("mp4", nargs="?")
    parser.add_argument("--label", default="RUN")
    parser.add_argument("--win-ms", type=float, default=60.0)
    parser.add_argument("--out")
    parser.add_argument("--diff", nargs=2, metavar=("A_JSON", "B_JSON"))
    parser.add_argument("--encoded-cuts", action="store_true",
                        help="컷 위치를 DB duration이 아니라 실제 인코딩 길이에서 구한다")
    parser.add_argument("--cuts-json", help="미리 구해둔 encoded_cut_points 결과 재사용")
    args = parser.parse_args()

    if args.diff:
        a = json.loads(Path(args.diff[0]).read_text(encoding="utf-8"))
        b = json.loads(Path(args.diff[1]).read_text(encoding="utf-8"))
        print(json.dumps(diff(a, b), ensure_ascii=False, indent=1))
        return

    if not args.export_input_id or not args.mp4:
        parser.error("export_input_id 와 mp4 가 필요하다")
    override = None
    if args.cuts_json:
        override = json.loads(Path(args.cuts_json).read_text(encoding="utf-8"))
    elif args.encoded_cuts:
        override = encoded_cut_points(args.export_input_id)
    result = probe(args.export_input_id, args.mp4, args.label, args.win_ms, override)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
