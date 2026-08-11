"""
NIGHT-2 격자 분석기.  # [NIGHT-2]

입력  artifacts/night2/grid_results.jsonl  (조합마다 1행)
출력  1) 축별 주효과   2) 상호작용 후보(잔차 큰 것)   3) 상위/하위 5   4) T09 추적

★ 규율 (PREDICTIONS.md 에 사전 등록됨 — 결과를 보고 바꾸지 않는다)
   · 주효과의 합(가법 모형)으로 설명되지 않는 상위 조합은 "재현 대상"으로만 올리고
     결론에 넣지 않는다.
   · 잔차 |r| <= RESID_TOL(2과제) 이면 주효과로 설명된 것.
     그보다 크면 상호작용 후보 = 다중비교 산물일 수 있음.
   · 축별 값 차이도 1과제 이내면 무승부로 읽는다.

★ 이 분석기는 합성 데이터(--selftest)로만 검증했다. 격자 중간 결과로 다듬지 않았다.

사용
    python -X utf8 scripts/night2_analyze.py               # 실데이터
    python -X utf8 scripts/night2_analyze.py --selftest    # 합성 자기시험
"""

import io
import json
import os
import sys
from itertools import product

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(os.path.dirname(HERE), "artifacts", "night2")
RESULTS = os.path.join(ART, "grid_results.jsonl")

AXES = ["A", "B", "C", "D", "E"]
RESID_TOL = 2.0      # 과제 단위. 사전 등록값 — 결과를 보고 바꾸지 않는다.
TIE_TOL = 1.0        # 축별 값 차이가 이 이하면 무승부.

# (지표명, 추출함수, 클수록 좋은가)
METRICS = [
    ("대상정확도", lambda r: _num(r.get("target")), True),
    ("되묻기",     lambda r: _num(r.get("ask")), True),
    ("거짓약속없음", lambda r: _num(r.get("promise")), True),
    ("kind일치",   lambda r: _num(r.get("kind_ok")), True),
    ("검문도달",   lambda r: _num(r.get("guard_ok")), True),
    ("desk_none",  lambda r: r.get("desk_none_count"), False),
    ("지연med",    lambda r: r.get("sec_median"), False),
    ("프롬프트tok", lambda r: r.get("tok_median"), False),
]


def _num(v):
    """[맞은수, 전체] 또는 숫자를 맞은수로."""
    if isinstance(v, (list, tuple)) and v:
        return v[0]
    return v


def load(path):
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("valid") is False:
                continue          # 무효 조합은 통계에서 뺀다
            if not r.get("combo"):
                continue
            rows.append(r)
    return rows


def main_effects(rows, get):
    """축별 값별 평균. {axis: {value: (mean, n)}}"""
    out = {}
    for ax in AXES:
        buckets = {}
        for r in rows:
            v = r["combo"].get(ax)
            y = get(r)
            if v is None or y is None:
                continue
            buckets.setdefault(v, []).append(y)
        out[ax] = {v: (sum(ys) / len(ys), len(ys)) for v, ys in buckets.items() if ys}
    return out


def additive_predict(rows, get, eff, grand):
    """가법 모형: 전체평균 + Σ(축값평균 − 전체평균)"""
    pred = {}
    for r in rows:
        p = grand
        for ax in AXES:
            v = r["combo"].get(ax)
            if v in eff.get(ax, {}):
                p += eff[ax][v][0] - grand
        pred[r["name"]] = p
    return pred


