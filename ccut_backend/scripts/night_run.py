"""[NIGHT-1] 밤 — 가짜 사용자 무리를 결에게 풀어놓는다.

★실제 배선 그대로 돈다(POST /intent/route-edit/stream).
  프롬프트만 따로 시험하면 배관 결함을 못 잡는다 — 오늘 유령 명령과 500 이
  배관에서 나왔다.

시나리오마다 원고를 시작 상태로 되돌린다. 사용자가 바뀌면 세계도 처음이어야
다음 사람의 결과가 앞사람 때문에 흐려지지 않는다.
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "D:/CCUT1.0.4/ccut_backend")

URL = "http://127.0.0.1:8011/intent/route-edit/stream"
P = "proj_sim_night1"          # ★실 프로젝트 아님
SRC = ["SRC_88EACAB6"]
IN = "D:/CCUT1.0.4/ccut_backend/artifacts/night_scenarios.json"
OUT = "D:/CCUT1.0.4/ccut_backend/artifacts/night_turns.json"


def snapshot():
    """[NIGHT-2 2026-08-10] 시작 상태 전체를 찍는다 — 살아 있는 fid 목록만이 아니다.

    ★구판은 `list(_live_fids(P)[0])` 하나만 찍었다. 그래서 아래 restore_to 가
      되돌릴 수 있는 것도 removed 플래그 하나뿐이었다(정찰이 잡은 '원복 결손').
      trim·excluded_ranges·ui_state.story.fids·active_intent·chat_pref·
      chat_summary·message·export 대기는 앞 페르소나의 것이 다음 사람에게
      그대로 넘어갔다 — 그러면 '결이 이상한 소리를 한다'로 보이지만 원인은
      하네스다(이 파일이 어제 같은 병으로 한 번 고쳐졌다).
    """
    from scripts import night2_harness as N2
    return N2.state(P)


# ★[하네스 결함 수리 2026-08-09] 시나리오 경계에서 원고만 되돌리고 ★원장은
#   그대로 뒀다★ — 그래서 앞 페르소나가 남긴 Receipt(kind=hand_done)이 다음
#   페르소나의 세계에 그대로 살아 있었다. 다음 사람이 "방금 뭐 했어?" 라고
#   물으면 자기가 시킨 적 없는 편집 기록이 답으로 나온다(read_receipt 는
#   program_id 로만 읽는다). 장면 이름 수정(scene_label_fix)도 같은 병이다 —
#   앞사람이 "14번은 바닷가 바위야" 라고 고친 이름이 다음 사람의 지도에
#   그대로 남아 지도가 페르소나마다 달라진다.
#   ★측정판에서 이 누수는 '결이 이상한 소리를 한다' 로 보이지만 원인은 하네스다.
#   시뮬 프로젝트에서만 지운다(P 는 proj_sim_ 접두사 강제).
_LEAK_KINDS = ("hand_done", "scene_label_fix", "wish",
               "export_propose", "export_done")


def wipe_ledger():
    """페르소나 사이에서 앞사람의 흔적을 걷는다 — 시뮬 프로젝트 전용."""
    assert P.startswith("proj_sim"), f"거부: {P} 는 시뮬 프로젝트가 아니다"
    import sqlite3
    con = sqlite3.connect("D:/CCUT1.0.4/ccut_backend/ccut_app.db", timeout=30)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        q = ",".join("?" * len(_LEAK_KINDS))
        c = con.execute(
            f"DELETE FROM project_timeline WHERE program_id=? AND kind IN ({q})",
            (P, *_LEAK_KINDS))
        con.commit()
        return c.rowcount
    finally:
        con.close()


def restore_to(want):
    """[NIGHT-2] 완전 원복 — 찍어 둔 그대로 되돌리고, 같은지 스스로 확인한다.

    want 는 snapshot() 이 준 상태표다(구판의 fid 리스트가 아니다).
    되돌린 결과가 시작값과 다르면 그 사실을 조용히 넘기지 않는다 —
    시작이 다르면 그 뒤 숫자는 아무것도 증명하지 못한다.
    """
    from scripts import night2_harness as N2
    r = N2.restore(P, want, verbose=False)
    if not r["ok"]:
        print(f"    ★[경계] 원복 불일치 — 이 뒤 결과는 무효로 봐야 한다: {r['why']}",
              flush=True)
    elif r["wiped"]:
        print(f"    [경계] 앞사람 원장 {r['wiped']}행 걷음 · "
              f"_HANDED {r['handed']}", flush=True)
    return r


def turn(text, hist):
    body = {"project_id": P, "source_ids": SRC, "fragment_labels": {},
            "input_text": text, "recent_messages": hist[-8:]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
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
        err = f"{type(e).__name__}: {str(e)[:70]}"
    m = res.get("matched") or {}
    return {"reply": "".join(toks), "kind": m.get("kind") or ("ERROR" if err else "-"),
            "cap": m.get("cap") or "", "sec": round(time.time() - t0, 1), "err": err}


def main(limit=None):
    from engine import desk_hands as H
    scen = json.load(open(IN, encoding="utf-8"))
    if limit:
        scen = scen[:limit]
    base = snapshot()
    print(f"[NIGHT] {P} · 원고 {len(base['live'])}조각 · 시나리오 {len(scen)}개 "
          f"· {sum(len(s['turns']) for s in scen)}턴", flush=True)
    rows, t_start = [], time.time()
    for si, s in enumerate(scen, 1):
        hist = []
        for ti, u in enumerate(s["turns"], 1):
            before = len(H._live_fids(P)[0])
            r = turn(u, hist)
            after = len(H._live_fids(P)[0])
            hist.append({"sender": "user", "text": u})
            hist.append({"sender": "ai", "text": r["reply"]})
            rows.append({"sid": s["id"], "persona": s["persona"],
                         "source": s["source"], "t": ti, "text": u,
                         "reply": r["reply"], "kind": r["kind"], "cap": r["cap"],
                         "before": before, "after": after, "sec": r["sec"],
                         "err": r["err"]})
        restore_to(base)
        el = time.time() - t_start
        print(f"  [{si:3}/{len(scen)}] {s['persona'][:22]:22} {len(s['turns'])}턴 "
              f"· 누적 {len(rows)}턴 · {el/60:.1f}분", flush=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
    restore_to(base)
    print(f"[NIGHT] 끝. {len(rows)}턴 · {(time.time()-t_start)/60:.1f}분 "
          f"· 원고 {len(H._live_fids(P)[0])}조각(시작 {len(base['live'])}) → {OUT}",
          flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
