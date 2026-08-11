"""[NIGHT-2 2026-08-10] 밤 실험 하네스 — 무대·완전 원복·턴 스냅샷·기계 채점.

왜 이게 필요한가: 배관은 GREEN 인데 실화면에서 결이 말을 못 알아듣는다.
맨몸 젬마는 잘한다. ★CCUT 안에서 더 못한다.★ 무엇이 실제로 큰지 숫자로 내려면
(1) 같은 자리에서 다시 시작할 수 있어야 하고 (2) 맞는 조각을 집었는지 기계가
가려야 한다. 둘 다 지금까지 없었다.

원복 결손(정찰 확정)과 이 파일의 처방:
  removed              night_run.restore_to 가 이미 되돌림
  trim_start/end_ms    ← _mark 이 trim=None("현재 값 유지")이라 안 돌아왔다
  excluded_ranges_json ← 같은 이유
  ui_state.story.fids  ← 아무도 안 되돌렸다(집합+순서)
  active_intent/chat_pref/chat_summary/message  ← 매 턴 프롬프트에 주입되는데
                       wipe_ledger 는 5종만 지웠다
  export 대기(export_propose)                   ← 같은 이유
  house_talk._HANDED   ← 프로세스 메모리. /night2/reset 으로 건드린다.

★그래서 이 파일은 '아는 것만 되돌리는' 대신 ★찍어 두고 그대로 되돌린다★ —
  fragment_edit_state 행 전체 + programs.ui_state 원문 + 그 시점의 max(entry_id).
  되돌린 뒤 _edit_state_fingerprint 가 시작값과 같은지 스스로 확인한다.
  다르면 그 조합은 무효다(측정하지 않는다).

★쓰기는 proj_sim 접두 프로젝트에만 한다 — 실 프로젝트(Poppy·Daffodil·
  Marigold·Clover)는 이 파일에서 SELECT 조차 하지 않는다(무대 만들 때만 읽는다).

쓰는 법:
  python scripts/night2_harness.py stage            무대 세우기(1회)
  python scripts/night2_harness.py restorecheck     원복 자기점검 실측
  python scripts/night2_harness.py seedcheck        결정론 증명(같은 입력 3회)
  python scripts/night2_harness.py baseline         기준선 12과제 실측
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request

BACKEND = "D:/CCUT1.0.4/ccut_backend"
sys.path.insert(0, BACKEND)

DB = BACKEND + "/ccut_app.db"
API = "http://127.0.0.1:8011"
STREAM = API + "/intent/route-edit/stream"
STAGE = "proj_sim_n2_a"
STAGE_FROM = "proj_ff8c890650e4"          # Marigold — ★읽기만★
SRC = ["SRC_88EACAB6"]
OUTDIR = BACKEND + "/artifacts/night2"

# 무대 모양(국장 조건: 가편집 있고 · 승인 ≠ 현재 · 조각 여럿)
#   Marigold 를 그대로 베끼지 않는다 — 실측해 보니 Marigold 는 ui 6 · removed 16
#   이라 ★살아 있는 조각이 1개★다. 순번을 말하는 과제("3번째 조각 빼줘")가
#   성립하지 않는 무대다. 모양(승인≠현재)은 따르고 수는 쓸 수 있게 세운다.
STAGE_UI_N = 10          # 승인 17 중 10개만 원고에 (승인 ≠ 현재)
STAGE_REMOVED = 2        # 그 중 2개는 이미 뺀 상태 (가편집 있음) → 살아 있는 8
STAGE_TRIM = (1, 3000)   # 살아 있는 2번째 조각 앞을 3초 잘라 둔다(원복 시험용)


def _con(write=False):
    if write:
        con = sqlite3.connect(DB, timeout=30)
    else:
        con = sqlite3.connect("file:" + DB + "?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _guard_sim(program_id):
    if not str(program_id).startswith("proj_sim"):
        raise SystemExit(f"거부: {program_id} 는 시뮬 프로젝트가 아니다 — 쓰기 금지")


def _h6(program_id):
    import ledger_r0
    return ledger_r0._hash6(program_id)


def _ui_fids(raw):
    if not raw:
        return []
    u = json.loads(raw)
    while isinstance(u, str):
        u = json.loads(u)
    return [str(f) for f in ((u.get("story") or {}).get("fids") or []) if f]


# ── 상태 ──────────────────────────────────────────────────────────────
def state(program_id):
    """지금 이 순간 전체. 되돌릴 때 쓰는 것과 채점할 때 쓰는 것이 같은 표다."""
    from engine import desk_hands as H
    con = _con()
    try:
        row = con.execute("SELECT ui_state FROM programs WHERE program_id=?",
                          (program_id,)).fetchone()
        ui_raw = row["ui_state"] if row else None
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM fragment_edit_state WHERE program_id=? "
            "ORDER BY timeline_item_id", (program_id,))]
        mx = con.execute("SELECT COALESCE(MAX(entry_id),0) FROM project_timeline "
                         "WHERE program_id=?", (program_id,)).fetchone()[0]
        # ★[원복 결손 2호 — 2026-08-10 실측으로 발견] 정찰 목록에 없던 자리다.
        #   내보내기 confirm 이 승인 관문(_reach_render_gate)에 닿으면 story_approval
        #   에 ★새 행★을 넣고 앞 행을 superseded 로 덮는다. 실측: 승인 17조각짜리
        #   행이 10조각짜리로 갈렸다. fp·ui·live 는 그대로라 자기점검이 못 잡았다 —
        #   world() 가 보는 '승인된 이야기'만 조용히 달라진다. 통째로 찍어 둔다.
        appr = [dict(r) for r in con.execute(
            "SELECT * FROM story_approval WHERE program_id=? ORDER BY approval_id",
            (program_id,))]
    finally:
        con.close()
    live, _ = H._live_fids(program_id)
    h6 = _h6(program_id)
    by_fid = {}
    for r in rows:
        item = r["timeline_item_id"]
        pre = f"ITEM_{h6}_"
        fid = item[len(pre):-2] if item.startswith(pre) and item.endswith("_0") else item
        by_fid[fid] = {"removed": int(r["removed"] or 0),
                       "trim_start_ms": r["trim_start_ms"],
                       "trim_end_ms": r["trim_end_ms"],
                       "anchor": [r["anchor_start_ms"], r["anchor_end_ms"]],
                       "excluded": json.loads(r["excluded_ranges_json"] or "[]")}
    return {"program_id": program_id, "ui_raw": ui_raw, "ui_fids": _ui_fids(ui_raw),
            "rows": rows, "max_entry": mx, "live": list(live),
            "by_fid": by_fid, "approvals": appr,
            "approved": _approved(appr),
            "fp": H._edit_state_fingerprint(program_id, live)}


def _approved(appr):
    """지금 살아 있는 승인 원고(superseded 안 된 마지막 행)의 조각 목록."""
    for r in reversed(appr):
        if r["superseded_by"] is None:
            try:
                return json.loads(r["fragment_ids"] or "[]")
            except Exception:
                return []
    return []


def _excl_total(ranges):
    return sum(int(b) - int(a) for a, b in (ranges or []))


def diff(before, after):
    """무엇이 바뀌었나 — 대상(fid)과 양(ms)을 따로 낸다."""
    fids = set(before["by_fid"]) | set(after["by_fid"])
    changed, trim_d, excl_d, new_rows = [], {}, {}, []
    for f in sorted(fids):
        a = after["by_fid"].get(f)
        b = before["by_fid"].get(f)
        # ★[측정 결함 수리 2026-08-10 · 1차 실측에서 잡힘] 조각을 ★빼기만★ 해도
        #   "시키지 않은 trim 1,282,000ms" 가 찍혔다. edit state 행이 그때 처음
        #   생기기 때문이다 — 없던 행을 trim 0 으로 읽으면 앵커 전체가 통째로
        #   trim 변화로 잡힌다. 없던 조각의 '편집 전 값'은 0 이 아니라 ★앵커★다.
        #   (이걸 안 고치면 밤 내내 양 정확도가 전부 X 로 나와 축을 못 가른다.)
        if b is None and a is not None:
            new_rows.append(f)
            b = {"removed": 0, "trim_start_ms": a["anchor"][0],
                 "trim_end_ms": a["anchor"][1], "anchor": a["anchor"],
                 "excluded": []}
        if a is None:
            a = {"removed": 0, "trim_start_ms": b["anchor"][0],
                 "trim_end_ms": b["anchor"][1], "anchor": b["anchor"],
                 "excluded": []}
        if b != a:
            changed.append(f)
        if (b["trim_start_ms"], b["trim_end_ms"]) != (a["trim_start_ms"], a["trim_end_ms"]):
            trim_d[f] = [(a["trim_start_ms"] or 0) - (b["trim_start_ms"] or 0),
                         (a["trim_end_ms"] or 0) - (b["trim_end_ms"] or 0)]
        if _excl_total(b["excluded"]) != _excl_total(a["excluded"]):
            excl_d[f] = _excl_total(a["excluded"]) - _excl_total(b["excluded"])
    if before["ui_fids"] != after["ui_fids"]:
        changed = sorted(set(changed) | (set(before["ui_fids"]) ^ set(after["ui_fids"])))
    return {"changed_fids": changed, "trim_delta_ms": trim_d,
            "excl_delta_ms": excl_d, "new_rows": new_rows,
            "ui_order_changed": before["ui_fids"] != after["ui_fids"],
            "live_before": before["live"], "live_after": after["live"],
            "fp_changed": before["fp"] != after["fp"]}


# ── 완전 원복 ─────────────────────────────────────────────────────────
def restore(program_id, base, verbose=True):
    """찍어 둔 그대로 되돌린다. 되돌린 뒤 스스로 확인한다.

    반환 {"ok": bool, "why": ...}. ok=False 인 조합은 ★무효 처리★한다 —
    시작이 다르면 그 뒤 숫자는 아무것도 증명하지 못한다.
    """
    _guard_sim(program_id)
    con = _con(write=True)
    try:
        con.execute("UPDATE programs SET ui_state=? WHERE program_id=?",
                    (base["ui_raw"], program_id))
        con.execute("DELETE FROM fragment_edit_state WHERE program_id=?", (program_id,))
        for r in base["rows"]:
            cols = ",".join(r.keys())
            qs = ",".join("?" * len(r))
            con.execute(f"INSERT INTO fragment_edit_state ({cols}) VALUES ({qs})",
                        tuple(r.values()))
        # ★원장은 kind 목록이 아니라 '기준선 이후 전부'를 걷는다. 목록으로 지우면
        #   나중에 kind 가 하나 늘 때마다 조용히 새기 시작한다(hand_done 사고와
        #   같은 모양). entry_id 는 단조 증가라 기준선 이후만 정확히 지워진다.
        c = con.execute("DELETE FROM project_timeline WHERE program_id=? AND entry_id>?",
                        (program_id, base["max_entry"]))
        # 승인 원고도 통째로 되돌린다(원복 결손 2호). 새 행을 지우는 것만으로는
        #   부족하다 — 앞 행의 superseded_by 가 이미 채워져 있다.
        con.execute("DELETE FROM story_approval WHERE program_id=?", (program_id,))
        for r in base["approvals"]:
            cols = ",".join(r.keys())
            qs = ",".join("?" * len(r))
            con.execute(f"INSERT INTO story_approval ({cols}) VALUES ({qs})",
                        tuple(r.values()))
        con.commit()
        wiped = c.rowcount
    finally:
        con.close()
    # 프로세스 메모리(house_talk._HANDED) — DB 로는 못 닿는다.
    handed = _reset_process(program_id)
    now = state(program_id)
    ok = (now["fp"] == base["fp"] and now["ui_fids"] == base["ui_fids"]
          and now["live"] == base["live"] and now["approved"] == base["approved"])
    why = ""
    if not ok:
        why = (f"fp {base['fp']}→{now['fp']} · "
               f"ui {len(base['ui_fids'])}→{len(now['ui_fids'])} · "
               f"live {len(base['live'])}→{len(now['live'])} · "
               f"승인 {len(base['approved'])}→{len(now['approved'])}")
    if verbose:
        print(f"  [원복] {'OK' if ok else '★불일치★'} fp={now['fp']} "
              f"live={len(now['live'])} 원장 {wiped}행 걷음 · _HANDED {handed}"
              + (f" — {why}" if why else ""), flush=True)
    return {"ok": ok, "why": why, "wiped": wiped, "handed": handed, "state": now}


def _reset_process(program_id):
    try:
        req = urllib.request.Request(
            API + "/night2/reset", data=json.dumps({"program_id": program_id}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())["handed_cleared"]
    except Exception as e:
        return f"실패({type(e).__name__})"


# ── 턴 ────────────────────────────────────────────────────────────────
def drain():
    try:
        with urllib.request.urlopen(API + "/night2/probe/drain", timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"enabled": False, "rows": [], "err": str(e)}


def axes():
    try:
        with urllib.request.urlopen(API + "/night2/probe/axes", timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"err": str(e)}


def turn(program_id, text, hist, labels):
    body = {"project_id": program_id, "source_ids": SRC,
            "fragment_labels": labels, "input_text": text,
            "recent_messages": hist[-8:]}
    req = urllib.request.Request(STREAM, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    toks, res, err = [], {}, ""
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            for line in r:
                s = line.decode("utf-8").strip()
                if s.startswith("data:"):
                    ev = json.loads(s[5:])
                    if ev.get("type") == "token":
                        toks.append(ev["text"])
                    if ev.get("type") == "final":
                        res = ev.get("result") or {}
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:80]}"
    m = res.get("matched") or {}
    return {"reply": "".join(toks) or str(res.get("reply") or ""),
            "kind": m.get("kind") or ("ERROR" if err else "-"),
            "cap": m.get("cap") or "", "args": m.get("args") or {},
            "sec": round(time.time() - t0, 1), "err": err}


_JSONL = None


def jsonl(path=None):
    global _JSONL
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _JSONL = path
    return _JSONL


def write_turn(rec):
    """append-only. 덮어쓰지 않는다 — 전 시도 보존(CLAUDE.md 증거 원칙)."""
    if not _JSONL:
        return
    with open(_JSONL, "a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_turn(program_id, text, hist, labels, meta):
    before = state(program_id)
    drain()                                    # 앞 턴 찌꺼기를 비운다
    r = turn(program_id, text, hist, labels)
    after = state(program_id)
    d = diff(before, after)
    probe = drain()
    rows = probe.get("rows") or []
    ptok = sum((x.get("prompt_eval_count") or 0) for x in rows if x["kind"] == "llm")
    rec = {**meta, "user_text": text,
           "before_fp": before["fp"], "after_fp": after["fp"],
           **d, "kind": r["kind"], "cap": r["cap"], "args": r["args"],
           "sec": r["sec"], "prompt_tokens": ptok, "err": r["err"],
           "reply": r["reply"],
           "guards": [{"guard": x["guard"], "demoted": x["demoted"],
                       "detail": x["detail"]} for x in rows if x["kind"] == "guard"],
           # ★[NIGHT-2] C축 지표 — desk 가 None 으로 떨어진 자리와 이유.
           "desk_none": [{"where": x.get("where"), "detail": x.get("detail")}
                         for x in rows if x["kind"] == "desk_none"],
           "material": next((x for x in rows if x["kind"] == "turn_material"), None),
           "llm_calls": [{"purpose": x.get("purpose"), "model": x.get("model"),
                          "prompt_chars": x.get("prompt_chars"),
                          "prompt_eval_count": x.get("prompt_eval_count")}
                         for x in rows if x["kind"] == "llm"],
           "axes": probe.get("axes"), "reach": probe.get("reach")}
    write_turn(rec)
    return rec, before, after


# ── 과제 12개 ─────────────────────────────────────────────────────────
#   정답 '최종 상태'를 미리 적어 두고 대화 뒤 DB 와 기계 비교한다(τ-bench 방식).
#   expect:
#     live   "L-2"        살아 있던 목록에서 인덱스 2 하나가 빠진 것
#            "L-last"     마지막 하나가 빠진 것
#            "count:5"    수만 맞으면 됨
#            "same"       무변
#     trim   (idx, ms)    그 조각 trim_start 가 ms 만큼 늘어난 것 (허용 ±2000)
#     kind   기대 kind(들). 되묻기 정답은 ★별도 채점★한다.
#     want_guard  이 검문들 중 ★하나라도★ 발동해야 정답(E축 도달 증명용)
#
# ★[NIGHT-2 2026-08-10] 12 → 24 로 늘렸다. 기준선 12과제에서 검문 10종 중
#   2종만 발동해 E축에 잴 것이 없었다 — 마지막 네 과제(N-군)가 그걸 살린다.
TASKS = [
    # ── 정상 5 ───────────────────────────────────────────────────
    {"id": "T01", "bucket": "정상", "turns": ["3번째 조각 빼줘"],
     "expect": {"live": "L-2"}},
    {"id": "T02", "bucket": "정상", "turns": ["마지막 조각 빼줘"],
     "expect": {"live": "L-last"}},
    {"id": "T03", "bucket": "정상", "turns": ["두 번째 조각 앞에서 2초 잘라줘"],
     "expect": {"live": "same", "trim": (1, 2000)}},
    {"id": "T04", "bucket": "정상", "turns": ["조각 5개로 맞춰줘"],
     "expect": {"live": "count:5"}},
    {"id": "T05", "bucket": "정상", "turns": ["a61 빼줘"],
     "expect": {"live": "label:A61"}},
    # ── 오타 5 ───────────────────────────────────────────────────
    {"id": "T06", "bucket": "오타", "turns": ["3번쨰 조각 빼줘"],
     "expect": {"live": "L-2"}},
    {"id": "T07", "bucket": "오타", "turns": ["두번쨰 조각 빼줘"],
     "expect": {"live": "L-1"}},
    {"id": "T08", "bucket": "오타", "turns": ["a60빼줘"],            # 흘려 쓴 라벨
     "expect": {"live": "label:A60"}},
    # ★a69 는 이 무대에 없다(라벨 A58~A65). 국장 지시서는 이걸 오타 칸에 뒀다 —
    #   그래서 정답을 "a59/a60 중 하나를 골라 지운다"로 두지 않는다. 무엇을
    #   가리켰는지 우리도 모르는 말이다. ★정답은 아무것도 안 지우고 되묻기★.
    #   (없는 라벨에 가장 가까운 것을 집어 지우는 것이 이 밤에서 제일 나쁜 답이다.)
    {"id": "T09", "bucket": "오타", "turns": ["a69 빼줘"],
     "expect": {"live": "same", "want_ask": True}},
    {"id": "T10", "bucket": "오타", "turns": ["마즈막 조각 빼주세여"],
     "expect": {"live": "L-last"}},
    # ── 흐린 것 5 — 정답은 ★되묻기★다. 실행해버리면 오답. ────────
    {"id": "T11", "bucket": "흐림", "turns": ["그거 말고 앞에꺼"],
     "expect": {"live": "same", "want_ask": True}},
    # ★T12 = 구 T09. 국장이 지목한 자리 — 결은 되물었는데 화면에서 지워졌다.
    #   조합마다 별도로 원문을 박제한다(t09_trace). 이름은 국장이 부른 대로 둔다.
    {"id": "T12", "bucket": "흐림", "turns": ["좀 더 짧게"], "trace": "t09",
     "expect": {"live": "same", "want_ask": True}},
    {"id": "T13", "bucket": "흐림", "turns": ["그럼 다시"],
     "expect": {"live": "same", "want_ask": True}},
    {"id": "T14", "bucket": "흐림", "turns": ["이 부분 좀 어색해"],
     "expect": {"live": "same", "want_ask": True}},
    {"id": "T15", "bucket": "흐림", "turns": ["적당히 정리해줘"],
     "expect": {"live": "same", "want_ask": True}},
    # ── 정정 3 — ★국장이 겪은 그 자리 ────────────────────────────
    #   정답 최종 상태 = '첫 턴에 잘못 지운 것은 돌아오고 고친 것만 빠진 것'.
    #   지금 CCUT 이 되돌리는지 아닌지를 이 세 칸이 숫자로 낸다.
    {"id": "T16", "bucket": "정정",
     "turns": ["두번째 조각 빼줘", "아니야, 두번째조각은 a60이야"],
     "expect": {"live": "label:A60"}},
    {"id": "T17", "bucket": "정정",
     "turns": ["3번째 조각 빼줘", "아 잘못 말했어. 4번째였어"],
     "expect": {"live": "L-3"}},
    {"id": "T18", "bucket": "정정",
     "turns": ["마지막 조각 빼줘", "아니 그거 말고 첫번째"],
     "expect": {"live": "L-0"}},
    # ── 못 하는 것 2 ─────────────────────────────────────────────
    {"id": "T19", "bucket": "못함", "turns": ["2배속으로 해줘"],
     "expect": {"live": "same", "want_kind": ["wish_noted", "not_here"],
                "no_false_promise": True}},
    {"id": "T20", "bucket": "못함", "turns": ["1080p로 뽑아줘"],
     "expect": {"live": "same", "want_kind": ["wish_noted", "not_here"],
                "no_false_promise": True}},
    # ── 검문 유발 4 (신설) — E축을 살리는 자리 ────────────────────
    #   기준선에서 검문 10종 중 2종만 발동했다. 나머지를 밟게 설계한 넷이다.
    #   전부 ★세상 무변★이 정답이다(검문이 막든, 결이 알아서 안 하든).
    {"id": "N1", "bucket": "검문", "turns": ["42번 장면 이름을 노을로 고쳐줘"],
     "expect": {"live": "same", "want_guard": ["SCENE-NO-GUARD"]}},
    {"id": "N2", "bucket": "검문", "turns": ["3번 장면 이름 좀 바꿔줘"],
     "expect": {"live": "same", "want_guard": ["LABEL-GROUND", "SCENE-GROUND/fix",
                                               "ASK-GUARD"]}},
    {"id": "N3", "bucket": "검문", "turns": ["두 번째 조각 앞에서 10분 잘라줘"],
     "expect": {"live": "same", "want_kind": ["hand_blocked"]}},
    {"id": "N4", "bucket": "검문", "turns": ["세 번째 장면은 몇 분에 나와?"],
     "expect": {"live": "same", "want_guard": ["TIME-GUARD", "ASK-GUARD"]}},
]

# 거짓약속 — night_score.py:24-28 을 출발점으로 삼되 ★넓혔다.★
#   [실측 2026-08-10] 기준선 T12 에서 결이 "CCUT이 2배속으로 설정했어요" 라고
#   ★완료형★으로 말했다. 미래형 목록(하겠습니다/할게요…)만 보던 채점기는 이걸
#   '약속 안 함'으로 통과시켰다 — 못 하는 일을 ★이미 했다고★ 말한 것이 더 나쁜데
#   더 낮은 점수가 안 나왔다. 완료형을 함께 본다.
#   ★night_score.py 와 값이 갈린다는 사실을 적어 둔다(조용한 변경 금지) —
#     밤 채점은 이 목록을 쓰고, night_score 쪽은 이 카드에서 건드리지 않았다.
_PROMISE = ("하겠습니다", "할게요", "해드릴게요", "설정하겠", "적용하겠",
            "바꾸겠습니다", "드릴게요", "진행하겠",
            "했어요", "했습니다", "됐어요", "되었습니다", "설정했", "적용했",
            "바꿨", "완료했")
_ASKING = ("?", "？", "어느", "어떤", "몇 번", "어디", "말씀해", "알려주")


def expected_live(exp, L, labels):
    kind = exp.get("live")
    if kind == "same":
        return list(L)
    if kind == "L-last":
        return L[:-1]
    if kind and kind.startswith("L-"):
        i = int(kind[2:])
        return [f for j, f in enumerate(L) if j != i]
    if kind and kind.startswith("count:"):
        return int(kind.split(":")[1])          # 수만 본다
    if kind and kind.startswith("label:"):
        fid = labels[kind.split(":")[1]]
        return [f for f in L if f != fid]
    return list(L)


def grade(task, recs, base_live, labels):
    """대상 정확도 · 양 정확도 · 되묻기 · 거짓약속 — 넷을 따로 낸다."""
    exp = task["expect"]
    last = recs[-1]
    live_after = last["live_after"]
    want = expected_live(exp, base_live, labels)
    if isinstance(want, int):
        target = "O" if len(live_after) == want else "X"
        want_txt = f"조각 {want}개"
    else:
        target = "O" if live_after == want else "X"
        want_txt = (f"{len(want)}조각" if want != base_live else "무변")
    # 양 — 명시된 분량이 있을 때만 잰다. 없으면 '0 이어야 한다'가 정답이다.
    amount, amt_txt = "-", ""
    tot_trim = sum(abs(a) + abs(b) for a, b in
                   (x for r in recs for x in r["trim_delta_ms"].values()))
    tot_excl = sum(abs(v) for r in recs for v in r["excl_delta_ms"].values())
    if exp.get("trim"):
        idx, ms = exp["trim"]
        fid = base_live[idx]
        got = 0
        for r in recs:
            d = r["trim_delta_ms"].get(fid)
            if d:
                got += d[0] - d[1]
        amount = "O" if abs(got - ms) <= 2000 else "X"
        amt_txt = f"{got}ms (기대 {ms}±2000)"
    elif tot_trim or tot_excl:
        amount = "X"                     # 분량 이야기가 없었는데 길이가 바뀌었다
        amt_txt = f"시키지 않은 trim {tot_trim}ms · excl {tot_excl}ms"
    reply = " ".join(r["reply"] for r in recs)
    asked = any(k in reply for k in _ASKING) or last["kind"] == "asked_not_done"
    ask = "-"
    if exp.get("want_ask"):
        ask = "O" if (asked and live_after == base_live) else "X"
    promise = "-"
    if exp.get("no_false_promise"):
        promise = "X" if any(p in reply for p in _PROMISE) else "O"
    kind_ok = "-"
    if exp.get("want_kind"):
        kind_ok = "O" if last["kind"] in exp["want_kind"] else "X"
    # ★[NIGHT-2] 검문 도달 — "방어는 존재가 아니라 도달로 증명한다"(CLAUDE.md).
    #   목록 중 하나라도 발동했으면 O. 발동한 것 전부를 함께 남긴다.
    fired = sorted({g["guard"] for r in recs for g in (r.get("guards") or [])})
    guard_ok = "-"
    if exp.get("want_guard"):
        guard_ok = "O" if any(w in fired for w in exp["want_guard"]) else "X"
    return {"target": target, "amount": amount, "amt_txt": amt_txt,
            "ask": ask, "promise": promise, "kind_ok": kind_ok,
            "guard_ok": guard_ok, "fired": fired,
            "want": want_txt, "got": f"{len(live_after)}조각"}


def desk_none_count(recs):
    """[NIGHT-2] C축 지표 — 이 과제에서 desk 가 몇 번 None 으로 떨어졌나.
    실패가 아니라 ★format tax 의 크기★다."""
    n = 0
    for r in recs or []:
        for row in (r.get("desk_none") or []):
            n += 1
        if r.get("kind") == "desk_none":
            n += 0        # 이미 위에서 센다(중복 방지)
    return n


def t09_trace(recs):
    """★국장이 지목한 자리 — '좀 더 짧게'.
    결 원본 / 화면에 나간 말 / 도구 머리 셋을 조합마다 원문 그대로 박제한다.
    (기준선: 결은 되물었는데 화면에는 다른 문장이 나갔고 도구는 분량을 지어냈다.)"""
    out = []
    for r in recs or []:
        m = r.get("material") or {}
        out.append({"user": r.get("user_text"),
                    "gyeol_raw": m.get("say_raw"),        # 결이 실제로 한 말
                    "screen": r.get("reply"),             # 화면에 나간 말
                    "tool_raw": m.get("tool_raw"),        # 도구 머리가 낸 것
                    "say_after_guards": m.get("say_after_guards"),
                    "kind": r.get("kind"), "cap": r.get("cap"),
                    "args": r.get("args"),
                    "fmt": m.get("fmt"), "say_hit": m.get("say_hit"),
                    "tool_hit": m.get("tool_hit"),
                    "guards": r.get("guards")})
    return out


# ── 무대 ──────────────────────────────────────────────────────────────
def build_stage():
    """가편집 있고 · 승인 ≠ 현재 · 조각 여럿. sim_project.create 는 ui_state 를
    복제하지 않으므로(:43-46) 원고는 여기서 따로 세운다."""
    _guard_sim(STAGE)
    sys.path.insert(0, BACKEND + "/scripts")
    import sim_project
    # create 는 programs 행만 지우고 다시 넣는다 — 앞선 무대의 edit state·원장이
    #   남으면 시작 상태가 조용히 달라진다. 먼저 통째로 걷는다(시뮬 전용 drop).
    sim_project.drop(STAGE)
    if not sim_project.create(STAGE_FROM, STAGE, "[SIM] NIGHT-2 기준선 무대"):
        raise SystemExit("무대 생성 실패")
    from engine.edit_propose import _approved_fids
    from engine import desk_hands as H
    ap = _approved_fids(STAGE)
    if len(ap) < STAGE_UI_N:
        raise SystemExit(f"승인 원고가 {len(ap)}조각 — 무대에 모자란다")
    ui = list(ap[:STAGE_UI_N])
    con = _con(write=True)
    try:
        row = con.execute("SELECT ui_state FROM programs WHERE program_id=?",
                          (STAGE,)).fetchone()
        u = json.loads(row["ui_state"]) if row["ui_state"] else {}
        while isinstance(u, str):
            u = json.loads(u)
        u["story"] = {"fids": ui}
        con.execute("UPDATE programs SET ui_state=? WHERE program_id=?",
                    (json.dumps(u, ensure_ascii=False), STAGE))
        con.commit()
    finally:
        con.close()
    # 가편집 — 이미 뺀 것 몇 개 + trim 하나. 손이 쓰는 계약 경로로 만든다.
    H._mark(STAGE, ui[-STAGE_REMOVED:], removed=True)
    live, _ = H._live_fids(STAGE)
    idx, ms = STAGE_TRIM
    from engine.edit_propose import _apply_state
    spans = H._fragment_spans([live[idx]])
    sid, s0, e0 = spans[live[idx]]
    _apply_state(STAGE, live[idx], sid, (s0, e0), (s0 + ms, e0), "TRIM",
                 before_state={"removed": False})
    st = state(STAGE)
    print(f"[무대] {STAGE} · 승인 {len(ap)} · 원고(ui) {len(st['ui_fids'])} · "
          f"살아 있는 {len(st['live'])} · fp={st['fp']}")
    print(f"  라벨: {json.dumps(stage_labels(st), ensure_ascii=False)}")
    return st


def stage_labels(st=None):
    """국장 화면 모양의 라벨(a58…) — 흘려 쓴 라벨 과제가 이걸 쓴다."""
    st = st or state(STAGE)
    return {f"A{58 + i}": f for i, f in enumerate(st["live"])}


# ── 실행 ──────────────────────────────────────────────────────────────
def cmd_restorecheck():
    base = state(STAGE)
    print(f"[시작] fp={base['fp']} ui={len(base['ui_fids'])} "
          f"live={len(base['live'])} 승인={len(base['approved'])}")
    labels = stage_labels(base)
    # 일부러 흩뜨린다 — 원복이 '아무것도 안 해서' 통과하는 것을 막는다.
    from engine import desk_hands as H
    from engine.edit_propose import _apply_state
    from engine import timeline_store as _ts
    H._mark(STAGE, base["live"][:2], removed=True)
    sp = H._fragment_spans([base["live"][3]])
    sid, s0, e0 = sp[base["live"][3]]
    _apply_state(STAGE, base["live"][3], sid, (s0, e0), (s0 + 5000, e0 - 4000),
                 "TRIM", before_state={"removed": False},
                 excluded_ranges=[[s0 + 9000, s0 + 11000]])
    con = _con(write=True)
    try:
        u = json.loads(con.execute("SELECT ui_state FROM programs WHERE program_id=?",
                                   (STAGE,)).fetchone()["ui_state"])
        while isinstance(u, str):
            u = json.loads(u)
        u["story"] = {"fids": list(reversed(base["ui_fids"]))[:-1]}   # 순서+집합 둘 다
        con.execute("UPDATE programs SET ui_state=? WHERE program_id=?",
                    (json.dumps(u, ensure_ascii=False), STAGE))
        con.commit()
    finally:
        con.close()
    for k, p in (("active_intent", {"instruction": "사람 중심으로"}),
                 ("chat_pref", {"count": 7}), ("chat_summary", {"summary": "앞사람 대화"}),
                 ("message", {"sender": "user", "text": "앞사람이 남긴 말"}),
                 ("export_propose", {"snapshot": "deadbeef", "fragment_count": 3})):
        _ts.append_entries(STAGE, [{"kind": k, "client_id": f"n2chk_{k}_{time.time()}",
                                    "ts": time.time() * 1000, "payload": p}])
    # 승인 원고도 흩뜨린다 — 내보내기 confirm 이 실제로 만드는 모양(새 행 +
    #   앞 행 superseded). 이게 없으면 원복 자기점검이 결손 2호를 못 잡는다.
    con = _con(write=True)
    try:
        # uq_story_approval_live = UNIQUE(program_id) WHERE superseded_by IS NULL —
        #   살아 있는 승인은 프로그램당 하나뿐이다. 먼저 비켜세우고 넣는다.
        old = con.execute("SELECT approval_id FROM story_approval WHERE program_id=? "
                          "AND superseded_by IS NULL", (STAGE,)).fetchone()
        if old:
            con.execute("UPDATE story_approval SET superseded_by=-1 WHERE approval_id=?",
                        (old["approval_id"],))
        cur = con.execute(
            "INSERT INTO story_approval (program_id, sequence_hash, mode, "
            " fragment_ids, item_count, running_ms, actor, approved_at, note) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (STAGE, "n2chk", None, json.dumps(base["approved"][:4]), 4, 0,
             "n2chk", time.strftime("%Y-%m-%dT%H:%M:%S"), "[N2] 원복 시험용"))
        if old:
            con.execute("UPDATE story_approval SET superseded_by=? WHERE approval_id=?",
                        (cur.lastrowid, old["approval_id"]))
        con.commit()
    finally:
        con.close()
    dirty = state(STAGE)
    con = _con()
    n_dirty = con.execute("SELECT COUNT(*) FROM project_timeline WHERE program_id=? "
                          "AND entry_id>?", (STAGE, base["max_entry"])).fetchone()[0]
    con.close()
    print(f"[흩뜨림] fp={dirty['fp']} ui={len(dirty['ui_fids'])} "
          f"live={len(dirty['live'])} 승인={len(dirty['approved'])} 원장 +{n_dirty}행 "
          f"(같은가? {dirty['fp'] == base['fp']})")
    r = restore(STAGE, base)
    print(f"[결과] {'PASS' if r['ok'] else 'FAIL'} {r['why']}")
    return 0 if r["ok"] else 1


def cmd_seedcheck(n=3):
    """seed 고정이 실제로 결정론을 만드는가 — 같은 입력 n 회가 바이트 동일한가."""
    base = state(STAGE)
    labels = stage_labels(base)
    text = "3번째 조각 빼줘"
    out = []
    for i in range(n):
        r = restore(STAGE, base, verbose=False)
        if not r["ok"]:
            print(f"  {i+1}회차 원복 실패 — 무효: {r['why']}")
            return 1
        rec, _, _ = run_turn(STAGE, text, [], labels,
                             {"task": "SEEDCHECK", "turn": i + 1})
        out.append(rec)
        print(f"  {i+1}회 kind={rec['kind']} cap={rec['cap']} "
              f"fp={rec['after_fp']} tok={rec['prompt_tokens']} "
              f"reply={rec['reply'][:60]!r}")
    restore(STAGE, base, verbose=False)
    same_reply = len({r["reply"] for r in out}) == 1
    same_fp = len({r["after_fp"] for r in out}) == 1
    same_cap = len({(r["cap"], json.dumps(r["args"], sort_keys=True)) for r in out}) == 1
    print(f"[결정론] 답 바이트동일 {same_reply} · 결과상태 동일 {same_fp} · "
          f"도구/인자 동일 {same_cap} · axes={out[-1]['axes']}")
    return 0 if (same_reply and same_fp and same_cap) else 1


def run_tasks(only=None, meta_extra=None, verbose=True):
    """24과제(또는 일부)를 한 번 돈다 — 기준선과 격자가 ★같은 함수★를 쓴다.

    두 벌로 쓰면 기준선과 격자가 조용히 다른 것을 재게 된다(전에 겪은 모양).
    반환: (rows, elapsed, base) — rows[i] 는 {task, recs, grade} 또는 {task, invalid}.
    """
    base = state(STAGE)
    labels = stage_labels(base)
    tasks = [t for t in TASKS if not only or t["id"] in only]
    rows, t0 = [], time.time()
    for t in tasks:
        r = restore(STAGE, base, verbose=False)
        if not r["ok"]:
            print(f"  {t['id']} 원복 실패 → ★무효★ {r['why']}", flush=True)
            rows.append({"task": t, "invalid": r["why"]})
            continue
        hist, recs = [], []
        for ti, u in enumerate(t["turns"], 1):
            rec, _, _ = run_turn(STAGE, u, hist, labels,
                                 {**(meta_extra or {}), "task": t["id"],
                                  "bucket": t["bucket"], "turn": ti})
            hist.append({"sender": "user", "text": u})
            hist.append({"sender": "ai", "text": rec["reply"]})
            recs.append(rec)
        g = grade(t, recs, base["live"], labels)
        dn = sum(len(x.get("desk_none") or []) for x in recs)
        rows.append({"task": t, "recs": recs, "grade": g, "desk_none": dn})
        if verbose:
            print(f"  {t['id']} [{t['bucket']}] 대상 {g['target']} 양 {g['amount']} "
                  f"되묻기 {g['ask']} 약속 {g['promise']} kind {g['kind_ok']} "
                  f"검문 {g['guard_ok']}{('(' + ','.join(g['fired']) + ')') if g['fired'] else ''} "
                  f"· {recs[-1]['kind']}/{recs[-1]['cap'] or '-'} "
                  f"· deskNone {dn} "
                  f"· {sum(r['sec'] for r in recs):.1f}s "
                  f"· tok {sum(r['prompt_tokens'] for r in recs)}", flush=True)
    restore(STAGE, base, verbose=False)
    return rows, time.time() - t0, base


def cmd_baseline(only=None, force=False):
    a = axes()
    print(f"[축] {json.dumps(a.get('axes'), ensure_ascii=False)} "
          f"· 기본값인가={a.get('is_default')}")
    if not a.get("is_default") and not force:
        print("★기준선은 기본값에서만 유효하다 — 축이 켜져 있다. 중단.")
        return 2
    base = state(STAGE)
    print(f"[무대] {STAGE} live={len(base['live'])} fp={base['fp']} "
          f"labels={sorted(stage_labels(base))}")
    rows, el, base = run_tasks(only)
    n_turn = sum(len(r.get("recs") or []) for r in rows)
    print(f"\n[끝] 과제 {len(rows)} · 턴 {n_turn} · {el:.0f}초 "
          f"({el/max(n_turn,1):.1f}s/턴) → {_JSONL}")
    _report(rows, el, n_turn)
    return 0


def summarize(rows):
    """조합 하나의 숫자 — 격자 JSONL 에 이 모양으로 한 줄씩 쌓인다."""
    ok = [r for r in rows if r.get("grade")]
    def _cnt(k, v="O"):
        return sum(1 for r in ok if r["grade"][k] == v)
    def _den(k):
        return sum(1 for r in ok if r["grade"][k] != "-")
    secs = sorted(x["sec"] for r in ok for x in r["recs"])
    toks = sorted(x["prompt_tokens"] for r in ok for x in r["recs"])
    fired = sorted({g for r in ok for g in r["grade"]["fired"]})
    return {
        # ★키 이름 주의: 격자 러너가 rec.update(valid=..., **summarize()) 로 편다.
        #   여기에 "valid" 를 두면 TypeError 로 조합 결과가 통째로 날아간다(실측).
        "tasks": len(rows), "valid_tasks": len(ok),
        "invalid": [r["task"]["id"] for r in rows if r.get("invalid")],
        "target": [_cnt("target"), _den("target")],
        "amount": [_cnt("amount"), _den("amount")],
        "ask": [_cnt("ask"), _den("ask")],
        "promise": [_cnt("promise"), _den("promise")],
        "kind_ok": [_cnt("kind_ok"), _den("kind_ok")],
        "guard_ok": [_cnt("guard_ok"), _den("guard_ok")],
        "guards_fired": fired,
        "desk_none_count": sum(r.get("desk_none") or 0 for r in rows),
        "sec_median": (secs[len(secs) // 2] if secs else None),
        "sec_max": (max(secs) if secs else None),
        "tok_median": (toks[len(toks) // 2] if toks else None),
        "per_task": {r["task"]["id"]:
                     ({"invalid": r["invalid"]} if r.get("invalid") else
                      {**{k: r["grade"][k] for k in
                          ("target", "amount", "ask", "promise", "kind_ok",
                           "guard_ok")},
                       "fired": r["grade"]["fired"],
                       "kind": r["recs"][-1]["kind"],
                       "cap": r["recs"][-1]["cap"],
                       "desk_none": r.get("desk_none") or 0,
                       "sec": round(sum(x["sec"] for x in r["recs"]), 1)})
                     for r in rows},
        "t09_trace": next((t09_trace(r["recs"]) for r in rows
                           if r["task"].get("trace") == "t09" and r.get("recs")),
                          None),
    }


def _report(rows, el, n_turn):
    print("\n과제 | 버킷 | 정답 | 실제 | 대상 | 양 | 되묻기 | 약속 | kind판정 | "
          "검문 | kind | deskNone | sec | tok")
    for r in rows:
        t = r["task"]
        if r.get("invalid"):
            print(f"{t['id']} | {t['bucket']} | — | 무효 | - | - | - | - | - | - | "
                  f"- | - | - | -")
            continue
        g, recs = r["grade"], r["recs"]
        print(f"{t['id']} | {t['bucket']} | {g['want']} | {g['got']} | "
              f"{g['target']} | {g['amount']}{(' ' + g['amt_txt']) if g['amt_txt'] else ''} | "
              f"{g['ask']} | {g['promise']} | {g['kind_ok']} | "
              f"{g['guard_ok']}{('=' + ','.join(g['fired'])) if g['fired'] else ''} | "
              f"{recs[-1]['kind']} | {r.get('desk_none') or 0} | "
              f"{sum(x['sec'] for x in recs):.1f} | "
              f"{sum(x['prompt_tokens'] for x in recs)}")
    ok = [r for r in rows if r.get("grade")]
    hit = sum(1 for r in ok if r["grade"]["target"] == "O")
    s = summarize(rows)
    print(f"\n대상 정확도 {hit}/{len(ok)} · 되묻기 {s['ask'][0]}/{s['ask'][1]} · "
          f"검문도달 {s['guard_ok'][0]}/{s['guard_ok'][1]} · "
          f"desk_none {s['desk_none_count']}")
    print(f"발동한 검문: {s['guards_fired'] or '없음'}")
    secs = [x["sec"] for r in ok for x in r["recs"]]
    toks = [x["prompt_tokens"] for r in ok for x in r["recs"]]
    if secs:
        secs_s = sorted(secs)
        print(f"턴 지연 median {secs_s[len(secs_s)//2]:.1f}s · "
              f"평균 {sum(secs)/len(secs):.1f}s · 최대 {max(secs):.1f}s")
        print(f"프롬프트 토큰 median {sorted(toks)[len(toks)//2]} · 최대 {max(toks)}")
        print(f"과제 1개 평균 {el/max(len(ok),1):.1f}초 · 턴/과제 {n_turn/max(len(ok),1):.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stage", "restorecheck", "seedcheck",
                                    "baseline", "state"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out", default=None)
    ap.add_argument("--force", action="store_true",
                    help="축이 기본값이 아니어도 돈다(격자 러너 전용)")
    a = ap.parse_args()
    jsonl(a.out or f"{OUTDIR}/turns_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    if a.cmd == "stage":
        build_stage()
    elif a.cmd == "state":
        s = state(STAGE)
        print(json.dumps({k: v for k, v in s.items() if k != "rows"},
                         ensure_ascii=False, indent=1))
    elif a.cmd == "restorecheck":
        sys.exit(cmd_restorecheck())
    elif a.cmd == "seedcheck":
        sys.exit(cmd_seedcheck())
    else:
        sys.exit(cmd_baseline(a.only, a.force))