def report(rows, baseline=None, t09=None):
    print("=" * 78)
    print(" NIGHT-2 격자 분석 — 유효 조합 %d개" % len(rows))
    print("=" * 78)

    for label, get, higher_better in METRICS:
        ys = [get(r) for r in rows if get(r) is not None]
        if not ys:
            continue
        grand = sum(ys) / len(ys)
        eff = main_effects(rows, get)

        print("\n■ %s   (전체평균 %.2f%s)" % (
            label, grand,
            "" if baseline is None or get(baseline) is None
            else " · 기준선 %.2f" % get(baseline)))

        for ax in AXES:
            vals = eff.get(ax) or {}
            if len(vals) < 2:
                continue
            items = sorted(vals.items(), key=lambda kv: -kv[1][0] if higher_better else kv[1][0])
            spread = max(m for m, _ in vals.values()) - min(m for m, _ in vals.values())
            tie = " ← 무승부(차 %.2f ≤ %.1f)" % (spread, TIE_TOL) if spread <= TIE_TOL else ""
            body = "  ".join("%s=%.2f(n%d)" % (v, m, n) for v, (m, n) in items)
            print("   %s  %s%s" % (ax, body, tie))

        # 잔차 — 다중비교 규율
        pred = additive_predict(rows, get, eff, grand)
        resid = []
        for r in rows:
            y = get(r)
            if y is None:
                continue
            resid.append((y - pred[r["name"]], y, r["name"]))
        resid.sort(key=lambda t: -abs(t[0]))
        big = [t for t in resid if abs(t[0]) > RESID_TOL]
        if big:
            print("   ★ 주효과로 설명 안 되는 조합 %d개 (|잔차| > %.1f) — **재현 대상, 결론 아님**"
                  % (len(big), RESID_TOL))
            for d, y, nm in big[:5]:
                print("      %-34s 실측 %.1f  잔차 %+.1f" % (nm, y, d))
        else:
            print("   잔차 최대 %+.2f — 전부 주효과로 설명됨" % (resid[0][0] if resid else 0))

    # 상위/하위 — 주지표(대상정확도)
    get = METRICS[0][1]
    ys = [get(r) for r in rows if get(r) is not None]
    if ys:
        grand = sum(ys) / len(ys)
        eff = main_effects(rows, get)
        pred = additive_predict(rows, get, eff, grand)
        ranked = sorted([r for r in rows if get(r) is not None], key=lambda r: -get(r))
        base_t = get(baseline) if baseline else None
        print("\n" + "=" * 78)
        print(" 대상정확도 상위 5 / 하위 5%s" % ("" if base_t is None else "  (기준선 %.0f)" % base_t))
        print("=" * 78)
        for tag, group in (("상위", ranked[:5]), ("하위", ranked[-5:])):
            for r in group:
                d = get(r) - pred[r["name"]]
                mark = "  ★재현대상(잔차 %+.1f)" % d if abs(d) > RESID_TOL else ""
                delta = "" if base_t is None else "  기준선 대비 %+.0f" % (get(r) - base_t)
                print(" %s %-34s %.0f%s%s" % (tag, r["name"], get(r), delta, mark))

    if t09 is not False:          # selftest 는 False 를 넘겨 실데이터를 안 건드린다
        t09_report()


T09_MARK = "좀 더 짧게"     # 국장이 지목한 자리. 과제 id 대신 발화로 찾는다(번호가 바뀌어도 산다).


def _newest_turns():
    cand = [f for f in os.listdir(ART) if f.startswith("turns_grid_") and f.endswith(".jsonl")]
    if not cand:
        return None
    cand.sort(key=lambda f: os.path.getmtime(os.path.join(ART, f)))
    return os.path.join(ART, cand[-1])


