# -*- coding: utf-8 -*-
"""CCUT 검증 오케스트레이터 — 4층 검증의 L0/L1/L2 실행기.

  L0 단위      LLM 없음, <5초. 결정론 함수만 (revision 파서/적용, intent 어휘,
               골든 단락, alias 매칭, honest-empty 시퀀스 규칙).
  L1 격리판정  golden_cases.json 전 케이스.
               invariant: 골든 단락(_golden_exact_verdict)이 gold를 정확 반환 (결정론 PASS/FAIL)
               drift:     LLM raw 판정과 gold의 일치율 (정보 제공용 — FAIL 없음, 추세 감시)
  L2 제품완주  tools/golden_runner.py run 위임 (백엔드 기동 + LLM 필요, 분 단위)

사용:
  python tools/verify.py L0 | L1 | L2 | all [--no-drift]
커밋 규칙: L0+L1 GREEN 없이 커밋 금지, L2 GREEN 없이 push 금지.
비결정성 원칙: LLM 경로는 불변식/범위로만 판정, 골든 단락 영역만 exact.
"""
import json
import os
import subprocess
import sys

# Windows 콘솔 cp949에서도 유니코드 출력 안전
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "ccut_backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

PASS, FAIL = "PASS", "FAIL"
_results = []


def check(layer, name, ok, detail=""):
    _results.append((layer, name, ok))
    print(f"[{layer}] {PASS if ok else FAIL} {name}" + (f" | {detail}" if detail else ""))
    return ok


