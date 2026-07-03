# -*- coding: utf-8 -*-
"""[DSPy 전 단계] 골든 케이스 러너 — 명령→편집 파이프라인 회귀 검증 + 케이스 축적.

용도:
  1) record: 실제 요청 1건을 실행하고 결과를 golden_cases/*.json 으로 저장
     (모든 검증 run이 자동으로 DSPy 학습 표본이 되게 하는 장치)
  2) run:    저장된 케이스 전부를 재실행해서 불변식 검사
     불변식(판정은 여기 고정):
       - A/B 시퀀스 ⊆ hub keep (명령 있는 경우)
       - keep=0 → A/B 빈 시퀀스 (honest-empty)
       - 명령 없는 경우 → keep 필터 미작동

사용:
  python tools/golden_runner.py record <project_id> "<instruction>" [--name NAME]
  python tools/golden_runner.py run
  python tools/golden_runner.py list

케이스 스키마 (golden_cases/NAME.json):
  {project_id, instruction, expect: {a_subset_keep, b_subset_keep, honest_empty|null,
   min_keep, max_keep}, recorded: {keep_n, pool_n, a_fids, b_fids, keep_fids}, ts}

주의: LLM judge는 비결정성이 있어 keep 수는 min/max 범위로 저장한다(±20%).
DSPy 도입 시 이 디렉토리가 그대로 trainset이 된다.
"""
import json
import os
import sqlite3
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "ccut_backend")
GOLDEN_DIR = os.path.join(ROOT, "golden_cases")
API = "http://127.0.0.1:8000"
sys.path.insert(0, BACKEND)


def _source_ids(project_id):
    db = sqlite3.connect(os.path.join(BACKEND, "ccut_app.db"))
    try:
        return [r[0] for r in db.execute(
            "SELECT source_id FROM project_sources WHERE program_id=? ORDER BY display_order",
            (project_id,))]
    finally:
        db.close()


def _request_proposals(project_id, source_ids, instruction):
    user_intent = {"target_length": 60.0}
    if instruction:
        user_intent["instruction_text"] = instruction
    payload = {"project_id": project_id, "source_ids": source_ids,
               "target_length": 60.0, "user_intent": user_intent, "refresh": True}
    req = urllib.request.Request(f"{API}/proposals/project",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    resp = json.load(urllib.request.urlopen(req, timeout=1800))
    props = {p.get("mode"): p for p in resp.get("proposals", [])}
    a = [f.get("fragment_id") for f in (props.get("A", {}).get("sequence") or [])]
    b = [f.get("fragment_id") for f in (props.get("B", {}).get("sequence") or [])]
    return a, b


def _hub_keep(source_ids, instruction):
    os.chdir(BACKEND)
    from engine import hub
    plan = hub.plan_edit(list(source_ids), instruction)
    keep = sorted({k.get("fid") for k in (plan.get("keep") or []) if k.get("fid")})
    return keep, plan


def cmd_record(project_id, instruction, name=None):
    sids = _source_ids(project_id)
    a, b = _request_proposals(project_id, sids, instruction)
    keep, plan = _hub_keep(sids, instruction) if instruction else ([], None)
    keep_n = len(keep)
    case = {
        "project_id": project_id,
        "instruction": instruction,
        "expect": {
            "a_subset_keep": bool(instruction),
            "b_subset_keep": bool(instruction),
            "honest_empty": (keep_n == 0) if instruction else None,
            "min_keep": max(0, int(keep_n * 0.8)),
            "max_keep": int(keep_n * 1.2) + 1,
        },
        "recorded": {"keep_n": keep_n, "a_fids": a, "b_fids": b,
                     "keep_fids": keep,
                     "intent": (plan or {}).get("intent")},
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    fname = name or f"{project_id}_{abs(hash(instruction)) % 10**8}"
    path = os.path.join(GOLDEN_DIR, f"{fname}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    print(f"[GOLDEN] recorded {path} keep={keep_n} A={len(a)} B={len(b)}")


def cmd_run():
    if not os.path.isdir(GOLDEN_DIR):
        print("[GOLDEN] no cases")
        return 0
    fails = 0
    for fn in sorted(os.listdir(GOLDEN_DIR)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(GOLDEN_DIR, fn), encoding="utf-8") as f:
            case = json.load(f)
        pid, instr = case["project_id"], case["instruction"]
        sids = _source_ids(pid)
        a, b = _request_proposals(pid, sids, instr)
        keep, _ = _hub_keep(sids, instr) if instr else ([], None)
        keep_set = set(keep)
        exp = case["expect"]
        errs = []
        if instr:
            if not exp["min_keep"] <= len(keep) <= exp["max_keep"]:
                errs.append(f"keep_n {len(keep)} not in [{exp['min_keep']},{exp['max_keep']}]")
            if exp["a_subset_keep"] and keep_set and not set(a) <= keep_set:
                errs.append(f"A not subset of keep: {sorted(set(a) - keep_set)}")
            if exp["b_subset_keep"] and keep_set and not set(b) <= keep_set:
                errs.append(f"B not subset of keep: {sorted(set(b) - keep_set)}")
            if exp.get("honest_empty") and (a or b):
                errs.append(f"honest-empty violated A={len(a)} B={len(b)}")
        verdict = "PASS" if not errs else "FAIL"
        fails += bool(errs)
        print(f"[GOLDEN] {verdict} {fn} keep={len(keep)} A={len(a)} B={len(b)}"
              + ("" if not errs else " | " + "; ".join(errs)))
    print(f"[GOLDEN] done fails={fails}")
    return 1 if fails else 0


def cmd_list():
    if not os.path.isdir(GOLDEN_DIR):
        print("[GOLDEN] no cases")
        return
    for fn in sorted(os.listdir(GOLDEN_DIR)):
        if fn.endswith(".json"):
            with open(os.path.join(GOLDEN_DIR, fn), encoding="utf-8") as f:
                c = json.load(f)
            print(f"{fn}: {c['project_id']} {c['instruction']!r} keep={c['recorded']['keep_n']}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"
    if mode == "record":
        name = None
        args = sys.argv[2:]
        if "--name" in args:
            i = args.index("--name")
            name = args[i + 1]
            args = args[:i] + args[i + 2:]
        cmd_record(args[0], args[1] if len(args) > 1 else "", name=name)
    elif mode == "run":
        sys.exit(cmd_run())
    else:
        cmd_list()