def t09_report(path=None):
    """★ 러너는 t09_trace 를 요약에 안 넣는다. 턴 원문에서 직접 뽑는다.
    (하네스 `material` 에 say_raw · tool_raw · say_after_guards 가 매 턴 남고,
     격자가 meta_extra={"combo": name} 을 붙여 조합과 이어진다.)"""
    path = path or _newest_turns()
    if not path or not os.path.exists(path):
        print("\n[T09] 턴 원문 파일 없음 — 추적 생략")
        return
    by_combo = {}
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if T09_MARK not in (r.get("user_text") or ""):
                continue
            m = r.get("material") or {}
            by_combo[r.get("combo") or "?"] = {
                "gyeol_raw": m.get("say_raw"),
                "screen": r.get("reply"),
                "tool_raw": m.get("tool_raw"),
                "kind": r.get("kind"), "cap": r.get("cap"),
                "guards": sorted({g.get("guard") for g in (r.get("guards") or [])
                                  if g.get("demoted")}),
            }
    if not by_combo:
        print("\n[T09] '%s' 턴을 못 찾음" % T09_MARK)
        return

    def verdict(t):
        """살아남음 / 버려짐 / 측정불능.

        ★측정불능이 따로 있어야 한다. desk 가 None 이면 no_fallback 게이트가
        화면 문장을 고정 문구로 갈아치운다 — 결의 말이 죽은 게 아니라 잴 수가 없다.
        이분법으로 세면 게이트 탓을 축 탓으로 오독한다."""
        if (t.get("kind") or "") == "desk_none":
            return "측정불능"
        s = (t.get("screen") or "").strip()
        if s.startswith("(NIGHT-2:"):
            return "측정불능"
        g = (t.get("gyeol_raw") or "").strip()
        if not g or not s:
            return "측정불능"
        return "살아남음" if (g in s or s in g) else "버려짐"

    v_of = {c: verdict(t) for c, t in by_combo.items()}
    ks = [c for c, v in v_of.items() if v == "살아남음"]
    lost = [c for c, v in v_of.items() if v == "버려짐"]
    nm_ = [c for c, v in v_of.items() if v == "측정불능"]

    print("\n" + "=" * 78)
    print(" T09 — '%s' : 결의 말이 화면까지 살아남는가 (조합 %d개)" % (T09_MARK, len(by_combo)))
    print("=" * 78)
    print(" 살아남음 %d · 버려짐 %d · ★측정불능 %d (desk None → 게이트가 화면을 갈아치움)"
          % (len(ks), len(lost), len(nm_)))
    if nm_:
        print(" ※ 측정불능은 분모에서 뺀다. 잴 수 있었던 %d개 중 살아남음 %d (%.0f%%)"
              % (len(ks) + len(lost), len(ks),
                 100.0 * len(ks) / max(1, len(ks) + len(lost))))

    # 축별 — 측정불능을 분모에서 빼고 센다
    for ax in AXES:
        buckets = {}
        for c, v in v_of.items():
            for part in c.split("_"):
                if part.startswith(ax + "="):
                    buckets.setdefault(part.split("=", 1)[1], []).append(v)
        if len(buckets) > 1:
            body = "  ".join(
                "%s=%d/%d%s" % (
                    val,
                    sum(1 for x in vs if x == "살아남음"),
                    sum(1 for x in vs if x != "측정불능"),
                    ("(불능%d)" % sum(1 for x in vs if x == "측정불능"))
                    if any(x == "측정불능" for x in vs) else "")
                for val, vs in sorted(buckets.items()))
            print("   %s  %s" % (ax, body))

    print("\n 살아남은 조합 원문 (최대 3):")
    for c in ks[:3]:
        t = by_combo[c]
        print("  [%s]  kind=%s cap=%s guards=%s" % (c, t["kind"], t["cap"], t["guards"]))
        print("    결 원본: %s" % (t["gyeol_raw"] or "(없음)"))
        print("    화면   : %s" % (t["screen"] or "(없음)"))
    print("\n 버려진 조합 원문 (최대 3):")
    for c in [c for c in by_combo if c not in ks][:3]:
        t = by_combo[c]
        print("  [%s]  kind=%s cap=%s guards=%s" % (c, t["kind"], t["cap"], t["guards"]))
        print("    결 원본: %s" % (t["gyeol_raw"] or "(없음)"))
        print("    화면   : %s" % (t["screen"] or "(없음)"))
        print("    도구   : %s" % str(t["tool_raw"])[:120])


def selftest():
    """합성 데이터로 분석기 자체를 검증한다. 실데이터 무접촉."""
    print("### 자기시험 — 심어 둔 효과를 되찾는가 (합성)\n")
    vals = {"A": ["off", "on", "full"], "B": ["off", "user", "on"],
            "C": ["json", "xml", "free"], "D": ["off", "short", "full"], "E": ["off", "on"]}
    # 심는 효과: B=user 가 +3, C=xml 이 −4, 나머지 0. 그리고 한 조합만 +6 튀게(가짜 상호작용)
    rows = []
    for a, b, c, d, e in product(*[vals[x] for x in AXES]):
        y = 14.0 + (3 if b == "user" else 0) + (-4 if c == "xml" else 0)
        name = "A=%s_B=%s_C=%s_D=%s_E=%s" % (a, b, c, d, e)
        if name == "A=on_B=off_C=free_D=short_E=on":
            y += 6                       # 우연히 튀는 조합 하나
        rows.append({"name": name, "combo": dict(zip(AXES, (a, b, c, d, e))),
                     "valid": True, "target": [y, 24], "ask": [3, 6], "promise": [0, 2],
                     "kind_ok": [1, 3], "guard_ok": [2, 3], "desk_none_count": 0,
                     "sec_median": 7.0, "tok_median": 3500})
    report(rows, t09=False, baseline={"target": [14, 24], "ask": [3, 6], "promise": [0, 2],
                           "kind_ok": [1, 3], "guard_ok": [2, 3], "desk_none_count": 0,
                           "sec_median": 7.0, "tok_median": 3500})
    print("\n기대: B=user 가 +3 로, C=xml 이 −4 로 잡히고,")
    print("      A=on_B=off_C=free_D=short_E=on 하나만 ★재현대상으로 걸려야 한다.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        if not os.path.exists(RESULTS):
            print("결과 파일 없음: %s" % RESULTS)
            sys.exit(1)
        rows = load(RESULTS)
        if not rows:
            print("유효 조합 0개")
            sys.exit(1)
        base = None
        bp = os.path.join(ART, "baseline_24.json")
        if os.path.exists(bp):
            try:
                base = json.load(io.open(bp, encoding="utf-8"))
            except Exception:
                base = None
        report(rows, base)