# ─────────────────────────────────────────────────────────────── L0
def run_l0():
    os.environ["CCUT_REVISION"] = "1"
    import importlib
    from engine import revision as rev
    importlib.reload(rev)

    seq = [{"fragment_id": f"SF_{i}", "start": i * 10, "end": i * 10 + 5, "duration": 5}
           for i in range(5)]

    d = rev.detect_revision("마지막 조각 빼줘", True)
    check("L0", "rev.detect 마지막빼줘", d == {"op": "remove_ordinal", "index": -1}, str(d))
    s, _ = rev.apply_revision({"op": "remove_ordinal", "index": -1}, seq)
    check("L0", "rev.apply 마지막제거", [f["fragment_id"] for f in s] == ["SF_0", "SF_1", "SF_2", "SF_3"])

    d = rev.detect_revision("3개로 줄여줘", True)
    check("L0", "rev.detect 3개로", d == {"op": "set_count", "count": 3}, str(d))
    s, _ = rev.apply_revision({"op": "set_count", "count": 3}, seq)
    check("L0", "rev.apply set_count", len(s) == 3)
    s, _ = rev.apply_revision({"op": "set_count", "count": 40}, seq)
    check("L0", "rev.apply count>len 무해", len(s) == 5)
    s, _ = rev.apply_revision({"op": "remove_ordinal", "index": 9}, seq)
    check("L0", "rev.apply idx범위밖 no-op", len(s) == 5)

    check("L0", "rev.detect 신규지시는 None", rev.detect_revision("실내만", True) is None)
    check("L0", "rev.detect 제안없으면 None", rev.detect_revision("마지막 조각 빼줘", False) is None)
    os.environ["CCUT_REVISION"] = "0"
    importlib.reload(rev)
    check("L0", "rev 게이트 OFF → None", rev.detect_revision("마지막 조각 빼줘", True) is None)
    os.environ["CCUT_REVISION"] = "1"

    from engine import hub
    di = hub._deterministic_intent("실내만")
    check("L0", "intent 실내만", di["keep"] == "실내" and di["exclude"] is None)
    di = hub._deterministic_intent("실내 빼줘")
    check("L0", "intent 실내빼줘", di["exclude"] == "실내")
    di = hub._deterministic_intent("아이들만 편집해줘")
    check("L0", "intent 아이들만(person palette)", di["keep"] in ("아이", "아이들"), str(di))
    di = hub._deterministic_intent("조각 5개로")
    check("L0", "intent 5개", di["count"] == 5)

    check("L0", "alias 해변→beach",
          bool(hub._scene_alias_hits("beach with sand and waves", hub._aliases_for_theme("해변"))))
    check("L0", "alias 무관장면 미매칭",
          not hub._scene_alias_hits("office desk computer", hub._aliases_for_theme("해변")))

    # [INTENT-ROUTER] 종업원 결정론 사다리 — 지시 케이스 6종 (LLM off, vocab 주입 = DB 무관)
    from engine import intent_router as ir
    _pv = [("PER_TEST", "정은한", ["은한이"])]
    r = ir.route_edit_intent(input_text="은한이만 편집해줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 애칭→정규화 실행", r["action"] == "run_proposal" and "정은한" in (r["normalized_instruction"] or ""),
          f'{r["action"]}/{r["normalized_instruction"]}')
    r = ir.route_edit_intent(input_text="은한이 나오는 장면만 골라줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 애칭+나오는", r["action"] == "run_proposal" and "정은한" in (r["normalized_instruction"] or ""))
    r = ir.route_edit_intent(input_text="정은한만 편집해줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 풀네임", r["action"] == "run_proposal")
    r = ir.route_edit_intent(input_text="이 사람 나오는 것만", allow_llm=False, person_vocab=_pv)
    check("L0", "router 장면어휘(사람)", r["action"] == "run_proposal", r["action"])
    r = ir.route_edit_intent(input_text="B안에서 은한이 아닌 장면 빼줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 제외+애칭 정규화", r["action"] == "run_proposal" and "정은한" in (r["normalized_instruction"] or ""),
          f'{r["action"]}/{r["normalized_instruction"]}')
    r = ir.route_edit_intent(input_text="좀 더 감성적으로 해줘", allow_llm=False, person_vocab=_pv)
    check("L0", "router 모호→되묻기(llm off)", r["action"] == "ask_clarification", r["action"])
    r = ir.route_edit_intent(input_text="", allow_llm=False, person_vocab=_pv)
    check("L0", "router 빈입력→되묻기", r["action"] == "ask_clarification")

    # [ARCHIVE P1] 인물+장소 복합 filters — archive_lookup 주입으로 DB 무관
    def _fake_proj(filters, project_source_ids=None):
        return {"scope": "project", "fids": ["SF_X1", "SF_X2", "SF_X3"],
                "by_program": {}, "coverage": {"place_labeled": 90, "total": 100},
                "filter_counts": {}}

    def _fake_arch(filters, project_source_ids=None):
        return {"scope": "archive", "fids": ["SF_A1_SRC_F8AB3DCE"],
                "sources": ["SRC_F8AB3DCE"], "by_program": {"Alnilam": 3},
                "coverage": {"place_labeled": 90, "total": 100}, "filter_counts": {}}

    r = ir.route_edit_intent(input_text="병원 장면만", allow_llm=False, person_vocab=_pv)
    check("L0", "router 장소단독(병원)→det 어휘", r["action"] == "run_proposal", r["action"])
    r = ir.route_edit_intent(input_text="은한이가 병원에 있는 장면만", allow_llm=False,
                             person_vocab=_pv, archive_lookup=_fake_proj)
    check("L0", "router 인물+장소 교집합(project)",
          r["action"] == "run_proposal" and len(r.get("candidate_fragment_ids") or []) == 3
          and {f["type"] for f in r.get("filters") or []} == {"person", "place"},
          f'{r["action"]}/cand={len(r.get("candidate_fragment_ids") or [])}')
    r = ir.route_edit_intent(input_text="바다에서 정은한 나온 장면", allow_llm=False,
                             person_vocab=_pv, archive_lookup=_fake_proj)
    check("L0", "router 장소+인물 순서 무관", r["action"] == "run_proposal"
          and {f["type"] for f in r.get("filters") or []} == {"person", "place"})
    r = ir.route_edit_intent(input_text="은한이가 병원에 있는 장면만", allow_llm=False,
                             person_vocab=_pv, archive_lookup=_fake_arch)
    check("L0", "router 아카이브 히트→ask_include_archive",
          r["action"] == "ask_include_archive" and "Alnilam" in (r.get("reply") or ""),
          r["action"])
    # [ARCHIVE B] "응, 포함해줘" 승인 응답 → 원 지시 재해석 + 소스 포함 실행
    _msgs = [
        {"sender": "user", "text": "은한이가 병원에 있는 장면만 편집해줘"},
        {"sender": "ai", "text": "지금 프로젝트에는 정은한+병원 조각이 없고, "
                                 "아카이브에 있어요 (Alnilam 3개). 아카이브까지 포함할까요?"},
    ]
    r = ir.route_edit_intent(input_text="응, 포함해줘", recent_messages=_msgs,
                             allow_llm=False, person_vocab=_pv, archive_lookup=_fake_arch)
    check("L0", "router 포함승인→실행+소스",
          r["action"] == "run_proposal" and r.get("include_source_ids") == ["SRC_F8AB3DCE"]
          and "정은한이" in (r.get("normalized_instruction") or ""),
          f'{r["action"]}/src={r.get("include_source_ids")}/norm={r.get("normalized_instruction")}')
    r = ir.route_edit_intent(input_text="응", recent_messages=[],
                             allow_llm=False, person_vocab=_pv)
    check("L0", "router 맥락없는 긍정→오작동 없음", r["action"] != "run_proposal" or not r.get("include_source_ids"),
          r["action"])

    # [조사 교정] 단순 replace의 '정은한가' 문법 붕괴 수리 검증
    r = ir.route_edit_intent(input_text="은한이가 병원에 있는 장면만", allow_llm=False,
                             person_vocab=_pv, archive_lookup=_fake_proj)
    check("L0", "router 조사교정 가→이", (r.get("normalized_instruction") or "").startswith("정은한이 "),
          r.get("normalized_instruction"))
    check("L0", "router 조사교정 는→은",
          ir.replace_name("은한이는 어디 있어", "은한이", "정은한") == "정은한은 어디 있어",
          ir.replace_name("은한이는 어디 있어", "은한이", "정은한"))
    check("L0", "router 조사교정 를→을",
          ir.replace_name("은한이를 보여줘", "은한이", "정은한") == "정은한을 보여줘",
          ir.replace_name("은한이를 보여줘", "은한이", "정은한"))
    check("L0", "router 조사교정 무조사 무변",
          ir.replace_name("은한이 나오는 장면만", "은한이", "정은한") == "정은한 나오는 장면만",
          ir.replace_name("은한이 나오는 장면만", "은한이", "정은한"))

    # 골든 단락: 대소문/공백 정규화 포함 exact
    cases = hub._load_golden_cases()
    if cases:
        c0 = cases[0]
        v = hub._golden_exact_verdict(c0["theme"], "  " + c0["tags"].upper() + " ")
        check("L0", "골든 단락 정규화 일치", v == bool(c0["gold"]))
    check("L0", "골든 단락 비골든 None",
          hub._golden_exact_verdict("운동장", "totally unknown scene xyz") is None)


