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
    from engine import desk_hands as H
    return list(H._live_fids(P)[0])


def restore_to(want):
    from engine import desk_hands as H
    from engine.edit_propose import _approved_fids
    w = set(want)
    allf = _approved_fids(P)
    live = [f for f in allf if f in w]
    dead = [f for f in allf if f not in w]
    if live:
        H._mark(P, live, removed=False)
    if dead:
        H._mark(P, dead, removed=True)


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
    print(f"[NIGHT] {P} · 원고 {len(base)}조각 · 시나리오 {len(scen)}개 "
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
          f"· 원고 {len(H._live_fids(P)[0])}조각(시작 {len(base)}) → {OUT}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
