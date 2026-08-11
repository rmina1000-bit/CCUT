"""[GEMMA4 2026-08-11] 1단계 맞대결 — 여섯 점.

같은 24과제 · 같은 무대 · num_ctx 16384 통일 · seed 7 · temp 1 · top_p .95 · top_k 64.
축 A=on B=on D=full E=off 고정. 모델·양자화·도구층·정체성 넷을 분리한다.

조합마다 /night2/probe/axes 로 '의도한 축 == 실제'를 확인하고 다르면 무효.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

BACKEND = "D:/CCUT1.0.4/ccut_backend"
sys.path.insert(0, BACKEND)
sys.path.insert(0, BACKEND + "/scripts")
import night2_harness as H          # noqa: E402
import night2_grid as G             # noqa: E402

OUT = BACKEND + "/artifacts/night2"
LOGS = OUT + "/logs"
RESULTS = OUT + "/gemma4_six_results.jsonl"
PYTHON = G.PYTHON

G3 = "gemma3:4b"
G4 = "gemma4:e4b-it-qat"
UN = "hf.co/unsloth/gemma-4-e4b-it-qat-GGUF:UD-Q4_K_XL"

POINTS = [
    {"n": 1, "model": G3, "C": "json",  "V": "keep",  "tag": "p1_g3_json_keep"},
    {"n": 2, "model": G4, "C": "json",  "V": "keep",  "tag": "p2_g4_json_keep"},
    {"n": 3, "model": G4, "C": "tools", "V": "keep",  "tag": "p3_g4_tools_keep"},
    {"n": 4, "model": UN, "C": "json",  "V": "keep",  "tag": "p4_un_json_keep"},
    {"n": 5, "model": UN, "C": "tools", "V": "keep",  "tag": "p5_un_tools_keep"},
    {"n": 6, "model": UN, "C": "tools", "V": "hands", "tag": "p6_un_tools_hands"},
    {"n": 7, "model": UN, "C": "tools", "V": "bare",  "tag": "p7_un_tools_bare"},
]

FIXED = {
    "CCUT_NIGHT2_PROBE": "1",
    "CCUT_NIGHT2_NO_RENDER": "1",
    "CCUT_NIGHT2_NO_FALLBACK": "1",
    "CCUT_QWEN_TOOLS": "0",
    "CCUT_LLM_SEED": "7",
    "CCUT_LLM_TEMPERATURE": "1",
    "CCUT_LLM_TOP_P": "0.95",
    "CCUT_LLM_TOP_K": "64",
    "CCUT_NIGHT2_NUM_CTX": "16384",
    "CCUT_NIGHT2_THINK": "0",
    "CCUT_N2_AXIS_A": "on",
    "CCUT_N2_AXIS_B": "on",
    "CCUT_N2_AXIS_D": "full",
    "CCUT_N2_AXIS_H": "on",
}
WIPE = [k for k in ("CCUT_N2_AXIS_A", "CCUT_N2_AXIS_B", "CCUT_N2_AXIS_C",
                    "CCUT_N2_AXIS_D", "CCUT_N2_AXIS_H", "CCUT_N2_AXIS_V",
                    "CCUT_NIGHT2_SHADOW", "CCUT_NIGHT2_MODEL",
                    "CCUT_NIGHT2_THINK", "CCUT_NIGHT2_NUM_CTX",
                    "CCUT_LLM_SEED", "CCUT_LLM_TEMPERATURE",
                    "CCUT_LLM_TOP_P", "CCUT_LLM_TOP_K")]


def _p(*a):
    print(*a, flush=True)


def env_for(pt):
    e = dict(FIXED)
    e["CCUT_N2_AXIS_C"] = pt["C"]
    e["CCUT_N2_AXIS_V"] = pt["V"]
    e["CCUT_NIGHT2_MODEL"] = pt["model"]
    return e


def want_axes(pt):
    return {"A": "on", "B": "on", "C": pt["C"], "D": "full", "H": "on",
            "V": pt["V"], "shadow": False, "no_render": True,
            "no_fallback": True, "seed": "7", "temperature": "1",
            "top_p": "0.95", "top_k": "64",
            "model": pt["model"], "think": False, "num_ctx": 16384}


def start_backend(envset, logpath):
    env = dict(os.environ)
    for k in WIPE:
        env.pop(k, None)
    env.update(envset)
    os.makedirs(os.path.dirname(logpath), exist_ok=True)
    f = open(logpath, "a", encoding="utf-8", errors="replace", newline="")
    p = subprocess.Popen([PYTHON, "main.py"], cwd=BACKEND, env=env,
                         stdout=f, stderr=subprocess.STDOUT)
    return p, f


def ollama_stop(model):
    try:
        subprocess.run(["ollama", "stop", model], capture_output=True,
                       text=True, timeout=60, encoding="utf-8", errors="replace")
    except Exception as e:
        _p(f"  (ollama stop {model} 실패: {e})")


def warm(model, num_ctx=16384):
    """콜드 로드 비용을 과제 1번에 얹지 않는다 — 미리 한 번 깨운다."""
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "안녕"}],
                       "stream": False, "keep_alive": "30m",
                       "options": {"num_ctx": num_ctx, "num_predict": 8}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode())
        _p(f"  [warm] {model} {time.time()-t0:.1f}s load_ns={d.get('load_duration')}")
        return True
    except Exception as e:
        _p(f"  [warm] ★실패★ {type(e).__name__}: {e}")
        return False


def extra_metrics(rows):
    """지시서가 요구한 지표 중 H.summarize 에 없는 것들."""
    n_calls, n_frag, calls_hist = [], 0, {}
    desk_calls = []
    for r in rows:
        for rec in (r.get("recs") or []):
            purposes = [c.get("purpose") for c in (rec.get("llm_calls") or [])]
            desk_p = [p for p in purposes
                      if p in ("json", "xml", "free", "tools", "tools_both")]
            n_calls.append(len(desk_p))
            calls_hist["+".join(sorted(desk_p)) or "(0)"] = \
                calls_hist.get("+".join(sorted(desk_p)) or "(0)", 0) + 1
            m = rec.get("material") or {}
            if m.get("desk_llm_calls") is not None:
                desk_calls.append(m["desk_llm_calls"])
            for g in (rec.get("guards") or []):
                if g.get("guard") == "FRAGMENT-GROUND":
                    n_frag += 1
    return {"llm_calls_per_turn": (round(sum(n_calls) / len(n_calls), 2)
                                   if n_calls else None),
            "llm_calls_hist": calls_hist,
            "desk_llm_calls_mode": (max(set(desk_calls), key=desk_calls.count)
                                    if desk_calls else None),
            "fragment_ground_fired": n_frag}


def t09_verdict(trace):
    """T09(=T12 '좀 더 짧게') 판정 — 결의 말이 살아남았나 버려졌나."""
    if not trace:
        return {"verdict": "측정불능", "why": "trace 없음"}
    t = trace[0]
    raw = (t.get("gyeol_raw") or "").strip()
    screen = (t.get("screen") or "").strip()
    after = (t.get("say_after_guards") or "").strip()
    if not raw:
        return {"verdict": "측정불능", "why": "결 원본이 비었다", **t}
    if not screen:
        return {"verdict": "버려짐", "why": "화면에 나간 말 0자", **t}
    core = raw[:20]
    if core and core in screen:
        v = "살아남음"
    elif after and after[:20] in screen:
        v = "살아남음(검문 뒤)"
    else:
        v = "버려짐"
    return {"verdict": v, "why": f"raw {len(raw)}자 · 검문뒤 {len(after)}자 · 화면 {len(screen)}자",
            **t}


def run_point(pt, only=None):
    tag = pt["tag"]
    log = f"{LOGS}/{tag}.log"
    turns = f"{OUT}/turns_{tag}.jsonl"
    t0 = time.time()
    rec = {"point": pt["n"], "tag": tag, "model": pt["model"],
           "C": pt["C"], "V": pt["V"], "t_start": time.strftime("%F %T"),
           "log": log, "turns": turns}
    G.kill_backend()
    for m in (G3, G4, UN):
        if m != pt["model"]:
            ollama_stop(m)
    proc, fh = start_backend(env_for(pt), log)
    try:
        live = G.wait_ready(180)
        if not live:
            rec.update(valid=False, why="백엔드가 안 떴다")
            return rec
        actual = (live or {}).get("axes") or {}
        rec["axes_actual"] = actual
        want = want_axes(pt)
        bad = {k: [v, actual.get(k)] for k, v in want.items() if actual.get(k) != v}
        if bad:
            rec.update(valid=False, why=f"축 불일치 {bad}")
            return rec
        if not warm(pt["model"]):
            rec.update(valid=False, why="모델 예열 실패")
            return rec
        H.jsonl(turns)
        rows, el, base = H.run_tasks(only, meta_extra={"combo": tag}, verbose=True)
        s = H.summarize(rows)
        rec.update(valid=True, sec=round(time.time() - t0), tasks_sec=round(el),
                   **s, **extra_metrics(rows),
                   t09_verdict=t09_verdict(s.get("t09_trace")),
                   qwen=G.qwen_evidence(log))
        return rec
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=20)
        except Exception:
            G.kill_backend()
        try:
            fh.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", nargs="*", type=int, default=[1, 2, 3, 4, 5, 6])
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--no-restore", action="store_true")
    a = ap.parse_args()
    os.makedirs(LOGS, exist_ok=True)
    G.stop_supervisor()
    pts = [p for p in POINTS if p["n"] in a.points]
    _p(f"[여섯점] {len(pts)}점 · 과제 {len(a.only or H.TASKS)} · 결과 {RESULTS}")
    try:
        for pt in pts:
            _p(f"\n=== [{pt['n']}] {pt['tag']} model={pt['model']} "
               f"C={pt['C']} V={pt['V']} ===")
            try:
                r = run_point(pt, a.only)
            except Exception as e:
                import traceback
                traceback.print_exc()
                r = {"point": pt["n"], "tag": pt["tag"], "valid": False,
                     "why": f"러너 예외 {type(e).__name__}: {e}"}
            with open(RESULTS, "a", encoding="utf-8", newline="") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            _p(f"--- {r['tag']} valid={r.get('valid')} {r.get('why') or ''} "
               f"대상={r.get('target')} 되묻기={r.get('ask')} kind={r.get('kind_ok')} "
               f"검문={r.get('guard_ok')} deskNone={r.get('desk_none_count')} "
               f"호출/턴={r.get('llm_calls_per_turn')} "
               f"sec_med={r.get('sec_median')} tok={r.get('tok_median')} "
               f"T09={(r.get('t09_verdict') or {}).get('verdict')} {r.get('sec')}s")
    finally:
        if a.no_restore:
            _p("[여섯점] --no-restore — supervisor 안 살림")
        else:
            G.restore_supervisor()
    return 0


if __name__ == "__main__":
    sys.exit(main())