# ─────────────────────────────────────────────────────────────── L1
def run_l1(drift=True):
    from engine import hub
    cases = hub._load_golden_cases()
    check("L1", f"골든 케이스 로드 ({len(cases)}건)", len(cases) > 0)

    # invariant: 단락이 모든 골든에 gold를 정확 반환 (결정론)
    bad = [c for c in cases
           if hub._golden_exact_verdict(c["theme"], c["tags"]) != bool(c["gold"])]
    check("L1", "invariant: 골든 단락 exact 전건",
          not bad, "; ".join(c["tags"][:40] for c in bad))

    if not drift:
        return
    # drift: raw LLM 판정 vs gold 일치율 (정보용, FAIL 없음)
    agree = total = 0
    for c in cases:
        try:
            out = hub._ollama_json(hub._build_judge_lean(c["theme"], [{"fid": "x", "scene": c["tags"]}]))
            item = next((it for it in (out.get("items") or []) if int(it.get("n", 0) or 0) == 1), {})
            raw = bool(item.get("t"))
            total += 1
            agree += (raw == bool(c["gold"]))
            print(f"[L1-drift] {'ok ' if raw == bool(c['gold']) else 'DIFF'} theme={c['theme']} "
                  f"gold={c['gold']} raw={raw} | {c['tags'][:60]}")
        except Exception as e:
            print(f"[L1-drift] skip ({e})")
    if total:
        print(f"[L1-drift] LLM-gold 일치율 {agree}/{total} = {agree / total:.0%} "
              "(정보용 — 단락이 있어 제품 판정은 100% gold)")


# ─────────────────────────────────────────────────────────────── L2
def run_l2():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "golden_runner.py"), "run"])
    check("L2", "golden_runner run", r.returncode == 0)


def summary():
    fails = [(l, n) for l, n, ok in _results if not ok]
    print("\n=== VERIFY SUMMARY ===")
    for layer in ("L0", "L1", "L2"):
        rs = [ok for l, _, ok in _results if l == layer]
        if rs:
            print(f"{layer}: {sum(rs)}/{len(rs)} PASS")
    print("VERDICT:", "GREEN" if not fails else f"RED ({len(fails)} fail)")
    return 1 if fails else 0


if __name__ == "__main__":
    mode = (sys.argv[1] if len(sys.argv) > 1 else "L0").lower()
    drift = "--no-drift" not in sys.argv
    if mode in ("l0", "all"):
        run_l0()
    if mode in ("l1", "all"):
        run_l1(drift=drift)
    if mode in ("l2", "all"):
        run_l2()
    sys.exit(summary())
