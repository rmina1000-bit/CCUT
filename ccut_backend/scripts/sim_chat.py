"""[SIM-1] 사용자 발화 시뮬레이션 — CCUT 이 한숨이 아니라 숨을 쉬는가.

채점은 '어느 문으로 갔는가'가 아니라 '사용자가 원한 일이 일어났는가'다.
그래서 DB 전후를 함께 본다 — 대화인데 편집이 일어나면 그건 실패다.
"""
import json
import re
import sqlite3
import sys
import time
import urllib.request

BASE_URL = "http://127.0.0.1:8011/intent/route-edit/stream"
DB = "file:D:/CCUT1.0.4/ccut_backend/ccut_app.db?mode=ro"
PROG = "proj_ff8c890650e4"
SRC = ["SRC_88EACAB6"]

CASES = [
    ("안녕. 오늘 촬영 힘들었어.", "talk", False),
    ("아 피곤해..", "talk", False),
    ("고마워", "talk", False),
    ("지금 것도 괜찮은 것 같아", "talk", False),
    ("존댓말 해줄래?", "talk", False),
    ("이 영상에 뭐가 찍혔어?", "look", False),
    ("산에서 뭐 했어?", "look", False),
    ("고양이 나온 장면 있어?", "look", False),
    ("조각이 몇 개야?", "look", False),
    ("14번 산은 산이 아니고, 바닷가 바위야.", "fix", False),
    # 아직 안 고친 장면으로 (이미 고친 장면을 또 고치라 하면 "이미 그렇다"가 정답이다)
    ("7번 바다는 낚시하는 장면이야.", "fix", True),
    ("3번 장면 이름이 틀렸어. 요리하는 장면이야.", "fix", False),
    ("여기가 조금 늘어지는 것 같아", "edit", False),
    ("앞부분이 지루해", "edit", False),
    ("바다 나오는 건 좀 줄여줘", "edit", False),
    ("3번째 조각 빼줘", "edit", False),
    ("조각 10개로 맞춰줘", "edit", False),
    ("순서를 바꿔줘", "edit", False),
    ("자막을 넣어줘", "none", False),
    ("색깔 좀 따뜻하게 해줘", "none", False),
    ("배경음악 깔아줘", "none", False),
    ("편집이나 하자.", "ask", False),
    ("대충 해줘", "ask", False),
    ("이 편집버전을 보기좋게 편집해줘.", "edit", False),
    # ── [한계선 탐색] 실제 유튜버가 할 법한 어려운 말
    ("앞뒤가 좀 안 맞는 것 같아", "edit", False),
    ("여기서 말이 잘렸어", "edit", False),
    ("유튜브에 올릴 건데 8분 정도면 좋겠어", "edit", False),
    ("처음이랑 끝만 남기자", "edit", False),
    ("아까 뺀 거 다시 살려줘", "edit", False),
    ("이 부분 좀 어색한데", "edit", False),
    ("재미없어", "ask", False),
    ("낚시하는 데만 보여줘", "look", False),
    ("물속 장면이 제일 좋아", "talk", False),
    ("집에서 찍은 건 다 빼", "edit", False),
    ("이거 몇 분짜리야?", "look", False),
    ("음... 잘 모르겠다", "ask", False),
]

PRIOR = [
    {"sender": "user", "text": "14번 산은 산이 아니고, 바닷가 바위야."},
    {"sender": "ai", "text": "14번 장면을 바닷가 바위로 고쳤어요."},
]

CANT = re.compile(r"못|없|않|안 |불가|어려")
ASKING = re.compile(r"\?|알려주|말씀해|어떤|어느|무엇")
PHANTOM = re.compile(r"정은한")


def db_state():
    con = sqlite3.connect(DB, uri=True)
    n = con.execute("SELECT COUNT(*) FROM fragment_edit_state WHERE program_id=?",
                    (PROG,)).fetchone()[0]
    ev = con.execute("SELECT COUNT(*) FROM vault_events "
                     "WHERE event_kind='edit_command'").fetchone()[0]
    fx = con.execute("SELECT COUNT(*) FROM project_timeline "
                     "WHERE program_id=? AND kind='scene_label_fix'",
                     (PROG,)).fetchone()[0]
    con.close()
    return n, ev, fx


def route(text, with_prior):
    body = {"project_id": PROG, "source_ids": SRC,
            "recent_messages": PRIOR if with_prior else [],
            "input_text": text, "fragment_labels": {}}
    req = urllib.request.Request(BASE_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=200) as r:
        raw = r.read().decode("utf-8")
    final = {}
    for chunk in raw.split(chr(10) + chr(10)):
        chunk = chunk.strip()
        if chunk.startswith("data:"):
            ev = json.loads(chunk[5:])
            if ev.get("type") == "final":
                final = ev.get("result") or {}
    if final.get("stream_text"):
        final["reply"] = final["stream_text"]
    return time.time() - t0, final


def judge(want, reply, kind, edited, fixed):
    """사용자가 원한 일이 일어났는가."""
    r = reply or ""
    if want == "talk":
        # 편집이 일어나면 실패. 말이 있으면 성공.
        return (not edited) and bool(r.strip()), "편집 발생" if edited else ""
    if want == "look":
        return bool(r.strip()) and not edited, "편집 발생" if edited else ""
    if want == "fix":
        return fixed, "정정이 저장되지 않음"
    if want == "edit":
        # 제안이 왔거나(카드·초안) 기준을 받아 움직였으면 성공.
        moved = kind in {"living_draft", "boundary_trim_proposal", "gemma_breath",
                         "llm_edit", "open_theme", "vocab", "rubric_direct",
                         "cap_proposed", "draft_none", "count"} or edited
        return moved, "되묻기만 함" if not moved else ""
    if want == "none":
        # 못 한다고 말했고, 편집이 안 일어났으면 성공.
        return bool(CANT.search(r)) and not edited, (
            "편집 발생" if edited else "못 한다고 말하지 않음")
    if want == "ask":
        # 되물어도 좋다. 다만 절차를 돌리거나 편집하면 실패.
        return not edited, "편집 발생"
    return False, "?"


def run(label=""):
    hit = 0
    phantom = 0
    slow = 0
    rows = []
    for text, want, prior in CASES:
        b = db_state()
        try:
            el, resp = route(text, prior)
        except Exception as e:
            rows.append((text, want, "ERR", str(e)[:40], 0, False, ""))
            continue
        a = db_state()
        edited = (a[0], a[1]) != (b[0], b[1])
        fixed = a[2] != b[2]
        m = resp.get("matched") or {}
        kind = m.get("kind") or resp.get("action") or "-"
        reply = str(resp.get("reply") or "")
        good, why = judge(want, reply, kind, edited, fixed)
        if PHANTOM.search(reply):
            phantom += 1
        hit += good
        slow += (el > 12)
        rows.append((text, want, kind, reply[:58], el, good, why))
    n = len(CASES)
    print(f"\n{'=' * 66}")
    print(f"{label}   {hit}/{n}   유령이름 {phantom}건 · 12초초과 {slow}건")
    print(f"{'=' * 66}")
    for text, want, kind, reply, el, good, why in rows:
        print(f"  {'O' if good else 'X'} [{want:4}] {el:4.1f}s {text[:26]!r}")
        if not good:
            print(f"        {kind} · {why} · {reply}")
    return hit, n


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "SIM")
