"""[거점 / HUB] qwen2.5 단독 판단 모듈.

센서/AVR거점/순차루프 구조의 '거점'. 센서(VL=프레임 raw / Whisper=자막 / 룰=motion·audio)가
책상에 올린 '조각(semantic_fragments)별 데이터'를 받아, 판단은 거점(qwen2)이 단독으로 한다.

원칙:
- 모든 편집은 조각화 후. 거점은 항상 semantic_fragments(SF) 단위를 받는다.
- 거점이 판단·명령. 센서는 데이터만(이 모듈은 센서 출력을 그대로 받아 씀).
- AVR: 책상(32k)이 커도 조각을 순차 배치로 처리(=한 사이클 처리량 제어, 노이즈 국소화).
- 신뢰성: format:json 강제(생짜 호출 JSON 깨짐 방지). 조각은 짧은 번호로 지칭(긴 SF id 멍글 방지).

격리: 이 파일은 백엔드 어디서도 호출되지 않는다. CLI로 라이브 DB read-only 테스트만.
  파이프라인 배선은 다음 단계(P3). 지금은 '거점이 실제로 되는가'를 부품으로 증명.

CLI:
  cd D:\\CCUT1.0.4\\ccut_backend
  python -m engine.hub SRC_8BDF7096 물놀이 --en "water play, beach, swimming"
  python -m engine.hub SRC_5327870D 실내 --en "indoor room, bedroom"
"""
import os
import json
import hashlib
import sqlite3
import urllib.request
try:
    import speed_trace as _speed_trace
except Exception:
    _speed_trace = None

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BACKEND_DIR, "ccut_app.db")

OLLAMA_URL = os.getenv("CCUT_OLLAMA_URL", "http://127.0.0.1:11434")
HUB_MODEL = os.getenv("CCUT_HUB_MODEL", os.getenv("CCUT_CMD_MODEL", "qwen2.5:7b-instruct"))
# [QWEN ROUGH-CUT 2PASS 2026-07-31] 자유출력/JSON 단일 러너 — num_ctx 8192.
# keep_alive 연장(콜드 재로드 +6.5s 실측 관리)은 그대로 유지한다.
# 전 호출 단일 ctx 유지 — 요청별 num_ctx가 다르면 Ollama가 러너를 재적재한다(스왑 비용).
OLLAMA_NUM_CTX = int(os.getenv("CCUT_OLLAMA_NUM_CTX", "8192"))
OLLAMA_KEEP_ALIVE = os.getenv("CCUT_OLLAMA_KEEP_ALIVE", "30m")
# [⑨ 투기 연결부 — OFF 고정(국장 결정)] Ollama는 draft 미지원(B 실측: 효과 0)이라
# 이 플래그는 연결부일 뿐 동작하지 않는다. llama-server 전환 시 이 지점에서 배선.
SPECULATIVE_DRAFT = os.getenv("CCUT_SPECULATIVE", "0") in ("1", "true", "True")
# [⑧ 직렬화] 판사·추출·대화·VL 계열이 같은 GPU를 공유 — hub 경유 호출을 전부 한 줄로
# 세운다 (기본 ON, CCUT_OLLAMA_SERIALIZE=0 가역). VL 워커(qwen_vl_visual_worker)는
# 별도 모듈 호출이라 이 락 밖 — 스왑 겹침은 판사/대화 쪽을 세워서 완화한다.
import threading as _threading
_OLLAMA_LOCK = _threading.Lock()
_SERIALIZE = os.getenv("CCUT_OLLAMA_SERIALIZE", "1") not in ("0", "false", "False")
_SINGLE_CONFIRM_PROMPT_VERSION = "judge_lean_v3_scene_speech_context"
_SINGLE_CONFIRM_CACHE = {}
_PLAN_CACHE = {}  # [R2-A 후속] plan_edit 결과 캐시 (A/B 이중 호출 중복 제거, CCUT_SINGLE_CACHE 가역)


# ---------- 센서 데이터 수집 (read-only) ----------

def load_bundles(con, source_id, desc_max=240, tr_max=120):
    """조각(SF) + VL 시각데이터 + 자막을 조각별 번들로. 라이브 DB SELECT만."""
    cur = con.cursor()
    cur.execute(
        """
        SELECT sf.fragment_id, sf.start, sf.end, fi.visual_desc, fi.transcript
        FROM semantic_fragments sf
        LEFT JOIN fragment_index fi ON fi.fragment_id = sf.fragment_id
        WHERE sf.source_id = ?
        ORDER BY sf.start
        """,
        (source_id,),
    )
    bundles = []
    for fid, s, e, desc, tr in cur.fetchall():
        bundles.append({
            "fid": fid,
            "source_id": source_id,
            "start": round(s or 0.0, 1),
            "end": round(e or 0.0, 1),
            "scene": (desc or "")[:desc_max].replace("\n", " ").strip(),
            "speech": (tr or "")[:tr_max].replace("\n", " ").strip(),
        })
    return bundles


def _load_context_for_sources(con, source_ids):
    ids = []
    for sid in source_ids or []:
        sid = (sid or "").strip()
        if sid and sid not in ids:
            ids.append(sid)
    if not ids:
        return {"project": None, "sources": {}}
    ph = ",".join("?" for _ in ids)
    sources = {}
    try:
        for sid, title, shot_date in con.execute(
            f"SELECT source_id, title, shot_date FROM sources WHERE source_id IN ({ph})",
            ids,
        ):
            sources[sid] = {
                "title": _prompt_field(title, 80),
                "shot_date": shot_date,
                "notes": [],
            }
    except Exception:
        sources = {sid: {"title": "", "shot_date": None, "notes": []} for sid in ids}
    try:
        for sid, note in con.execute(
            f"SELECT target_id, text FROM narrative_notes "
            f"WHERE target_kind='source' AND target_id IN ({ph}) ORDER BY note_id",
            ids,
        ):
            if sid in sources and len(sources[sid]["notes"]) < 4:
                sources[sid]["notes"].append(_prompt_field(note, 80))
    except Exception:
        pass
    project = None
    try:
        rows = list(con.execute(
            f"SELECT DISTINCT ps.program_id, p.name "
            f"FROM project_sources ps JOIN programs p ON p.program_id=ps.program_id "
            f"WHERE ps.source_id IN ({ph})",
            ids,
        ))
        if len(rows) == 1:
            project = {"program_id": rows[0][0], "name": _prompt_field(rows[0][1], 80)}
    except Exception:
        project = None
    return {"project": project, "sources": sources}


def _apply_context_to_bundles(bundles, context):
    sources = (context or {}).get("sources") or {}
    project = (context or {}).get("project")
    for b in bundles or []:
        sid = b.get("source_id")
        if sid in sources:
            b["source_context"] = sources[sid]
        if project:
            b["project_context"] = project
    return bundles


# ---------- 거점 호출 (format:json 강제) ----------

def _ollama_json(prompt: str, timeout: int = 60, temperature: float = 0) -> dict:
    # temperature 기본 0 — 판사(judge) 결정성 불변. 대화 계열만 명시적으로 올린다.
    payload = {
        "model": HUB_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": temperature, "num_predict": 2048,
                    "num_ctx": OLLAMA_NUM_CTX},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL + "/api/generate", data=body,
        headers={"Content-Type": "application/json"},
    )
    trace_id = _speed_trace.get_current() if _speed_trace else None
    call_idx = None
    if trace_id and _speed_trace and _speed_trace.enabled():
        call = {
            "kind": "json",
            "purpose": "routing",
            "model": HUB_MODEL,
            "prompt_chars": len(prompt),
            "body_bytes": len(body),
            "num_ctx": OLLAMA_NUM_CTX,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "temperature": temperature,
            "num_predict": 2048,
            "stop": None,
            "timeout": timeout,
            "payload": payload,
            "t_queue_enter": _speed_trace.now_ms(),
        }
        call_idx = _speed_trace.append_ollama_call(trace_id, call)
    if _SERIALIZE:
        with _OLLAMA_LOCK:
            if trace_id and _speed_trace and _speed_trace.enabled():
                _speed_trace.mark(trace_id, "t3_5", None)
                _speed_trace.update_ollama_call(trace_id, call_idx, t_queue_exit=_speed_trace.now_ms())
                _speed_trace.mark(trace_id, "t4", None)
                _speed_trace.update_ollama_call(trace_id, call_idx, t_request=_speed_trace.now_ms())
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
    else:
        if trace_id and _speed_trace and _speed_trace.enabled():
            _speed_trace.mark(trace_id, "t3_5", None)
            _speed_trace.update_ollama_call(trace_id, call_idx, t_queue_exit=_speed_trace.now_ms())
            _speed_trace.mark(trace_id, "t4", None)
            _speed_trace.update_ollama_call(trace_id, call_idx, t_request=_speed_trace.now_ms())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    if trace_id and _speed_trace and _speed_trace.enabled():
        _speed_trace.update_ollama_call(
            trace_id,
            call_idx,
            t_done=_speed_trace.now_ms(),
            done=bool(data.get("done")),
            done_reason=data.get("done_reason"),
            prompt_eval_count=data.get("prompt_eval_count"),
            eval_count=data.get("eval_count"),
            prompt_eval_duration_ns=data.get("prompt_eval_duration"),
            eval_duration_ns=data.get("eval_duration"),
            load_duration_ns=data.get("load_duration"),
            total_duration_ns=data.get("total_duration"),
            completion_chars=len(str(data.get("response") or "")),
            response_raw=data,
            last_normal_chunk=str(data.get("response") or ""),
            connection_closed_by="ollama" if data.get("done") else "backend",
        )
    return json.loads(data.get("response", "{}") or "{}")


def _ollama_stream(prompt: str, timeout: int = 60, temperature: float = 0.7,
                   num_predict: int = 512, top_p: float = None, top_k: int = None):
    """[F2 스트리밍] 토큰 단위 생성기 — /api/generate stream=true (NDJSON).
    format 미지정(자유 텍스트) — 대화 reply 전용. 판사/추출(format:json) 경로 무접촉.
    [⑥ 샘플링] 대화 프로파일(top_p/top_k)은 호출측이 명시 — 판사 결정론과 분리.
    [⑧ 직렬화] 스트림 전체가 락 구간 — 생성 중 판사/추출이 끼어들지 않는다."""
    opts = {"temperature": temperature, "num_predict": num_predict,
            "num_ctx": OLLAMA_NUM_CTX}
    if top_p is not None:
        opts["top_p"] = top_p
    if top_k is not None:
        opts["top_k"] = top_k
    payload = {
        "model": HUB_MODEL,
        "prompt": prompt,
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": opts,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL + "/api/generate", data=body,
        headers={"Content-Type": "application/json"},
    )
    trace_id = _speed_trace.get_current() if _speed_trace else None
    call_idx = None
    if trace_id and _speed_trace and _speed_trace.enabled():
        call_idx = _speed_trace.append_ollama_call(trace_id, {
            "kind": "stream",
            "purpose": "generation",
            "model": HUB_MODEL,
            "prompt_chars": len(prompt),
            "body_bytes": len(body),
            "num_ctx": OLLAMA_NUM_CTX,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "temperature": temperature,
            "num_predict": num_predict,
            "top_p": top_p,
            "top_k": top_k,
            "stop": opts.get("stop"),
            "timeout": timeout,
            "payload": payload,
            "chunks": [],
            "t_queue_enter": _speed_trace.now_ms(),
        })
    if _SERIALIZE:
        _OLLAMA_LOCK.acquire()
    if trace_id and _speed_trace and _speed_trace.enabled():
        if "t3_5" not in getattr(_speed_trace, "_RECORDS", {}).get(trace_id, {}):
            _speed_trace.mark(trace_id, "t3_5", None)
        _speed_trace.update_ollama_call(trace_id, call_idx, t_queue_exit=_speed_trace.now_ms())
    try:
        if trace_id and _speed_trace and _speed_trace.enabled():
            if "t4" not in getattr(_speed_trace, "_RECORDS", {}).get(trace_id, {}):
                _speed_trace.mark(trace_id, "t4", None)
            _speed_trace.update_ollama_call(trace_id, call_idx, t_request=_speed_trace.now_ms())
        completion_chars = 0
        done_metrics = {}
        stream_closed_by = "backend"
        last_normal_chunk = ""
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                raw_line = line.decode("utf-8", errors="replace")
                try:
                    data = json.loads(raw_line)
                except Exception:
                    if trace_id and _speed_trace and _speed_trace.enabled():
                        rec = getattr(_speed_trace, "_RECORDS", {}).get(trace_id, {})
                        calls = rec.get("ollama_calls") or []
                        call = calls[call_idx] if call_idx is not None and call_idx < len(calls) else {}
                        chunks = list(call.get("chunks") or [])
                        chunks.append({"t": _speed_trace.now_ms(), "raw": raw_line, "parse_error": True})
                        _speed_trace.update_ollama_call(trace_id, call_idx, chunks=chunks)
                    continue
                chunk = data.get("response") or ""
                if chunk:
                    completion_chars += len(chunk)
                    last_normal_chunk = chunk
                    if trace_id and _speed_trace and _speed_trace.enabled():
                        rec = getattr(_speed_trace, "_RECORDS", {}).get(trace_id, {})
                        calls = rec.get("ollama_calls") or []
                        call = calls[call_idx] if call_idx is not None and call_idx < len(calls) else {}
                        chunks = list(call.get("chunks") or [])
                        chunks.append({"t": _speed_trace.now_ms(), "text": chunk, "raw": raw_line})
                        _speed_trace.update_ollama_call(trace_id, call_idx, chunks=chunks,
                                                        last_normal_chunk=chunk)
                        if "t5" not in rec:
                            _speed_trace.mark(trace_id, "t5", None)
                        if not call.get("t_first_token"):
                            _speed_trace.update_ollama_call(
                                trace_id, call_idx, t_first_token=_speed_trace.now_ms())
                    yield chunk
                if data.get("done"):
                    done_metrics = data
                    stream_closed_by = "ollama"
                    break
    except GeneratorExit:
        stream_closed_by = "frontend"
        raise
    except Exception:
        stream_closed_by = "backend"
        raise
    finally:
        if trace_id and _speed_trace and _speed_trace.enabled():
            _speed_trace.update_ollama_call(
                trace_id,
                call_idx,
                t_done=_speed_trace.now_ms(),
                done=bool(done_metrics.get("done")),
                done_reason=done_metrics.get("done_reason"),
                prompt_eval_count=done_metrics.get("prompt_eval_count"),
                eval_count=done_metrics.get("eval_count"),
                prompt_eval_duration_ns=done_metrics.get("prompt_eval_duration"),
                eval_duration_ns=done_metrics.get("eval_duration"),
                load_duration_ns=done_metrics.get("load_duration"),
                total_duration_ns=done_metrics.get("total_duration"),
                completion_chars=completion_chars,
                response_raw=done_metrics or None,
                last_normal_chunk=last_normal_chunk,
                connection_closed_by=stream_closed_by,
            )
        if _SERIALIZE:
            _OLLAMA_LOCK.release()


