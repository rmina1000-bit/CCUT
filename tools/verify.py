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