def _ollama_chat_stream(messages: list[dict], timeout: int = 60, temperature: float = 0.7,
                        num_predict: int = 512, top_p: float = None, top_k: int = None):
    opts = {"temperature": temperature, "num_predict": num_predict,
            "num_ctx": OLLAMA_NUM_CTX}
    if top_p is not None:
        opts["top_p"] = top_p
    if top_k is not None:
        opts["top_k"] = top_k
    payload = {
        "model": HUB_MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": opts,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    trace_id = None
    call_idx = None
    if _speed_trace:
        trace_id = _speed_trace.get_current()
    if trace_id and _speed_trace and _speed_trace.enabled():
        prompt_chars = sum(len(str((m or {}).get("content") or "")) for m in messages or [])
        call_idx = _speed_trace.append_ollama_call(trace_id, {
            "kind": "chat_stream",
            "purpose": "generation",
            "model": HUB_MODEL,
            "prompt_chars": prompt_chars,
            "message_count": len(messages or []),
            "message_roles": [str((m or {}).get("role") or "") for m in messages or []],
            "temperature": temperature,
            "num_ctx": OLLAMA_NUM_CTX,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "num_predict": num_predict,
            "top_p": top_p,
            "top_k": top_k,
            "stop": opts.get("stop"),
            "timeout": timeout,
            "payload": payload,
            "chunks": [],
            "t_queue_enter": _speed_trace.now_ms(),
        })
    if _SERIALIZE:
        if trace_id and _speed_trace and _speed_trace.enabled():
            _speed_trace.mark(trace_id, "t3_5", None)
            _speed_trace.update_ollama_call(trace_id, call_idx, t_queue_exit=_speed_trace.now_ms())
        _OLLAMA_LOCK.acquire()
    try:
        if trace_id and _speed_trace and _speed_trace.enabled():
            _speed_trace.mark(trace_id, "t4", None)
            _speed_trace.update_ollama_call(trace_id, call_idx, t_request=_speed_trace.now_ms())
        completion_chars = 0
        done_metrics = {}
        stream_closed_by = "backend"
        last_normal_chunk = ""
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                raw_line = line.decode("utf-8", errors="replace")
                try:
                    data = json.loads(raw_line)
                except Exception:
                    if trace_id and _speed_trace and _speed_trace.enabled():
                        rec = getattr(_speed_trace, "_RECORDS", {}).get(trace_id, {})
                        calls = rec.get("ollama_calls") or []
                        call = calls[call_idx] if call_idx is not None and call_idx < len(calls) else {}
                        chunks = list(call.get("chunks") or [])
                        chunks.append({"t": _speed_trace.now_ms(), "raw": raw_line, "parse_error": True})
                        _speed_trace.update_ollama_call(trace_id, call_idx, chunks=chunks)
                    continue
                message = data.get("message") if isinstance(data.get("message"), dict) else {}
                chunk = message.get("content") or data.get("response") or ""
                if chunk:
                    completion_chars += len(chunk)
                    last_normal_chunk = chunk
                    if trace_id and _speed_trace and _speed_trace.enabled():
                        rec = getattr(_speed_trace, "_RECORDS", {}).get(trace_id, {})
                        calls = rec.get("ollama_calls") or []
                        call = calls[call_idx] if call_idx is not None and call_idx < len(calls) else {}
                        chunks = list(call.get("chunks") or [])
                        chunks.append({"t": _speed_trace.now_ms(), "text": chunk, "raw": raw_line})
                        _speed_trace.update_ollama_call(trace_id, call_idx, chunks=chunks,
                                                        last_normal_chunk=chunk)
                        if "t5" not in rec:
                            _speed_trace.mark(trace_id, "t5", None)
                        if not call.get("t_first_token"):
                            _speed_trace.update_ollama_call(trace_id, call_idx,
                                                            t_first_token=_speed_trace.now_ms())
                    yield chunk
                if data.get("done"):
                    done_metrics = data
                    stream_closed_by = "ollama"
                    break
    except GeneratorExit:
        stream_closed_by = "frontend"
        raise
    except Exception:
        stream_closed_by = "backend"
        raise
    finally:
        if trace_id and _speed_trace and _speed_trace.enabled():
            _speed_trace.update_ollama_call(
                trace_id,
                call_idx,
                t_done=_speed_trace.now_ms(),
                done=bool(done_metrics.get("done")),
                done_reason=done_metrics.get("done_reason"),
                prompt_eval_count=done_metrics.get("prompt_eval_count"),
                eval_count=done_metrics.get("eval_count"),
                prompt_eval_duration_ns=done_metrics.get("prompt_eval_duration"),
                eval_duration_ns=done_metrics.get("eval_duration"),
                load_duration_ns=done_metrics.get("load_duration"),
                total_duration_ns=done_metrics.get("total_duration"),
                completion_chars=completion_chars,
                response_raw=done_metrics or None,
                last_normal_chunk=last_normal_chunk,
                connection_closed_by=stream_closed_by,
            )
        if _SERIALIZE:
            _OLLAMA_LOCK.release()


def _build_prompt(theme_ko, theme_en, chunk):
    """조각을 번호(1..N)로 지칭. 거점이 테마 판정 + 불확실 시 재분석 명령."""
    theme = theme_ko + (f" ({theme_en})" if theme_en else "")
    lines = []
    for i, b in enumerate(chunk, 1):
        sc = b["scene"] or "(시각데이터 없음)"
        sp = f" / 말소리: {b['speech']}" if b["speech"] else ""
        lines.append(f'{i}. [{b["start"]}~{b["end"]}s] 장면: {sc}{sp}')
    frags = "\n".join(lines)
    return (
        "너는 영상 편집 거점이다. 센서가 올린 조각별 장면 태그를 보고 직접 판단한다.\n"
        f"판정 테마: '{theme}'.\n"
        "각 조각이 이 테마에 해당하는지 판단하라.\n"
        "엄격 규칙: 장면 태그에 분명한 근거가 있을 때만 is_theme=true. 근거 없으면 false(추측 금지).\n"
        "예: '실내' 판정 시 태그에 indoor/room/실내 등 명시 단서가 있어야 함. "
        "school building·concrete ground·schoolyard 등 야외 구조물은 실내가 아니다.\n"
        "장면이 모호하면 recheck=true. reason(근거)은 반드시 한국어로 짧게.\n"
        "JSON만 출력. 형식:\n"
        '{"items":[{"n":번호,"scene":"한단어 장면라벨","is_theme":true/false,'
        '"confidence":0.0~1.0,"recheck":true/false,"reason":"짧은 근거"}]}\n'
        "조각:\n" + frags + "\n"
    )


def judge_theme(source_id, theme_ko, theme_en=None, batch=8, verbose=True):
    """거점이 한 source의 조각들을 테마로 순차 판정. 결과 리스트 반환."""
    con = sqlite3.connect(DB_PATH)
    bundles = load_bundles(con, source_id)
    con.close()
    if not bundles:
        print(f"[HUB] {source_id}: 조각 없음")
        return []

    results = []
    for i in range(0, len(bundles), batch):
        chunk = bundles[i:i + batch]
        prompt = _build_prompt(theme_ko, theme_en, chunk)
        try:
            out = _ollama_json(prompt)
            items = out.get("items") or []
        except Exception as e:
            print(f"[HUB] batch {i // batch} 호출 실패 ({e})")
            items = []
        # [ROBUST] 모델이 간혹 {"n":"t"} 같은 비정형을 내놓아도 판 전체가 죽지 않게
    by_n = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            by_n[int(it.get("n"))] = it
        except (TypeError, ValueError):
            print(f"[HUB-JUDGE][WARN] malformed item skipped: {str(it)[:60]}")
        for j, b in enumerate(chunk, 1):
            it = by_n.get(j, {})
            results.append({
                "fid": b["fid"],
                "time": f'{b["start"]}~{b["end"]}s',
                "scene": it.get("scene"),
                "is_theme": bool(it.get("is_theme")),
                "confidence": it.get("confidence"),
                "recheck": bool(it.get("recheck")),
                "reason": it.get("reason"),
            })
        if verbose:
            print(f"[HUB] 배치 {i // batch + 1}: {len(chunk)}조각 판정 완료")
    return results


# ---------- [P3a] 편집계획: 분해(추출 → judge_theme → 결정론 count) ----------

def _clean_s(v):
    if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none"):
        return v.strip()
    return None


import re

# 알려진 핵심 어휘 = 결정론(손발). 새 표현만 LLM(머리) 폴백.
_THEME_VOCAB = [
    "실내", "실외", "야외", "운동장", "물놀이", "바다", "해변", "해안", "바닷가", "갯벌", "수영", "계곡", "강",
    "풍경", "음식", "요리", "사람", "인물", "아이", "어린이", "가족", "밤", "야경", "거리",
    "호텔", "침실", "방", "체육관", "공원", "놀이터",
    "병원", "지하철",  # [PLACE P1] 장소-단독 명령은 이 어휘(전체풀 judge) 경로
    "큰애", "작은애", "막내", "배경",  # [QWEN-R1 R-b⑤] 가족 호칭·비교 대상 어휘
]
# [QWEN-R1 R-b④] 시간 부사 — 장소 어휘('방' 등)의 부분매칭 오탐원. 테마 매칭 전 마스킹.
_TIME_ADVERBS = ("방금", "아까", "지금")
# [R-b⑤ 방어] 테마 어휘를 부분 포함하는 비편집 결합어 — '배경음악'의 '배경' 오탐 차단.
_VOCAB_GUARD = ("배경음악", "배경 음악")
_NUM_KO = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6,
           "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
_EXCLUDE_MARK = ("빼", "제외", "말고", "없이", "줄여", "줄이", "덜")  # [R-b①] 감축 동사 = exclude 극성
_RUBRIC_EXCLUDE_MARK_EXTRA = ("없는", "없게", "없도록", "제외한")


def _det_count(t):
    """'5개','다섯 개','3컷' → 정수. '명'(사람 수)은 제외. [R-b③] 단위: 개·컷·조각·장면."""
    m = re.search(r"(\d+)\s*(?:개|컷|조각|장면)", t)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 40 else None
    for k, v in _NUM_KO.items():
        if re.search(k + r"\s*(?:개|컷|조각|장면)", t):
            return v
    return None


def _named_persons():
    """[PERSON-PALETTE] 사용자가 이름을 저장한 인물 목록 — 동적 편집 어휘.
    풀네임 + 애칭을 모두 반환(입구 문지기·어휘 노출용). 정규화는 _person_theme가 한다."""
    try:
        con = sqlite3.connect(DB_PATH)
        vocab = []
        for _pid, name, aliases in _person_name_alias_rows(con):
            if name:
                vocab.append(name)
            vocab.extend(a for a in (aliases or "").split(",") if a.strip())
        con.close()
        # 긴 어휘 우선(부분매칭 오탐 완화) + 2자 이상
        return [v for v in sorted(set(vocab), key=len, reverse=True) if len(v) >= 2]
    except Exception:
        return []


def _person_name_alias_rows(con):
    """(person_id, name, aliases) 행. aliases 컬럼이 아직 없는 DB도 안전 폴백."""
    try:
        return list(con.execute(
            "SELECT person_id, name, COALESCE(aliases,'') FROM persons "
            "WHERE status='named' AND name IS NOT NULL AND length(name) >= 2"))
    except sqlite3.OperationalError:
        return [(r[0], r[1], "") for r in con.execute(
            "SELECT person_id, name FROM persons WHERE status='named' AND name IS NOT NULL AND length(name) >= 2")]


def resolve_person_name(text, vocab=None):
    """[PERSON-ALIAS] 명령문에서 인물 이름/애칭을 찾아
    {matched, canonical, person_id, confidence}를 반환. 없으면 None.
    저장은 풀네임, 검색은 애칭 — 애칭('은한이')으로 찾아도 조각 태그(풀네임 '정은한')와
    맞도록 정규화 근거를 제공한다. 긴 표기부터 매칭(부분매칭 오탐 완화).
    vocab: [(person_id, name, [aliases..])] 주입 시 DB 미접근(테스트/재현용)."""
    rows = vocab
    if rows is None:
        try:
            con = sqlite3.connect(DB_PATH)
            rows = [(pid, nm, [a.strip() for a in (al or "").split(",") if a.strip()])
                    for pid, nm, al in _person_name_alias_rows(con)]
            con.close()
        except Exception:
            return None
    cands = []  # (표기, 풀네임, person_id)
    for pid, name, aliases in rows:
        if name and len(name) >= 2:
            cands.append((name, name, pid))
        for a in (aliases or []):
            a = a.strip()
            if len(a) >= 2:
                cands.append((a, name, pid))
    cands.sort(key=lambda x: len(x[0]), reverse=True)
    for token, full, pid in cands:
        if token in text:
            return {"matched": token, "canonical": full, "person_id": pid,
                    "confidence": 1.0 if token == full else 0.95}
    return None


def _person_theme(t):
    """명령의 인물 이름/애칭 → 풀네임 (resolve_person_name 래퍼)."""
    hit = resolve_person_name(t)
    return hit["canonical"] if hit else None


# [고리① QWEN-R1] 인물 그림자 잔여 검출 — 인물 이름과 편집 상용구를 걷어낸 뒤
# 남는 '내용어'가 있으면 결정론은 인물로 확정하지 않는다 ("심장 시술" 소실 사건).
_PERSON_BOILER = (
    "나오는", "나오게", "나온", "나와", "등장하는", "등장", "출연", "보이는", "찍힌", "있는",
    "장면", "조각", "컷", "클립", "부분", "영상",
    "위주로", "중심으로", "만으로",
    "편집", "남겨", "남게", "골라", "모아", "추려", "뽑아", "만들어", "만들", "보여",
    "해 줘", "해줘", "해 봐", "해봐", "주세요", "부탁해", "부탁", "줘", "다시", "좀",
    "빼 줘", "빼줘", "빼고", "빼", "제외", "말고", "없이", "지워", "없애", "삭제", "줄여",
)


def _person_shadow_residue(t, matched_tokens):
    """인물 표기·상용구·숫자를 제거한 잔여 내용어(2자 이상 토큰)를 반환. 없으면 ''."""
    s = t or ""
    for tok in (matched_tokens or []):
        if tok:
            s = s.replace(tok, " ")
    for w in sorted(_PERSON_BOILER, key=len, reverse=True):
        s = s.replace(w, " ")
    s = re.sub(r"\d+\s*(개|컷|조각|장면)?", " ", s)
    s = re.sub(r"[^0-9A-Za-z가-힣]+", " ", s)
    return " ".join(x for x in s.split() if len(x) >= 2)


def _deterministic_intent(t):
    """알려진 어휘에 한해 {keep,exclude,count} 확정. 못 잡으면 theme_found=False."""
    count = _det_count(t)
    is_excl = any(k in t for k in _EXCLUDE_MARK)
    # [R-b②④] 테마 매칭용 사본 — 'X보다'(비교 기준부)와 시간 부사를 마스킹해
    # "인물보다 배경 위주"의 '인물', "방금 그거"의 '방' 오탐을 차단. 극성·count는 원문 그대로.
    t_theme = re.sub(r"\S+보다", " ", t)
    for adv in _TIME_ADVERBS + _VOCAB_GUARD:
        t_theme = t_theme.replace(adv, " ")
    theme = next((kw for kw in _THEME_VOCAB if kw in t_theme), None)
    if theme is None:
        # [PERSON-ALIAS] 저장된 사람 이름/애칭이 명령에 있으면 그 인물의 풀네임이 테마
        # (조각 태그는 '인물:풀네임'이므로 애칭을 풀네임으로 정규화해야 judge가 매칭)
        # [고리① 절단] 단, 인물 밖 내용어가 남으면 확정하지 않는다 — "정은한 심장 시술
        # 장면만"을 keep=정은한으로 깎던 그림자. det 미확정 → LLM 폴백이 테마를 본다.
        hit = resolve_person_name(t)
        if hit:
            _residue = _person_shadow_residue(t, [hit["matched"]])
            if _residue:
                print(f"[HUB-EXTRACT] person-shadow 억제: '{hit['canonical']}' 외 "
                      f"잔여 내용어 {_residue!r} -> det 미확정(LLM 폴백)")
            else:
                theme = hit["canonical"]
    keep = exclude = None
    if theme:
        if is_excl:
            exclude = theme
        else:
            keep = theme
    return {"keep": keep, "exclude": exclude, "count": count,
            "theme_found": theme is not None}


# ---------- [C1] 복합 intent: 절 단위 극성 파서 (env CCUT_COMPOUND_INTENT, #58 승격: 기본 ON) ----------
# 근거: outputs/compound_intent_deep (201케이스) — 문장 전체 극성+next() 1테마 방식은
# useful 14.9%/극성오류 98건, 절 단위 v3는 useful 98.0%/극성오류 4건.
# 사전 확장분은 이 파서 전용(legacy _THEME_VOCAB 무변). 매칭은 longest-match consume.
_COMPOUND_VOCAB_EXTRA = [
    "가족여행", "가족 여행", "여행", "셀카", "셀피", "먹방", "마술", "침대",
    "갯벌", "바닷가", "해안가", "파도", "경치", "나들이",
    "방송", "먹는", "먹기", "식사", "얼굴",  # 부분매칭 방어용('방송'의 '방', '먹방'의 '방' 등)
]
_CLAUSE_MARKS = ("제외하고", "빼고", "말고", "없이", "남기고", "그리고", "하고",
                 ",", ".", "+", "/", "랑", "와", "과", "인데", "지만", "보다")
_RUBRIC_COMPOUND_VOCAB_EXTRA = ("물",)
_RUBRIC_CLAUSE_MARK_EXTRA = ("없는", "없게", "없도록")


def _active_exclude_marks():
    return _EXCLUDE_MARK + (_RUBRIC_EXCLUDE_MARK_EXTRA if _rubric_enabled() else ())


def _active_clause_marks():
    return _CLAUSE_MARKS + (_RUBRIC_CLAUSE_MARK_EXTRA if _rubric_enabled() else ())


def _active_compound_vocab_extra():
    return _COMPOUND_VOCAB_EXTRA + (list(_RUBRIC_COMPOUND_VOCAB_EXTRA) if _rubric_enabled() else [])


def _split_clauses(t):
    """극성 경계('빼고','남기고' 등)와 접속 기호에서 문장을 절로 분리."""
    marks = _active_clause_marks()
    parts = re.split("(" + "|".join(re.escape(m) for m in marks) + ")", t)
    clauses, buf = [], ""
    for part in parts:
        if not part:
            continue
        buf += part
        if part in marks:
            clauses.append(buf.strip())
            buf = ""
    if buf.strip():
        clauses.append(buf.strip())
    return [c for c in clauses if c]


def _clause_term_hits(clause, vocab):
    """절 안에서 non-overlapping longest-match 어휘 히트('먹방' 안의 '방' 오탐 방지)."""
    raw = []
    for term in vocab:
        start = 0
        while True:
            pos = clause.find(term, start)
            if pos < 0:
                break
            raw.append((pos, pos + len(term), term))
            start = pos + 1
    raw.sort(key=lambda h: (-(h[1] - h[0]), h[0], h[2]))
    occupied = [False] * max(len(clause), 1)
    hits = []
    for pos, end, term in raw:
        if any(occupied[i] for i in range(pos, end)):
            continue
        for i in range(pos, end):
            occupied[i] = True
        hits.append((pos, term))
    return [term for pos, term in sorted(hits)]


def _compound_enabled():
    # [#58 C1 승격] 기본 ON — CCUT_COMPOUND_INTENT=0 으로 가역 (구: 기본 OFF)
    return os.getenv("CCUT_COMPOUND_INTENT", "1") not in ("0", "false", "False")


def _rubric_enabled():
    # [RUBRIC-1] 기본 OFF — 켜지기 전까진 아래 plan_edit의 compound-exclude 보정
    # 코드가 아예 실행되지 않는다(기존 동작 100% 무변).
    return os.getenv("CCUT_RUBRIC_ENABLED") in ("1", "true", "True")


def parse_compound_intent(t, vocab=None):
    """한 문장 안의 keep/exclude 를 절 단위로 분리 판정.
    반환: {keep_terms:[], exclude_terms:[], keep_clauses:[], count, found}
    아무 어휘도 못 잡으면 found=False → 호출측은 legacy 경로 그대로."""
    t = t or ""
    # [#58 승격 정합] R-b④⑤ 마스킹 승계(0f81e698) — '방금'의 '방', '배경음악'의
    # '배경' 부분매칭 오탐이 승격 경로에서 되살아나지 않게 동일 차단.
    for _adv in _TIME_ADVERBS + _VOCAB_GUARD:
        t = t.replace(_adv, " ")
    if vocab is None:
        # 인물 이름/애칭도 절 단위 극성 대상("정은한는 빼고 한미숙 위주로")
        vocab = sorted(set(_THEME_VOCAB) | set(_active_compound_vocab_extra()) | set(_named_persons()),
                       key=len, reverse=True)
    keep_terms, exclude_terms, keep_clauses = [], [], []
    for clause in _split_clauses(t):
        hits = _clause_term_hits(clause, vocab)
        if not hits:
            continue
        # 'A보다' = A를 뒤로 미룸(감점) → exclude 취급 (sim v3와 동일)
        local_excl = any(m in clause for m in _active_exclude_marks()) or clause.endswith("보다")
        target = exclude_terms if local_excl else keep_terms
        for h in hits:
            if h not in target:
                target.append(h)
        if not local_excl:
            keep_clauses.append(clause)
    return {"keep_terms": keep_terms, "exclude_terms": exclude_terms,
            "keep_clauses": keep_clauses, "count": _det_count(t),
            "found": bool(keep_terms or exclude_terms)}


_THEME_ALIASES = {
    "실내": ("실내", "indoor", "interior", "inside", "room", "bedroom", "hallway", "corridor", "closet", "bed", "pillow", "wardrobe", "couch", "sofa", "복도", "走廊", "室内", "방", "침실", "체육관", "subway", "train", "bus", "carriage", "지하철", "기차", "버스"),
    "실외": ("실외", "야외", "외부", "밖", "outdoor", "outside", "exterior", "schoolyard", "playground", "street", "road", "park"),
    "야외": ("실외", "야외", "외부", "밖", "outdoor", "outside", "exterior", "schoolyard", "playground", "street", "road", "park"),
    "운동장": ("운동장", "schoolyard", "playground", "field", "ground"),
    "물놀이": ("물놀이", "water play", "swimming", "beach", "sea", "ocean", "pool", "바다", "해변", "수영"),
    "바다": ("바다", "sea", "ocean", "beach", "shore", "해변"),
    "해변": ("해변", "beach", "shore", "sand", "바다"),
    "해안": ("해안", "해안가", "해변", "바닷가", "beach", "shore", "coast", "seaside", "sand", "바다"),
    "바닷가": ("바닷가", "해변", "해안", "beach", "shore", "coast", "sand", "바다"),
    "갯벌": ("갯벌", "mudflat", "tidal flat", "mud", "바다"),
    "수영": ("수영", "swimming", "pool", "water"),
    "계곡": ("계곡", "valley", "stream", "creek"),
    "강": ("강", "river"),
    "풍경": ("풍경", "landscape", "scenery", "view", "background"),
    "음식": ("음식", "food", "meal", "dish"),
    "요리": ("요리", "cooking", "cook", "kitchen"),
    "사람": ("사람", "인물", "person", "people", "child", "kid", "face", "man", "woman", "boy", "girl", "adult", "family", "가족"),
    "인물": ("사람", "인물", "person", "people", "face", "man", "woman", "portrait"),
    "아이": ("아이", "아이들", "어린이", "child", "children", "kid", "kids", "boy", "girl", "toddler", "baby"),
    "어린이": ("아이", "아이들", "어린이", "child", "children", "kid", "kids", "boy", "girl"),
    "아이들": ("아이", "아이들", "어린이", "child", "children", "kid", "kids", "boy", "girl", "toddler", "baby"),
    "가족": ("가족", "family", "사람", "인물", "person", "people", "parent", "mother", "father", "child"),
    "밤": ("밤", "night", "dark"),
    "야경": ("야경", "night view", "nightscape", "night"),
    "거리": ("거리", "street", "road"),
    "호텔": ("호텔", "hotel"),
    "침실": ("침실", "bedroom"),
    "방": ("방", "room"),
    "체육관": ("체육관", "gym", "gymnasium", "indoor gym"),
    "공원": ("공원", "park"),
    "놀이터": ("놀이터", "playground"),
    # [PLACE P1] 장소-단독 명령은 이 결정론 어휘 경로(전체풀 judge)를 탄다 —
    # 파생 라벨로 사전필터하면 리콜이 후퇴하므로. 교집합 경로는 인물+장소 복합 전용.
    "병원": ("병원", "병실", "hospital", "clinic", "ward", "patient", "medical", "nurse"),
    "지하철": ("지하철", "전철", "열차", "subway", "train", "platform", "carriage"),
}

_INDOOR_POSITIVE = _THEME_ALIASES["실내"]
_INDOOR_NEGATIVE = (
    "outdoor", "outside", "exterior", "schoolyard", "school yard", "playground",
    "school building", "building exterior", "concrete ground", "field", "park",
    "street", "road", "beach", "sea", "ocean", "shore", "water play", "swimming",
    "야외", "실외", "외부", "운동장", "놀이터", "공원", "거리", "바다", "해변", "물놀이", "수영",
)


def _scene_text(item):
    scene = item.get("scene")
    if scene:
        return str(scene)
    for key in ("visual_desc", "description", "caption", "summary"):
        if item.get(key):
            return str(item.get(key))
    semantic = item.get("semantic") if isinstance(item.get("semantic"), dict) else {}
    intelligence = item.get("intelligence") if isinstance(item.get("intelligence"), dict) else {}
    parts = [
        semantic.get("topic"),
        semantic.get("scene"),
        semantic.get("description"),
        intelligence.get("visual_desc"),
        intelligence.get("caption"),
    ]
    return " ".join(str(p) for p in parts if p)


def _item_fid(item):
    return item.get("fid") or item.get("fragment_id") or item.get("id")


def _item_time(item):
    if item.get("time"):
        return item.get("time")
    start = item.get("start", item.get("start_time", ""))
    end = item.get("end", item.get("end_time", ""))
    return f"{start}~{end}s" if start != "" or end != "" else ""


def _aliases_for_theme(theme):
    aliases = list(_THEME_ALIASES.get(theme, (theme,)))
    if theme and theme not in aliases:
        aliases.append(theme)
    return tuple(str(a).lower() for a in aliases if a)


def _scene_has_any(scene, aliases):
    text = (scene or "").lower()
    return any(a and a in text for a in aliases)


def _scene_alias_hits(scene, aliases):
    text = (scene or "").lower()
    return [a for a in aliases if a and a.lower() in text]


_RUBRIC_TEXT_ALIASES = {
    "딸기": ("strawberry",),
    "박수": ("clapping", "applause", "applaud"),
    "아빠": ("father", "dad"),
    "케이크": ("cake",),
    "촛불": ("candle",),
    "식당": ("restaurant", "dining"),
    "놀이공원": ("amusement park", "theme park"),
}


_RUBRIC_ABSTRACT_KEEP_ALIASES = {
    "풍경": ("풍경", "경치", "landscape", "scenery", "scenic", "panorama", "view"),
    "경치": ("경치", "풍경", "landscape", "scenery", "scenic", "panorama", "view"),
}


def _evidence_text(item):
    parts = [
        item.get("scene"),
        item.get("speech"),
        item.get("evidence_text"),
        item.get("search_text"),
    ]
    semantic = item.get("semantic") if isinstance(item.get("semantic"), dict) else {}
    intelligence = item.get("intelligence") if isinstance(item.get("intelligence"), dict) else {}
    parts.extend([
        semantic.get("transcript"),
        semantic.get("description"),
        intelligence.get("transcript"),
        intelligence.get("visual_desc"),
    ])
    return " ".join(str(p) for p in parts if p)


def _rubric_term_aliases(term):
    aliases = [str(term or "").strip()]
    aliases.extend(_RUBRIC_TEXT_ALIASES.get(str(term or "").strip(), ()))
    seen = set()
    out = []
    for alias in aliases:
        key = alias.lower()
        if alias and key not in seen:
            seen.add(key)
            out.append(alias)
    return tuple(out)


def _rubric_evidence_hits(term, item):
    text = _evidence_text(item).lower()
    return [a for a in _rubric_term_aliases(term) if a.lower() in text]


def _rubric_abstract_evidence_hits(term, item):
    aliases = _RUBRIC_ABSTRACT_KEEP_ALIASES.get(str(term or "").strip(), ())
    text = _evidence_text(item).lower()
    return [a for a in aliases if a.lower() in text]


def _rubric_guard_abstract_judged(theme, judged, bundles, verbose=True):
    if str(theme or "").strip() not in _RUBRIC_ABSTRACT_KEEP_ALIASES:
        return judged
    by_fid = {b.get("fid"): b for b in bundles}
    guarded = []
    dropped = 0
    for item in judged:
        if not item.get("is_theme"):
            guarded.append(item)
            continue
        bundle = by_fid.get(item.get("fid")) or item
        hits = _rubric_abstract_evidence_hits(theme, bundle)
        if hits:
            item["rubric_abstract_hits"] = hits
            guarded.append(item)
            continue
        dropped += 1
        item = dict(item)
        item["is_theme"] = False
        item["rubric_abstract_guard"] = "no_explicit_evidence"
        item["reason"] = "rubric abstract evidence guard"
        guarded.append(item)
    if dropped and verbose:
        print(
            f"[RUBRIC-1 ABSTRACT-GUARD] keep={theme!r} "
            f"dropped={dropped} no_explicit_evidence"
        )
    return guarded


_RUBRIC_RRF_K = 60


def _rubric_bm25_tokens(text):
    tokens = []
    for raw in re.findall(r"[0-9A-Za-z가-힣]+", str(text or "").lower()):
        if not raw:
            continue
        tokens.append(raw)
        if re.search(r"[가-힣]", raw):
            max_n = min(4, len(raw))
            for n in range(2, max_n + 1):
                for i in range(0, len(raw) - n + 1):
                    tokens.append(raw[i:i + n])
    return tokens


def _rubric_query_tokens(term):
    aliases = []
    aliases.extend(_rubric_term_aliases(term))
    aliases.extend(_aliases_for_theme(term))
    seen_alias = set()
    tokens = []
    seen_token = set()
    for alias in aliases:
        key = str(alias or "").strip().lower()
        if not key or key in seen_alias:
            continue
        seen_alias.add(key)
        for tok in _rubric_bm25_tokens(key):
            if tok not in seen_token:
                seen_token.add(tok)
                tokens.append(tok)
    return tokens


def _rubric_bm25_rank(term, bundles):
    query_tokens = _rubric_query_tokens(term)
    if not query_tokens or not bundles:
        return [], {"query_tokens": query_tokens, "top": []}

    import math
    from collections import Counter

    docs = []
    df = {}
    total_len = 0
    for b in bundles:
        tokens = _rubric_bm25_tokens(_evidence_text(b))
        counts = Counter(tokens)
        docs.append({"bundle": b, "counts": counts, "length": len(tokens)})
        total_len += len(tokens)
        for tok in set(tokens):
            df[tok] = df.get(tok, 0) + 1

    n_docs = len(docs)
    avg_len = (total_len / n_docs) if n_docs else 0.0
    k1 = 1.5
    b_param = 0.75
    ranked = []
    for doc in docs:
        score = 0.0
        matched = []
        length = doc["length"] or 1
        for tok in query_tokens:
            freq = doc["counts"].get(tok, 0)
            if not freq:
                continue
            denom = freq + k1 * (1 - b_param + b_param * (length / (avg_len or 1.0)))
            idf = math.log(1 + (n_docs - df.get(tok, 0) + 0.5) / (df.get(tok, 0) + 0.5))
            score += idf * (freq * (k1 + 1)) / denom
            matched.append(tok)
        if score > 0:
            bundle = doc["bundle"]
            ranked.append({
                "fid": bundle.get("fid"),
                "score": score,
                "matched_tokens": matched,
                "bundle": bundle,
            })
    ranked.sort(key=lambda x: (-x["score"], str(x["fid"] or "")))
    diag = {
        "query_tokens": query_tokens,
        "top": [
            {
                "fid": r["fid"],
                "score": round(r["score"], 4),
                "matched_tokens": r["matched_tokens"][:8],
            }
            for r in ranked[:8]
        ],
    }
    return ranked, diag


def _rubric_rrf_fuse(rankings, k=_RUBRIC_RRF_K):
    fused = {}
    sources = {}
    for source_name, ranked_fids in rankings:
        for idx, fid in enumerate(ranked_fids, 1):
            if not fid:
                continue
            fused[fid] = fused.get(fid, 0.0) + 1.0 / (k + idx)
            sources.setdefault(fid, []).append(source_name)
    return [
        {"fid": fid, "rrf": score, "sources": sources.get(fid, [])}
        for fid, score in sorted(fused.items(), key=lambda x: (-x[1], str(x[0])))
    ]


def _rubric_bundle_keep_item(bundle, reason, extra=None):
    item = {
        "fid": bundle["fid"],
        "time": f'{bundle["start"]}~{bundle["end"]}s',
        "scene": bundle["scene"],
        "speech": bundle.get("speech"),
        "evidence_text": bundle.get("evidence_text") or _evidence_text(bundle),
        "is_theme": True,
        "reason": reason,
    }
    if extra:
        item.update(extra)
    return item


def _rubric_hybrid_keep(theme, deterministic_keep, judged, bundles, count=None, verbose=True):
    bundle_by_fid = {b.get("fid"): b for b in bundles}
    deterministic_by_fid = {
        b.get("fid"): b for b in deterministic_keep if b.get("fid")
    }
    judged_true = [j for j in judged if j.get("is_theme") and j.get("fid")]
    judged_by_fid = {j.get("fid"): j for j in judged_true}
    bm25_ranked, bm25_diag = _rubric_bm25_rank(theme, bundles)
    bm25_by_fid = {r["fid"]: r for r in bm25_ranked if r.get("fid")}

    fused = _rubric_rrf_fuse([
        ("bm25", [r["fid"] for r in bm25_ranked]),
        ("llm", [j["fid"] for j in judged_true]),
        ("evidence", [b["fid"] for b in deterministic_keep if b.get("fid")]),
    ])
    if not fused:
        return [], {
            "bm25": bm25_diag,
            "rrf_top": [],
            "selected": [],
            "selected_count": 0,
        }

    selected = fused
    if isinstance(count, int) and count > 0:
        selected = selected[:count]
    kept = []
    for fused_item in selected:
        fid = fused_item["fid"]
        if fid in deterministic_by_fid:
            b = deterministic_by_fid[fid]
            hits = b.get("rubric_evidence_hits") or _rubric_evidence_hits(theme, b)
            kept.append(_rubric_bundle_keep_item(
                b, "rubric hybrid bm25/evidence match",
                {
                    "rubric_evidence_hits": hits,
                    "rubric_rrf": round(fused_item["rrf"], 6),
                    "rubric_rrf_sources": fused_item["sources"],
                },
            ))
            continue
        if fid in bm25_by_fid:
            b = bm25_by_fid[fid]["bundle"]
            kept.append(_rubric_bundle_keep_item(
                b, "rubric hybrid bm25 match",
                {
                    "rubric_bm25_score": round(bm25_by_fid[fid]["score"], 6),
                    "rubric_bm25_tokens": bm25_by_fid[fid]["matched_tokens"][:8],
                    "rubric_rrf": round(fused_item["rrf"], 6),
                    "rubric_rrf_sources": fused_item["sources"],
                },
            ))
            continue
        if fid in judged_by_fid:
            item = dict(judged_by_fid[fid])
            item["rubric_rrf"] = round(fused_item["rrf"], 6)
            item["rubric_rrf_sources"] = fused_item["sources"]
            kept.append(item)
            continue
        b = bundle_by_fid.get(fid)
        if b:
            kept.append(_rubric_bundle_keep_item(
                b, "rubric hybrid fallback",
                {
                    "rubric_rrf": round(fused_item["rrf"], 6),
                    "rubric_rrf_sources": fused_item["sources"],
                },
            ))

    diag = {
        "bm25": bm25_diag,
        "rrf_top": [
            {
                "fid": item["fid"],
                "rrf": round(item["rrf"], 6),
                "sources": item["sources"],
            }
            for item in fused[:8]
        ],
        "selected": [item.get("fid") for item in kept],
        "selected_count": len(kept),
    }
    if verbose:
        print(
            f"[RUBRIC-1 HYBRID] keep={theme!r} "
            f"bm25={len(bm25_ranked)} llm={len(judged_true)} "
            f"evidence={len(deterministic_keep)} selected={len(kept)} "
            f"count={count}"
        )
    return kept, diag


def _rubric_keep_prepass(theme, bundles, verbose=True):
    matched = []
    remaining = []
    for b in bundles:
        hits = _rubric_evidence_hits(theme, b)
        if hits:
            enriched = dict(b)
            enriched["evidence_text"] = _evidence_text(b)
            enriched["rubric_evidence_hits"] = hits
            matched.append(enriched)
        else:
            remaining.append(b)
    if matched and verbose:
        print(
            f"[RUBRIC-1 EVIDENCE-PREPASS] keep={theme!r} "
            f"matched={len(matched)} judge_rest={len(remaining)}"
        )
    return matched, remaining


def _self_check_item(theme, is_exclude, item):
    scene = _scene_text(item)
    evidence = (_evidence_text(item) or scene) if _rubric_enabled() else scene
    text = evidence.lower()
    aliases = _aliases_for_theme(theme)
    has_theme = (
        (_rubric_enabled() and bool(item.get("rubric_evidence_hits")))
        or _scene_has_any(evidence, aliases)
    )

    if theme == "실내":
        has_indoor = _scene_has_any(scene, _INDOOR_POSITIVE)
        has_outdoor = any(sig in text for sig in _INDOOR_NEGATIVE)
        if is_exclude:
            if has_indoor:
                return "MISMATCH", "excluded indoor signal present"
            return "PASS", None
        if has_outdoor and not has_indoor:
            return "MISMATCH", "strong outdoor signal in indoor-only result"
        if has_indoor:
            return "PASS", None
        return "AMBIGUOUS", "no explicit indoor signal"

    if is_exclude:
        if has_theme:
            return "MISMATCH", f"excluded theme '{theme}' appears in scene"
        return "PASS", None

    if has_theme:
        return "PASS", None
    return "AMBIGUOUS", f"theme '{theme}' not explicit in scene"


def self_check_selection(theme, is_exclude, selected, judged=None, judge_mode=None):
    """Pure post-check: no model calls, no selection changes."""
    selected = selected or []
    judged = judged or []
    if judge_mode is None and theme and not is_exclude and not judged:
        judge_mode = "batch+single"
    mismatches, ambiguous, omitted = [], [], []

    for item in selected:
        verdict, reason = _self_check_item(theme, is_exclude, item)
        if verdict == "MISMATCH":
            mismatches.append({
                "fid": _item_fid(item), "time": _item_time(item),
                "scene": _scene_text(item), "reason": reason
            })
        elif verdict == "AMBIGUOUS":
            ambiguous.append({
                "fid": _item_fid(item), "time": _item_time(item),
                "scene": _scene_text(item), "reason": reason
            })

    selected_ids = {_item_fid(item) for item in selected}
    if theme and not is_exclude:
        for item in judged:
            if _item_fid(item) in selected_ids:
                continue
            verdict, _reason = _self_check_item(theme, False, item)
            if verdict == "PASS" and not bool(item.get("is_theme")):
                omitted.append({
                    "fid": _item_fid(item), "time": _item_time(item),
                    "scene": _scene_text(item), "reason": "judge omitted explicit theme candidate"
                })

    total = len(selected)
    mismatch_count = len(mismatches)
    ambiguous_count = len(ambiguous)
    omitted_count = len(omitted)
    ambiguous_ratio = (ambiguous_count / total) if total else 0.0
    if total == 0:
        status = "FAIL"
    elif mismatch_count >= max(2, int(total * 0.4 + 0.999)):
        status = "FAIL"
    elif mismatch_count or omitted_count:
        status = "WARN"
    elif ambiguous_count and ambiguous_ratio > 0.1:
        status = "WARN"
    else:
        status = "PASS"

    if total == 0:
        message = "요청 조건에 맞는 조각을 찾지 못했습니다."
    elif status == "PASS":
        message = "요청 조건과 선택 조각이 대체로 일치합니다."
    elif status == "FAIL":
        message = "조건을 만족하지 못했습니다. 요청과 다른 컷이 다수 포함됐습니다."
    elif theme == "실내":
        message = "실내로 확정 가능한 조각이 부족해서 일부 애매한 컷이 포함됐거나 누락 후보가 있습니다."
    else:
        message = "요청 조건과 일부 어긋나거나 애매한 컷이 포함됐습니다."

    if judge_mode == "batch":
        status = "WARN"
        message = "batch-only judge result used as final selection"

    result = {
        "status": status,
        "theme": theme,
        "mode": "exclude" if is_exclude else "keep",
        "judge_mode": judge_mode,
        "mismatch_count": mismatch_count,
        "ambiguous_count": ambiguous_count,
        "omitted_count": omitted_count,
        "total_count": total,
        "judged_count": len(judged),
        "message": message,
        "mismatches": mismatches[:8],
        "ambiguous": ambiguous[:8],
        "omitted": omitted[:8],
    }
    return result


def extract_intent(instruction):
    """[추출] 명령 → {keep, exclude, count}. [#58 C1 승격] 절단위 극성 파서 최우선 —
    복합문("셀카는 빼고 가족여행만")의 keep/exclude를 절 단위로 확정 (201케이스
    useful 98% 실측, e302dc87). 못 잡으면 기존 결정론(단일 테마) → LLM 폴백 순서 무변."""
    if _compound_enabled():
        _c = parse_compound_intent(instruction or "")
        # [고리① 절단 — C1 대칭] keep이 전부 인물 표기뿐인데 인물 밖 내용어가 남으면
        # C1도 확정하지 않는다 ("정은한 심장 시술 장면만" -> keep=['정은한'] 그림자 재생산 차단).
        if _c["found"] and _c["keep_terms"] and not _c["exclude_terms"]:
            _persons = set(_named_persons())
            if all(k in _persons for k in _c["keep_terms"]):
                _residue = _person_shadow_residue(instruction or "", _c["keep_terms"])
                if _residue:
                    print(f"[C1-COMPOUND] person-shadow 억제: keep={_c['keep_terms']} 외 "
                          f"잔여 내용어 {_residue!r} -> C1 미확정(det/LLM 폴백)")
                    _c = {**_c, "found": False}
        if _c["found"]:
            print(f"[C1-COMPOUND] keep={_c['keep_terms']} exclude={_c['exclude_terms']} "
                  f"count={_c['count']} (extract_intent 승격 경로)")
            _base = {"keep": (_c["keep_terms"][0] if _c["keep_terms"] else None),
                     "exclude": (_c["exclude_terms"][0] if _c["exclude_terms"] else None),
                     "count": _c["count"],
                     "keep_terms": _c["keep_terms"],
                     "exclude_terms": _c["exclude_terms"],
                     "keep_clauses": _c["keep_clauses"]}
            # [4b M3 해소] exclude만 확정되고 keep측 잔여 내용어가 남으면("정은한 빼고
            # 심장 시술만") keep은 이해층(LLM+번역)으로 보충 — exclude는 결정론 우선 유지.
            if _c["exclude_terms"] and not _c["keep_terms"]:
                _residue = _person_shadow_residue(instruction or "", _c["exclude_terms"])
                if _residue:
                    print(f"[C1-COMPOUND] exclude 확정 + keep측 잔여 {_residue!r} -> "
                          "keep은 LLM 이해층 보충")
                    _llm = _llm_extract_intent(instruction, det_count=_c["count"])
                    if _llm.get("keep"):
                        _base["keep"] = _llm["keep"]
                        if _llm.get("keep_query"):
                            _base["keep_query"] = _llm["keep_query"]
                            _base["translated"] = _llm.get("translated")
            return _base
    det = _deterministic_intent(instruction or "")
    if det["theme_found"]:
        print(f"[HUB-EXTRACT] det keep={det['keep']} exclude={det['exclude']} count={det['count']}")
        return {"keep": det["keep"], "exclude": det["exclude"], "count": det["count"]}
    # 어휘 못 잡음 → LLM 폴백(새 표현). count는 결정론값 우선.
    return _llm_extract_intent(instruction, det_count=det["count"])


def _llm_extract_intent(instruction, det_count=None):
    """[4b 번역층 — 국장 A 확정 2026-07-18] 큐원이 새 표현의 keep/exclude를 뽑고,
    상위 개념은 근접 '태그 어휘'로 번역까지 제안한다("심장 시술"→"병원"). 규칙이
    화이트리스트(_THEME_VOCAB)로 검증한 번역만 keep_query/exclude_query로 채택 —
    원문 keep/exclude는 불변 보존(조건 1), 번역 채택 시 translated로 §5 고지(조건 2).
    판사 규칙 무접촉 — 번역은 검색층 테마 선택에서만 쓰인다."""
    vocab_line = ", ".join(_THEME_VOCAB)
    prompt = (
        "사용자 영상편집 명령에서 아래 항목만 뽑아 JSON으로 출력한다. 조각 판단/선택은 하지 마라.\n"
        f"명령: {instruction}\n"
        "키: keep(남길 내용조건 명사구, 없으면 null), "
        "exclude(빼야 할 내용조건, 없으면 null), count(조각 개수 정수, 없으면 null), "
        "keep_vocab(keep과 개념이 충분히 가까운 아래 태그 어휘 1개, 가까운 것이 없으면 null), "
        "exclude_vocab(exclude에 대해 같은 규칙)\n"
        f"태그 어휘: {vocab_line}\n"
        "예시:\n"
        '  "실내만" -> {"keep":"실내","exclude":null,"count":null,"keep_vocab":"실내","exclude_vocab":null}\n'
        '  "실내 빼줘" -> {"keep":null,"exclude":"실내","count":null,"keep_vocab":null,"exclude_vocab":"실내"}\n'
        '  "철수 심장 수술 장면만" -> {"keep":"심장 수술","exclude":null,"count":null,"keep_vocab":"병원","exclude_vocab":null}\n'
        '  "우주선 나오는 장면만" -> {"keep":"우주선","exclude":null,"count":null,"keep_vocab":null,"exclude_vocab":null}\n'
        '  "한명만 있는 조각만" -> {"keep":"한 명만 있는 장면","exclude":null,"count":null,"keep_vocab":null,"exclude_vocab":null}\n'
        '  "물놀이 5개" -> {"keep":"물놀이","exclude":null,"count":5,"keep_vocab":"물놀이","exclude_vocab":null}\n'
        '  "더 빠르게" -> {"keep":null,"exclude":null,"count":null,"keep_vocab":null,"exclude_vocab":null}\n'
        "JSON만:"
    )
    try:
        out = _ollama_json(prompt)
    except Exception as e:
        print(f"[HUB-EXTRACT] 실패 ({e})")
        return {"keep": None, "exclude": None, "count": None}
    c = out.get("count")
    if isinstance(c, bool):
        c = None
    llm_count = int(c) if isinstance(c, (int, float)) and 1 <= int(c) <= 40 else None
    # 개수는 결정론('N개')이 LLM보다 신뢰도 높음 → 결정론 우선
    final_count = det_count if det_count is not None else llm_count
    keep = _clean_s(out.get("keep"))
    exclude = _clean_s(out.get("exclude"))

    def _vocab_ok(orig, v):
        """[4b 규칙 검증] 화이트리스트 어휘만 + 원문이 이미 담은 어휘는 번역 아님."""
        v = _clean_s(v)
        if not orig or not v or v not in _THEME_VOCAB:
            return None
        return None if v in orig else v

    keep_q = _vocab_ok(keep, out.get("keep_vocab"))
    excl_q = _vocab_ok(exclude, out.get("exclude_vocab"))
    result = {"keep": keep, "exclude": exclude, "count": final_count}
    if keep_q:
        result["keep_query"] = keep_q
        result["translated"] = {"from": keep, "to": keep_q}
    elif excl_q:
        result["exclude_query"] = excl_q
        result["translated"] = {"from": exclude, "to": excl_q}
    print(f"[HUB-EXTRACT] llm keep={keep} exclude={exclude} count={final_count} "
          f"keep_query={result.get('keep_query')} exclude_query={result.get('exclude_query')}")
    return result


GOLDEN_CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_cases.json")


def _load_golden_cases():
    """확정 골든 케이스 로드({theme, tags, gold}). 파일 없거나 깨지면 빈 리스트(프롬프트는 기본 규칙만)."""
    try:
        with open(GOLDEN_CASES_PATH, encoding="utf-8") as f:
            cases = json.load(f).get("cases", [])
        return [c for c in cases if isinstance(c, dict) and c.get("tags") and c.get("theme")]
    except Exception:
        return []


def _golden_fewshot_block(theme, max_examples=6):
    """현재 테마의 골든 케이스에서 대표 예시 블록 생성(true/false 균형, 최대 6개).
    해당 테마 골든이 없으면 빈 문자열 — 다른 테마 라벨을 섞어 오도하지 않는다."""
    cases = [c for c in _load_golden_cases() if c.get("theme") == theme]
    if not cases:
        return ""
    pos = [c for c in cases if c.get("gold")][:max_examples // 2]
    neg = [c for c in cases if not c.get("gold")][:max_examples - len(pos)]
    picked = pos + neg
    if not picked:
        return ""
    lines = [f'- "{c["tags"]}" -> t={"true" if c.get("gold") else "false"}' for c in picked]
    return "확정 예시:\n" + "\n".join(lines) + "\n"


def _prompt_field(value, max_len):
    text = " ".join(str(value or "").replace("\n", " ").split()).strip()
    return text[:max_len]


def _context_block_for_chunk(chunk):
    project = next((b.get("project_context") for b in chunk if b.get("project_context")), None)
    source_rows = []
    seen = set()
    for b in chunk:
        sid = b.get("source_id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        ctx = b.get("source_context") if isinstance(b.get("source_context"), dict) else {}
        if ctx:
            source_rows.append({
                "source_id": sid,
                "title": ctx.get("title"),
                "shot_date": ctx.get("shot_date"),
                "notes": ctx.get("notes") or [],
            })
    if not project and not source_rows:
        return ""
    return json.dumps({"project": project, "sources": source_rows[:8]}, ensure_ascii=False)


def _bundle_context_text(bundle):
    parts = []
    project = bundle.get("project_context") if isinstance(bundle.get("project_context"), dict) else {}
    source = bundle.get("source_context") if isinstance(bundle.get("source_context"), dict) else {}
    if project.get("name"):
        parts.append(str(project.get("name")))
    if source.get("title"):
        parts.append(str(source.get("title")))
    for note in source.get("notes") or []:
        if note:
            parts.append(str(note))
    return " ".join(parts)


def _compact_match_text(text):
    return re.sub(r"\s+", "", str(text or "").lower())


def _context_matches_theme(bundle, theme):
    ctx = _compact_match_text(_bundle_context_text(bundle))
    if not ctx:
        return False
    terms = [theme]
    try:
        terms.extend(_get_theme_aliases(theme))
    except Exception:
        pass
    for term in terms:
        t = _compact_match_text(term)
        if len(t) >= 2 and t in ctx:
            return True
    return False


def _local_contradicts_theme(bundle, theme):
    local = f'{bundle.get("scene") or ""} {bundle.get("speech") or ""}'
    t = _compact_match_text(theme)
    if len(t) < 2 or t not in _compact_match_text(local):
        return False
    return any(marker in local for marker in ("아님", "아니", "없음", "없는", "not "))


def _build_judge_lean(theme, chunk):
    """[속도] 판정 전용 lean 프롬프트 — 출력은 {n,t}만(why/recheck 제거 = 생성 토큰↓).
    경계 판단은 산문 규칙 대신 골든 케이스 few-shot 예시(golden_cases.json)로 전달."""
    lines = []
    for i, b in enumerate(chunk, 1):
        scene = _prompt_field(b.get("scene"), 240) or "(none)"
        speech = _prompt_field(b.get("speech"), 120) or "(none)"
        lines.append(f"{i}. scene: {scene} | speech: {speech}")
    context_block = _context_block_for_chunk(chunk)
    return (
        f"각 조각이 테마 '{theme}'에 해당하면 t=true, 아니면 t=false. "
        "scene/speech/상위맥락 중 분명한 근거가 없으면 false(추측 금지).\n"
        "각 조각 입력은 scene(시각)과 speech(Whisper 전사)이다. 둘을 함께 보되, 근거 없는 추측은 금지한다.\n"
        + (f"상위맥락(영상/프로젝트)은 약한 가중치다. source note처럼 명시된 상위 진실은 근거가 될 수 있지만, scene/speech와 충돌하면 덮어쓰지 말라:\n{context_block}\n" if context_block else "")
        + _golden_fewshot_block(theme)
        + '오직 JSON: {"items":[{"n":번호,"t":true}]}\n'
        "조각:\n" + "\n".join(lines)
    )


def _build_fragment_decision_prompt(theme, bundle, project_context=None):
    meta = {
        "fid": bundle.get("fid"),
        "source_id": bundle.get("source_id"),
        "time": f'{bundle.get("start")}~{bundle.get("end")}s',
        "theme": theme,
    }
    if project_context:
        meta["project_context"] = project_context
    payload = {
        "scene": _prompt_field(bundle.get("scene"), 240),
        "speech": _prompt_field(bundle.get("speech"), 120),
        "source_context": bundle.get("source_context"),
        "project_context": bundle.get("project_context"),
        "meta": meta,
    }
    return (
        "You are CCUT's fragment meaning judge. Decide a short fragment name and meaning from sensors only.\n"
        "Use scene, speech, and meta together. Do not invent people, objects, dialogue, or intent not present in input.\n"
        "Return JSON only with this schema: "
        '{"name":"short Korean noun phrase","meaning":"one Korean sentence","evidence":["scene: ...","speech: ...","context: ...","meta: ..."]}\n'
        "Input:\n" + json.dumps(payload, ensure_ascii=False)
    )


def _sensor_evidence(bundle):
    evidence = []
    scene = _prompt_field((bundle or {}).get("scene"), 120)
    speech = _prompt_field((bundle or {}).get("speech"), 120)
    if scene:
        evidence.append(f"scene: {scene}")
    if speech:
        evidence.append(f"speech: {speech}")
    # [관문D 2026-07-20 stash이식] context 근거 노출 — project명·source제목·notes.
    #   있을 때만 추가(지어내기 0). speech·scene·context 3종 근거를 얇게 드러낸다.
    context_text = _prompt_field(_bundle_context_text(bundle or {}), 180)
    if context_text:
        evidence.append(f"context: {context_text}")
    if bundle:
        evidence.append(
            f'meta: fid={bundle.get("fid")} source_id={bundle.get("source_id")} '
            f'time={bundle.get("start")}~{bundle.get("end")}s'
        )
    return evidence[:4]


def _sanitize_fragment_decision(raw, bundle=None):
    if not isinstance(raw, dict):
        return None
    name = _prompt_field(raw.get("name"), 40)
    meaning = _prompt_field(raw.get("meaning"), 160)
    if not name or not meaning:
        return None
    return {"name": name, "meaning": meaning, "evidence": _sensor_evidence(bundle)}


def _decide_fragment_name_meaning(theme, bundle, project_context=None):
    prompt = _build_fragment_decision_prompt(theme, bundle, project_context=project_context)
    try:
        return _sanitize_fragment_decision(
            _ollama_json(prompt, timeout=45, temperature=0),
            bundle=bundle,
        )
    except Exception as e:
        return {"name": None, "meaning": None, "evidence": [], "error": str(e)}


def _requery_indoor_signal(scene, aliases, fid=None):
    prompt = (
        f"센서 데이터: {scene}\n"
        f"센서가 실내 관련 사물 ({', '.join(aliases)})을 감지했다. "
        "이 장면은 실내인가?\n"
        "반드시 한국어로만 답하라.\n"
        '{"indoor": true/false, "reason": "..."}'
    )
    import time as _t
    _t0 = _t.time()
    out = _ollama_json(prompt)
    elapsed = _t.time() - _t0
    result = bool(out.get("indoor"))
    print(
        f"[P3b REQUERY] frag={fid or 'UNKNOWN'} alias={','.join(aliases)} "
        f"judge=false -> requery={str(result).lower()} time={elapsed:.2f}s"
    )
    return result


def _requery_theme_signal(theme, scene, aliases, fid=None):
    """[PERSON-PALETTE] 실내 재질의 패턴의 일반화: 센서 alias가 있는데 judge=false인
    조각을 테마 문구로 허브에 재질의. 판단 주체는 여전히 hub 1곳."""
    prompt = (
        f"센서 데이터: {scene}\n"
        f"센서가 '{theme}' 관련 단서 ({', '.join(aliases)})를 감지했다. "
        f"이 장면은 '{theme}'에 해당하는가?\n"
        "반드시 한국어로만 답하라.\n"
        '{"match": true/false, "reason": "..."}'
    )
    import time as _t
    _t0 = _t.time()
    out = _ollama_json(prompt)
    elapsed = _t.time() - _t0
    result = bool(out.get("match"))
    print(
        f"[P3b REQUERY] frag={fid or 'UNKNOWN'} theme={theme} alias={','.join(aliases)} "
        f"judge=false -> requery={str(result).lower()} time={elapsed:.2f}s"
    )
    return result


# [PERSON-PALETTE] 인물 계열 테마 — CCUT_PERSON_REQUERY=1일 때만 재질의 승격 (기본 OFF)
_PERSON_THEMES = ("사람", "인물", "아이", "어린이")


def _golden_exact_verdict(theme, scene):
    """[R3] 확정 골든과 센서 텍스트가 정확히 일치하면 그 gold를 결정론으로 반환.
    (SF_566DF6: 동일 장면이 퓨샷에 t=true로 있어도 모델이 false → 확정 라벨은 재판단 금지)
    일치 기준은 정규화 해시(_scene_sensor_hash) — 퍼지 매칭 없음."""
    h = _scene_sensor_hash(scene)
    for c in _load_golden_cases():
        if c.get("theme") == theme and _scene_sensor_hash(c.get("tags")) == h:
            return bool(c.get("gold"))
    return None


def _normalize_judge_theme_decision(theme, scene, raw_value, fid=None):
    """Post-process hub judge output with deterministic scene boundary rules."""
    golden = _golden_exact_verdict(theme, scene)
    if golden is not None:
        if golden != bool(raw_value):
            print(f"[P3b GOLDEN-MATCH] frag={fid or 'UNKNOWN'} theme={theme} "
                  f"judge={str(bool(raw_value)).lower()} -> golden={str(golden).lower()} (확정 라벨 우선)")
        return golden
    decision = bool(raw_value)
    if theme == "실내":
        if decision:
            return True
        aliases = _scene_alias_hits(scene, _INDOOR_POSITIVE)
        if aliases:
            try:
                return _requery_indoor_signal(scene, aliases, fid=fid)
            except Exception as e:
                print(f"[P3b REQUERY][WARN] frag={fid or 'UNKNOWN'} failed ({e}) -> keep judge=false")
                return False
        return False
    if theme in _PERSON_THEMES and os.getenv("CCUT_PERSON_REQUERY") in ("1", "true", "True"):
        if decision:
            return True
        aliases = _scene_alias_hits(scene, _aliases_for_theme(theme))
        if aliases:
            try:
                return _requery_theme_signal(theme, scene, aliases, fid=fid)
            except Exception as e:
                print(f"[P3b REQUERY][WARN] frag={fid or 'UNKNOWN'} failed ({e}) -> keep judge=false")
                return False
        return False
    return decision


def _judge_one_chunk(theme_ko, chunk, chunk_no):
    """청크 1개 판단 → 결과 리스트. 병렬/순차 공용 (내용·프롬프트 동일 = 편향 중립)."""
    prompt = _build_judge_lean(theme_ko, chunk)
    try:
        out = _ollama_json(prompt)
        items = out.get("items") or []
    except Exception as e:
        print(f"[HUB-JUDGE] batch {chunk_no} 실패 ({e})")
        items = []
    # [ROBUST] 모델이 간혹 {"n":"t"} 같은 비정형을 내놓아도 판 전체가 죽지 않게
    by_n = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            by_n[int(it.get("n"))] = it
        except (TypeError, ValueError):
            print(f"[HUB-JUDGE][WARN] malformed item skipped: {str(it)[:60]}")
    results = []
    for j, b in enumerate(chunk, 1):
        it = by_n.get(j, {})
        raw_t = bool(it.get("t"))
        normalized_t = _normalize_judge_theme_decision(theme_ko, b["scene"], raw_t, fid=b["fid"])
        context_applied = False
        context_reason = None
        if not normalized_t and _context_matches_theme(b, theme_ko) and not _local_contradicts_theme(b, theme_ko):
            normalized_t = True
            context_applied = True
            context_reason = "source_context"
        results.append({
            "fid": b["fid"], "time": f'{b["start"]}~{b["end"]}s',
            "scene": b["scene"],
            "is_theme": normalized_t,
            "batch_raw_is_theme": raw_t,
            "requery_applied": bool(normalized_t and not raw_t),
            "context_applied": context_applied,
            "context_reason": context_reason,
            "confidence": None, "recheck": False, "reason": None,
        })
    return results


_BATCH_JUDGE_CACHE = {}  # [SPEED-②] 조각 단위 배치판단 캐시 — 영상 추가 시 새 조각만 판단


def _batch_cache_key(theme_ko, b):
    return (b.get("fid"), theme_ko, _bundle_sensor_hash(b),
            HUB_MODEL, _SINGLE_CONFIRM_PROMPT_VERSION, _golden_state_sig())


def _judge_batch(theme_ko, bundles, theme_en=None, batch=8):
    """[속도] 조각 묶음을 배치 판단. lean 출력({n,t})로 생성 토큰 최소화.
    출력키는 plan_edit이 쓰는 fid/time/scene/is_theme 유지.

    [SPEED-②] CCUT_SINGLE_CACHE=1이면 조각 단위 캐시 — 같은 테마·같은 장면은 재판단 없음.
    (영상을 추가해도 새 조각만 LLM에 감. pool 서명 기반 plan 캐시의 증분 보완)
    [JUDGE-PAR] CCUT_JUDGE_PARALLEL=N (기본 1=기존 순차 무변): 청크를 N개 동시 요청.
    서버가 OLLAMA_NUM_PARALLEL 슬롯을 열어야 실효 (기본 auto 1|4).
    청크 구성·프롬프트는 순차와 동일 — 위치편향 구조 불변, 결과는 원래 순서로 병합."""
    use_cache = os.getenv("CCUT_SINGLE_CACHE") in ("1", "true", "True")
    cached_by_fid = {}
    todo = []
    if use_cache:
        for b in bundles:
            hit = _BATCH_JUDGE_CACHE.get(_batch_cache_key(theme_ko, b))
            if hit is not None:
                cached_by_fid[b["fid"]] = dict(hit)
            else:
                todo.append(b)
        if cached_by_fid:
            print(f"[P3b BATCH-CACHE] hit={len(cached_by_fid)}/{len(bundles)} judge_todo={len(todo)}")
    else:
        todo = list(bundles)

    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    try:
        workers = max(1, min(int(os.getenv("CCUT_JUDGE_PARALLEL", "1")), 8))
    except Exception:
        workers = 1
    if workers <= 1 or len(chunks) <= 1:
        fresh = []
        for no, chunk in enumerate(chunks):
            fresh.extend(_judge_one_chunk(theme_ko, chunk, no))
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            chunk_results = list(ex.map(
                lambda t: _judge_one_chunk(theme_ko, t[1], t[0]), enumerate(chunks)))
        fresh = []
        for r in chunk_results:
            fresh.extend(r)

    # [SPEED-②] 새 판단 캐시 저장 + 원래 bundles 순서로 병합
    fresh_by_fid = {}
    for item in fresh:
        fresh_by_fid[item["fid"]] = item
        if use_cache:
            b = next((x for x in todo if x["fid"] == item["fid"]), None)
            if b is not None:
                _BATCH_JUDGE_CACHE[_batch_cache_key(theme_ko, b)] = dict(item)
    results = []
    for b in bundles:
        item = fresh_by_fid.get(b["fid"]) or cached_by_fid.get(b["fid"])
        if item is not None:
            results.append(item)
    return results


def _judge_single_confirm(theme_ko, bundle):
    import time as _t
    _t0 = _t.time()
    try:
        out = _ollama_json(_build_judge_lean(theme_ko, [bundle]))
        items = out.get("items") or []
        item = next((it for it in items if isinstance(it, dict) and int(it.get("n", 0) or 0) == 1), None)
        if item is None:
            raise ValueError("missing single judge item")
        result = _normalize_judge_theme_decision(theme_ko, bundle.get("scene"), item.get("t"), fid=bundle.get("fid"))
        return bool(result), _t.time() - _t0, None
    except Exception as e:
        return False, _t.time() - _t0, e


def _single_cache_enabled():
    return os.getenv("CCUT_SINGLE_CACHE") in ("1", "true", "True")


def _scene_sensor_hash(scene):
    normalized = " ".join(str(scene or "").split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _bundle_sensor_hash(bundle):
    scene = _prompt_field(bundle.get("scene"), 240).lower()
    speech = _prompt_field(bundle.get("speech"), 120).lower()
    context = _prompt_field(_bundle_context_text(bundle), 320).lower()
    return hashlib.sha256(f"scene:{scene}\nspeech:{speech}\ncontext:{context}".encode("utf-8")).hexdigest()[:16]


def _golden_state_sig():
    """[AUDIT-⑽] golden_cases.json 변경 시 캐시 무효화용 서명 (mtime+size).
    골든 추가/수정이 재시작 없이도 판정 캐시에 반영되게 한다."""
    try:
        st = os.stat(GOLDEN_CASES_PATH)
        return f"{st.st_mtime_ns}:{st.st_size}"
    except Exception:
        return "no-golden"


def _single_cache_key(theme_ko, bundle):
    return (
        bundle.get("fid"),
        theme_ko,
        _bundle_sensor_hash(bundle),
        HUB_MODEL,
        _SINGLE_CONFIRM_PROMPT_VERSION,
        _golden_state_sig(),
    )


def _confirm_keep_candidates_single(theme_ko, judged, bundles):
    bundle_by_fid = {b.get("fid"): b for b in bundles}
    batch_keep = 0
    confirmed = 0
    single_calls = 0
    cache_hits = 0
    cache_misses = 0
    total_time = 0.0
    use_cache = _single_cache_enabled()

    for item in judged:
        batch_t = bool(item.get("is_theme"))
        item["batch_is_theme"] = batch_t
        item["judge_mode"] = "batch"
        if not batch_t:
            continue

        batch_keep += 1
        if item.get("requery_applied"):
            confirmed += 1
            item["single_is_theme"] = bool(item.get("is_theme"))
            item["single_time_sec"] = 0.0
            item["judge_mode"] = "batch+requery"
            print(
                f"[P3b SINGLE-CONFIRM] frag={item.get('fid')} "
                "batch=true -> single=t skipped=requery"
            )
            continue

        bundle = bundle_by_fid.get(item.get("fid")) or {
            "fid": item.get("fid"),
            "scene": item.get("scene") or "",
            "start": 0,
            "end": 0,
        }
        cache_key = _single_cache_key(theme_ko, bundle)
        if use_cache and cache_key in _SINGLE_CONFIRM_CACHE:
            cached = _SINGLE_CONFIRM_CACHE[cache_key]
            single_t = bool(cached.get("is_theme"))
            cache_hits += 1
            item["single_is_theme"] = single_t
            item["single_time_sec"] = 0.0
            item["judge_mode"] = "batch+single"
            item["is_theme"] = single_t
            if single_t:
                confirmed += 1
            print(f"[P3b SINGLE-CACHE] frag={item.get('fid')} hit")
            print(
                f"[P3b SINGLE-CONFIRM] frag={item.get('fid')} "
                f"batch=true -> single={'t' if single_t else 'f'} cached"
            )
            continue

        if use_cache:
            cache_misses += 1
            print(f"[P3b SINGLE-CACHE] frag={item.get('fid')} miss")

        single_t, elapsed, error = _judge_single_confirm(theme_ko, bundle)
        single_calls += 1
        total_time += elapsed
        item["single_is_theme"] = bool(single_t)
        item["single_time_sec"] = round(elapsed, 3)
        item["judge_mode"] = "batch+single"
        item["is_theme"] = bool(single_t)
        if single_t:
            confirmed += 1
        if error is not None:
            item["single_error"] = str(error)
            print(
                f"[P3b SINGLE-CONFIRM][WARN] frag={item.get('fid')} "
                f"batch=true -> single=f failed ({error}) time={elapsed:.2f}s"
            )
        elif use_cache:
            _SINGLE_CONFIRM_CACHE[cache_key] = {"is_theme": bool(single_t)}
        print(
            f"[P3b SINGLE-CONFIRM] frag={item.get('fid')} "
            f"batch=true -> single={'t' if single_t else 'f'} time={elapsed:.2f}s"
        )

    avg = (total_time / single_calls) if single_calls else 0.0
    if use_cache:
        print(
            f"[P3b JUDGE] mode=batch+single batch_keep={batch_keep} "
            f"confirmed={confirmed} single_calls={single_calls} "
            f"cache_hits={cache_hits} cache_misses={cache_misses} "
            f"single_time_total={total_time:.2f}s "
            f"single_time_avg={avg:.2f}s"
        )
    else:
        print(
            f"[P3b JUDGE] mode=batch+single batch_keep={batch_keep} "
            f"confirmed={confirmed} single_calls={single_calls} "
            f"single_time_total={total_time:.2f}s "
            f"single_time_avg={avg:.2f}s"
        )
    result = {
        "batch_keep": batch_keep,
        "confirmed": confirmed,
        "single_calls": single_calls,
        "single_time_total": total_time,
    }
    if use_cache:
        result["cache_hits"] = cache_hits
        result["cache_misses"] = cache_misses
    return result


def plan_edit(source_ids, instruction_text, batch=8, verbose=True,
              candidate_fragment_ids=None, rubric=None):
    """[P3a] 명령+조각풀 → 편집계획. 분해 파이프라인:
      1) extract_intent: 명령 → {keep,exclude,count} (분류만)
      2) judge_theme(테마): 클립별 keep/exclude (검증된 P1 판단)
      3) count: 모델이 아니라 결정론으로 그대로 전달(하류 P3b가 적용)
    내용조건 없으면 판단 0, 전체 유지.
    candidate_fragment_ids: [ARCHIVE P1] archive_query가 추린 후보 — 있으면 그
      조각들만 판정(비용 절감 + 교집합 조건 준수). 캐시 키는 pool_sig가 자연 분리.
    반환: {keep:[{fid,time,scene,why}], count:int|None, intent, reason}
    """
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    supplied_rubric = None
    if rubric and _rubric_enabled():
        try:
            from engine import edit_rubric as _edit_rubric
            supplied_rubric = _edit_rubric.EditRubric.from_qwen_json(
                rubric, raw_goal=instruction_text
            )
            _mentioned_count = _det_count(instruction_text or "")
            if supplied_rubric.count is not None:
                supplied_rubric.count = _mentioned_count
        except Exception as _rubric_err:
            supplied_rubric = None
            if verbose:
                print(f"[RUBRIC-1][WARN] supplied rubric rejected ({_rubric_err})")
    if supplied_rubric is not None:
        _rk = supplied_rubric.required_keep_terms()
        _rx = supplied_rubric.required_exclude_terms()
        intent = {"keep": (_rk[0] if _rk else None),
                  "exclude": (_rx[0] if _rx else None),
                  "count": supplied_rubric.count,
                  "keep_terms": list(_rk),
                  "exclude_terms": list(_rx),
                  "keep_clauses": [instruction_text] if _rk else []}
    else:
        intent = extract_intent(instruction_text)

    if verbose:
        print(f"[QWEN_ROUTE] route=hub_plan model={HUB_MODEL}")
        print(f"[HUB-PLAN] intent={intent}")

    # [#58 C1 승격] 절단위 극성은 extract_intent가 이미 반영 — 여기서는 참조만
    # (구 게이트 블록의 이중 파싱 제거). ledger keep-절 제한·plan 캐시 키가 소비.
    _compound = ({"keep_terms": intent.get("keep_terms") or [],
                  "exclude_terms": intent.get("exclude_terms") or [],
                  "keep_clauses": intent.get("keep_clauses") or []}
                 if (intent.get("keep_terms") or intent.get("exclude_terms")) else None)

    # [4b 번역층] 검색층 테마는 번역어(keep_query/exclude_query) 우선 —
    # 원문 keep/exclude는 intent에 불변 보존(조건 1). 판사 규칙 무접촉.
    if intent.get("keep"):
        theme = intent.get("keep_query") or intent["keep"]
    else:
        theme = intent.get("exclude_query") or intent.get("exclude")
    is_exclude = intent["exclude"] is not None and intent["keep"] is None

    # 조각풀은 두 분기 모두 필요 → 먼저 적재 (plan 캐시 키의 pool hash에도 사용)
    con = sqlite3.connect(DB_PATH)
    bundles = []
    fid_to_source = {}
    _source_context = _load_context_for_sources(con, source_ids)
    for sid in source_ids:
        _loaded = load_bundles(con, sid)
        _apply_context_to_bundles(_loaded, _source_context)
        bundles.extend(_loaded)
        for _b in _loaded:
            _fid = _b.get("fid")
            if _fid:
                fid_to_source[_fid] = sid
    con.close()
    if candidate_fragment_ids:
        _cand = set(candidate_fragment_ids)
        _before_n = len(bundles)
        bundles = [b for b in bundles if b["fid"] in _cand]
        if verbose:
            print(f"[HUB-PLAN] candidates={len(bundles)}/{_before_n} (archive filter)")

    # 내용조건 없음 → 판단 생략, 전체 유지 (count만 결정론)
    if not theme:
        keep = [{"fid": b["fid"], "time": f'{b["start"]}~{b["end"]}s',
                 "scene": b["scene"], "why": "내용조건 없음(전체)"} for b in bundles]
        return {"keep": keep, "count": intent["count"], "intent": intent,
                "reason": f"no content filter, keep all {len(keep)}"}

    _ledger_enabled = os.getenv("CCUT_LEDGER_KEEP") in ("1", "true", "True")
    # [C1] 복합 파서가 켜져 있으면 B0 ledger는 keep 절만 읽음 —
    # "셀카는 빼고 가족여행만" 에서 exclude 절의 단어가 노트 매칭되는 것 방지.
    _ledger_text = (" ".join(_compound["keep_clauses"])
                    if _compound and _compound["keep_clauses"]
                    else (instruction_text or ""))
    _ledger_person = None
    _ledger_tokens = {}
    _ledger_sig = None
    _ledger_meta = None
    if _ledger_enabled:
        if is_exclude:
            _ledger_sig = "exclude-skip"
        else:
            _ledger_person = resolve_person_name(_ledger_text)
            if _ledger_person:
                _ledger_sig = "person-skip"
            else:
                try:
                    from engine.narrative_ledger import source_note_tokens as _source_note_tokens
                    _ledger_tokens = _source_note_tokens(source_ids)
                    _ledger_sig_src = json.dumps(
                        {sid: sorted(list(toks)) for sid, toks in _ledger_tokens.items()},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    _ledger_sig = hashlib.sha256(_ledger_sig_src.encode("utf-8")).hexdigest()[:16]
                except Exception as _ledger_err:
                    _ledger_tokens = {}
                    _ledger_sig = "error"
                    if verbose:
                        print(f"[B0-LEDGER][WARN] token read failed ({_ledger_err})")

    # [R2-A 후속] 같은 요청 안에서 A안·B안이 plan_edit를 각각 호출 → batch judge 2배.
    # 판(plan) 수준 인메모리 캐시: 명령+소스+조각풀(sensor)+모델이 같으면 재계산 금지.
    # 단일판정 캐시와 동일하게 CCUT_SINGLE_CACHE로 가역, 실패/예외 결과는 저장하지 않음.
    _plan_cache_on = os.getenv("CCUT_SINGLE_CACHE") in ("1", "true", "True")
    _plan_key = None
    if _plan_cache_on:
        _pool_sig = hashlib.sha256(
            "|".join(sorted(f'{b["fid"]}:{_bundle_sensor_hash(b)}' for b in bundles)).encode("utf-8")
        ).hexdigest()[:16]
        _plan_key = (("prepass1", os.getenv("CCUT_TAG_PREPASS", "1")),
                     tuple(source_ids), theme, is_exclude, intent.get("count"),
                     _pool_sig, HUB_MODEL, _golden_state_sig(),
                     ("ledger", _ledger_sig,
                      hashlib.sha256(_ledger_text.encode("utf-8")).hexdigest()[:12])
                     if _ledger_enabled else None,
                      ("compound", tuple(_compound["keep_terms"]), tuple(_compound["exclude_terms"]))
                      if _compound else None,
                      ("rubric", hashlib.sha256(
                          json.dumps(supplied_rubric.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")
                      ).hexdigest()[:16]) if supplied_rubric is not None else None)
        _hit = _PLAN_CACHE.get(_plan_key)
        if _hit is not None:
            if verbose:
                print(f"[P3b PLAN-CACHE] hit keep={len(_hit.get('keep') or [])} ({_hit.get('reason')})")
            import copy as _copy
            return _copy.deepcopy(_hit)

    # 내용조건 있음 → 전체 조각을 '큰 배치'로 한 번에 판단(속도: 소스별 루프 제거)
    import time as _t
    _jbatch = int(os.getenv("CCUT_HUB_JUDGE_BATCH", "8"))
    _t0 = _t.time()
    # [QWEN-R1 R-a] 이중핵 정배선 — 명확(태그 정확 일치)=규칙 프리패스, 애매=판사.
    # keep·exclude 양분기 대칭: scene 태그 "(인물:테마)"/"(장소:테마)" 정확 일치 = is_theme 확정,
    # 판사는 태그 부재 조각만 심사. CCUT_TAG_PREPASS=0으로 가역(기본 ON).
    _prepass = []
    _rubric_prepass = []
    _rubric_hybrid_diag = None
    _judge_bundles = bundles
    if os.getenv("CCUT_TAG_PREPASS", "1") not in ("0", "false", "False"):
        _tag_re = re.compile(r"\((?:인물|장소):" + re.escape(theme) + r"\)")
        _prepass = [b for b in bundles if _tag_re.search(b.get("scene") or "")]
        if _prepass:
            _pre_fids = {b["fid"] for b in _prepass}
            _judge_bundles = [b for b in bundles if b["fid"] not in _pre_fids]
            if verbose:
                _mode = "exclude" if is_exclude else "keep"
                print(f"[R-a PREPASS] tag-exact {_mode}={len(_prepass)} judge_rest={len(_judge_bundles)}")
                if is_exclude:
                    # [§5] 규칙이 제외한 조각은 목록 원시로 남긴다 (조용한 제외 금지)
                    for _b in _prepass:
                        print(f"[R-a PREPASS] excluded {_b['fid']} (태그 정확 일치)")
    if supplied_rubric is not None and not is_exclude:
        _rubric_prepass, _judge_bundles = _rubric_keep_prepass(
            theme, _judge_bundles, verbose=verbose
        )
    judged = _judge_batch(theme, _judge_bundles, batch=_jbatch)
    if supplied_rubric is not None and not is_exclude:
        judged = _rubric_guard_abstract_judged(
            theme, judged, _judge_bundles, verbose=verbose
        )
    if verbose:
        print(f"[HUB-PLAN] judged {len(judged)}frags batch={_jbatch} "
              f"calls={(len(judged) + _jbatch - 1) // _jbatch} time={_t.time() - _t0:.1f}s")
    if is_exclude:
        # 프리패스 조각 = 테마 확정 → 제외(kept에 미포함). 잔여는 판사 판정대로.
        kept = [j for j in judged if not j["is_theme"]]
        tag = f"exclude '{theme}'"
    else:
        _confirm_keep_candidates_single(theme, judged, _judge_bundles)
        if supplied_rubric is not None:
            kept, _rubric_hybrid_diag = _rubric_hybrid_keep(
                theme,
                list(_prepass) + list(_rubric_prepass),
                judged,
                bundles,
                count=intent.get("count"),
                verbose=verbose,
            )
        else:
            kept = [{"fid": b["fid"], "time": f'{b["start"]}~{b["end"]}s', "scene": b["scene"],
                     "is_theme": True, "reason": "태그 정확 일치(규칙)"} for b in _prepass] \
                   + [j for j in judged if j["is_theme"]]
        tag = f"keep '{theme}'"
    if _ledger_enabled:
        if is_exclude:
            _ledger_meta = {"hit": [], "matched_tokens": [], "kept": 0, "skip": "exclude"}
            if verbose:
                print(
                    f"[B0-LEDGER] INPUT{{text={json.dumps(_ledger_text, ensure_ascii=False)}, "
                    f"sources={json.dumps(list(source_ids), ensure_ascii=False)}}} "
                    f"-> OUTPUT{{hit=[], judge_kept={len(kept)}, ledger_kept=0, total={len(kept)}}}"
                )
        elif _ledger_person:
            _person_label = _ledger_person.get("matched") or _ledger_person.get("canonical") or ""
            _ledger_meta = {"hit": [], "matched_tokens": [], "kept": 0, "skip": "person"}
            if verbose:
                print(f"[B0-LEDGER] SKIP person={_person_label} text={json.dumps(_ledger_text, ensure_ascii=False)}")
        else:
            hit_sources = sorted(
                sid for sid, toks in _ledger_tokens.items()
                if any(tok in _ledger_text for tok in toks)
            )
            matched_tokens = sorted({
                tok
                for sid in hit_sources
                for tok in (_ledger_tokens.get(sid) or set())
                if tok in _ledger_text
            }, key=lambda x: (-len(x), x))
            hit_set = set(hit_sources)
            kept_fids = {j.get("fid") for j in kept}
            ledger_kept = [
                j for j in judged
                if fid_to_source.get(j.get("fid")) in hit_set
                and j.get("fid") not in kept_fids
                and not j.get("batch_is_theme")
            ]
            for j in ledger_kept:
                if not j.get("reason"):
                    j["reason"] = "ledger_note_match"
            kept = kept + ledger_kept
            _ledger_meta = {
                "hit": hit_sources,
                "matched_tokens": matched_tokens,
                "kept": len(ledger_kept),
            }
            if verbose:
                print(
                    f"[B0-LEDGER] INPUT{{text={json.dumps(_ledger_text, ensure_ascii=False)}, "
                    f"sources={json.dumps(list(source_ids), ensure_ascii=False)}}} "
                    f"-> OUTPUT{{hit={json.dumps(hit_sources, ensure_ascii=False)}, "
                    f"judge_kept={len(kept_fids)}, ledger_kept={len(ledger_kept)}, total={len(kept)}}}"
                )
    keep = []
    _bundle_by_fid = {b.get("fid"): b for b in bundles}
    _decision_enabled = os.getenv("CCUT_QWEN_FRAGMENT_DECISION", "1") not in ("0", "false", "False")
    try:
        _decision_max = max(0, int(os.getenv("CCUT_FRAGMENT_DECISION_MAX", "3")))
    except Exception:
        _decision_max = 3
    _decision_count = 0
    for j in kept:
        _entry = {"fid": j["fid"], "time": j["time"], "scene": j["scene"],
                  "why": j.get("reason")}
        _bundle = _bundle_by_fid.get(j["fid"])
        if _bundle and _bundle.get("speech"):
            _entry["speech"] = _bundle.get("speech")
        if _decision_enabled and _decision_count < _decision_max and _bundle:
            _decision = _decide_fragment_name_meaning(
                theme,
                _bundle,
                project_context={"mode": "exclude" if is_exclude else "keep"},
            )
            if _decision:
                _entry["qwen_decision"] = _decision
                _decision_count += 1
        for _k in (
            "evidence_text",
            "rubric_evidence_hits",
            "rubric_bm25_score",
            "rubric_bm25_tokens",
            "rubric_rrf",
            "rubric_rrf_sources",
        ):
            if j.get(_k) is not None:
                _entry[_k] = j.get(_k)
        keep.append(_entry)

    # [RUBRIC-1, gate=CCUT_RUBRIC_ENABLED 기본 OFF] 복합조건 압축손실 보정.
    # 실측 병목: 위 theme/is_exclude 단일계(라인 ~1191, "theme = keep or exclude")는
    # keep과 exclude가 동시에 있어도 하나만 취하고 나머지를 완전히 버린다
    # ("먹방 빼고 실내만" -> theme=실내만 판정, exclude=먹방은 무시되어 실내+먹방 조각이
    # 그대로 살아남음). 기존 keep 파이프라인(위)은 전혀 안 건드리고, 그 결과 위에
    # exclude 조건으로 별도 판정해 위반 조각만 걸러내는 층을 얹는다. gate OFF면
    # rubric은 None이고 이 블록 전체가 no-op — 기존 keep 리스트 그대로 내려간다.
    rubric = None
    _rubric_excl_removed = 0
    _rubric_violations = []
    if _rubric_enabled():
        from engine import edit_rubric as _edit_rubric
        rubric = supplied_rubric or _edit_rubric.EditRubric.from_intent(intent, raw_goal=instruction_text)
        if rubric.is_compound() and not is_exclude:
            for _excl_theme in rubric.required_exclude_terms():
                _kept_fids = {k["fid"] for k in keep}
                _excl_pool = [b for b in bundles if b["fid"] in _kept_fids]
                if not _excl_pool:
                    continue
                _excl_judged = _judge_batch(_excl_theme, _excl_pool, batch=_jbatch)
                _excl_violate_fids = {j["fid"] for j in _excl_judged if j["is_theme"]}
                if _excl_violate_fids:
                    _rubric_excl_removed += len(_excl_violate_fids)
                    if verbose:
                        print(f"[RUBRIC-1] compound exclude 보정: keep-theme={theme!r} 대비 "
                              f"exclude={_excl_theme!r} 위반 {len(_excl_violate_fids)}건 제거")
                    keep = [k for k in keep if k["fid"] not in _excl_violate_fids]

    self_check = self_check_selection(
        theme, is_exclude, keep, judged=judged,
        judge_mode="batch+single" if not is_exclude else None,
    )
    if rubric is not None:
        # [RUBRIC-1] self_check가 압축 theme 대신 채점표를 보게 — required exclude
        # 위반이 (드물게) 여전히 남아있는지 최종 확인해 rubric_check로 별도 첨부.
        # 기존 self_check_selection 결과(위)는 수정하지 않고 나란히 붙인다.
        self_check["rubric_check"] = {
            "enabled": True,
            "is_compound": rubric.is_compound(),
            "compound_exclude_removed": _rubric_excl_removed,
            "required_exclude_terms": rubric.required_exclude_terms(),
            "required_keep_terms": rubric.required_keep_terms(),
            "remaining_violations": _rubric_violations,
            "status": "FAIL" if _rubric_violations else "PASS",
        }
    # [4b §5 고지] 번역이 실제 사용된 판이면 self_check에 실어 화면까지 흘린다(조건 2)
    if intent.get("translated"):
        self_check["translated"] = intent["translated"]
    _plan = {"keep": keep, "count": intent["count"], "intent": intent,
             "reason": f"{tag}: {len(keep)}/{len(judged)}",
             "self_check": self_check}
    if _ledger_meta is not None:
        _plan["ledger"] = _ledger_meta
    if _rubric_hybrid_diag is not None:
        _plan["rubric_retrieval"] = _rubric_hybrid_diag
    if rubric is not None:
        _plan["rubric"] = rubric.to_dict()
    if _plan_cache_on and _plan_key is not None:
        import copy as _copy
        if len(_PLAN_CACHE) >= 32:  # [AUDIT-⑽] 무제한 증식 방지 (FIFO)
            _PLAN_CACHE.pop(next(iter(_PLAN_CACHE)))
        _PLAN_CACHE[_plan_key] = _copy.deepcopy(_plan)
    return _plan


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode")

    pj = sub.add_parser("judge")  # P1: 테마 판정
    pj.add_argument("source_id")
    pj.add_argument("theme")
    pj.add_argument("--en", default=None)
    pj.add_argument("--batch", type=int, default=8)

    pp = sub.add_parser("plan")   # P3a: 편집계획
    pp.add_argument("source_ids", nargs="+")
    pp.add_argument("--cmd", required=True)
    pp.add_argument("--batch", type=int, default=16)

    args = ap.parse_args()

    if args.mode == "plan":
        print(f"[HUB-PLAN] model={HUB_MODEL} sources={len(args.source_ids)} cmd={args.cmd!r}")
        r = plan_edit(args.source_ids, args.cmd, batch=args.batch)
        print(f"\ncount={r['count']}  keep={len(r['keep'])}  ({r['reason']})")
        print(f"{'time':<16} {'scene':<46} why")
        print("-" * 100)
        for k in r["keep"]:
            print(f"{k['time']:<16} {str(k['scene'])[:46]:<46} {str(k['why'])[:30]}")
    else:
        # judge (P1 기존)
        print(f"[HUB] model={HUB_MODEL} source={args.source_id} theme={args.theme!r} "
              f"en={args.en!r} batch={args.batch}")
        res = judge_theme(args.source_id, args.theme, args.en, batch=args.batch)
        print(f"\n{'n':>2} {'is':>3} {'conf':>5} {'rechk':>5}  {'time':<14} {'label':<16} 근거")
        print("-" * 90)
        theme_n = 0
        recheck_n = 0
        for i, r in enumerate(res, 1):
            theme_n += 1 if r["is_theme"] else 0
            recheck_n += 1 if r["recheck"] else 0
            conf = r["confidence"]
            conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "  - "
            print(f"{i:>2} {'Y' if r['is_theme'] else '.':>3} {conf_s:>5} "
                  f"{'Y' if r['recheck'] else '.':>5}  {r['time']:<14} "
                  f"{str(r['scene'])[:16]:<16} {str(r['reason'])[:40]}")
        print("-" * 90)
        print(f"총 {len(res)}조각 | 테마판정 {theme_n} | 재분석요청 {recheck_n}")
