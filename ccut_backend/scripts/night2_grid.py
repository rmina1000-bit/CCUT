"""[NIGHT-2 2026-08-10] 격자 러너 — 축을 껐다 켜며 24과제를 반복한다.

★이 파일은 ★턴으로 돌리는 물건이 아니다.★ detached 로 띄우고 자게 두는 물건이다.
  A(3) × B(3) × C(3) × D(3) × E(2) = 162조합 × 24과제(27턴).
  조합 하나 ≈ 재기동 25s + 27턴 × ~7.8s ≈ 235s → 전체 ≈ 10.6시간.

한 조합에서 하는 일(이 순서를 어기면 숫자가 오염된다):
  1) 백엔드 정지 → 그 조합의 env 로 다시 띄움 (env 는 프로세스 시작 때만 읽힌다)
  2) /night2/probe/axes 로 ★의도한 축 값과 실제가 같은지★ 확인
     — is_default 로는 못 본다. 격자에서는 어차피 기본이 아니다.
     — 다르면 그 조합 ★무효★. 재기동 실패나 오타를 데이터로 삼지 않는다.
  3) 24과제 실행 (매 과제 앞뒤로 완전 원복 + 자기점검)
  4) 원복 자기점검이 한 번이라도 깨졌으면 그 과제는 무효로 표시된다
  5) 결과 한 줄을 grid_results.jsonl 에 append + progress.json 갱신
     — ★중간에 죽어도 그때까지가 남는다.★ 마지막에 몰아 쓰지 않는다.

★밤이 끝나면 supervisor 를 되살린다 — finally 에 넣었고, 러너가 강제 종료돼도
  아래 한 줄이면 복구된다(보고서에도 적었다):
    powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File D:\\CCUT1.0.4\\run_backend_supervised.ps1

멈추는 법: artifacts/night2/STOP 파일을 만들면 지금 조합을 끝내고 정상 종료한다
  (supervisor 복구까지 하고 끝난다). 강제 kill 보다 이쪽이 안전하다.

쓰는 법:
  python scripts/night2_grid.py --cgate         C축 게이트 검증(json/xml/free × 3과제)
  python scripts/night2_grid.py --baseline      기준선 24과제(기본값)
  python scripts/night2_grid.py                 격자 162조합
  python scripts/night2_grid.py --limit 2       격자 앞 2조합만(연기 시험)
"""
import argparse
import itertools
import json
import os
import subprocess
import sys
import time
import urllib.request

BACKEND = "D:/CCUT1.0.4/ccut_backend"
ROOT = "D:/CCUT1.0.4"
sys.path.insert(0, BACKEND)
sys.path.insert(0, BACKEND + "/scripts")

import night2_harness as H                                   # noqa: E402

OUT = BACKEND + "/artifacts/night2"
LOGS = OUT + "/logs"
PROGRESS = OUT + "/progress.json"
RESULTS = OUT + "/grid_results.jsonl"
STOPFILE = OUT + "/STOP"
SUPERVISOR = ROOT + "/run_backend_supervised.ps1"
PYTHON = r"C:\Users\rmina\AppData\Local\Programs\Python\Python312\python.exe"
PORT = 8011

# 격자 축. H 는 여기 없다 — 국장 지시대로 별도 한 조합(도달 0건 음성 박제)이다.
AXES = {
    "A": ["on", "off", "full"],
    "B": ["on", "off", "user"],
    "C": ["json", "xml", "free"],
    "D": ["full", "short", "off"],
    "E": ["off", "on"],          # E = CCUT_NIGHT2_SHADOW
}

# 격자 내내 고정하는 것 — 이건 축이 아니라 ★밤의 조건★이다.
FIXED = {
    "CCUT_NIGHT2_PROBE": "1",        # 기록(동작 무변경). 이게 없으면 잴 게 없다.
    "CCUT_NIGHT2_NO_RENDER": "1",    # 밤중 렌더 차단(국장 지시)
    "CCUT_NIGHT2_NO_FALLBACK": "1",  # desk 무응답을 뒷사다리로 안 넘긴다
    "CCUT_LLM_SEED": "7",            # 결정론 — 축 말고는 안 달라지게
    "CCUT_QWEN_TOOLS": "0",          # 큐원 기동 금지(국장 지시)
}


def _p(*a):
    print(*a, flush=True)


# ── 백엔드 다루기 ──────────────────────────────────────────────────────
def _ps(script, timeout=60):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                           "-ExecutionPolicy", "Bypass", "-Command", script],
                          capture_output=True, text=True, timeout=timeout)


def stop_supervisor():
    """supervisor 를 끈다 — 안 끄면 우리가 죽인 백엔드를 3초 뒤 되살려서
    ★env 없는 백엔드★가 올라온다(그 조합의 숫자는 전부 거짓이 된다)."""
    r = _ps("Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | "
            "Where-Object { $_.CommandLine -like '*run_backend_supervised*' } | "
            "ForEach-Object { Write-Output $_.ProcessId; "
            "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    killed = [x for x in (r.stdout or "").split() if x.strip().isdigit()]
    _p(f"[격자] supervisor 정지: pid {killed or '없음'}")
    return killed


def restore_supervisor():
    """★밤의 마지막 의무.★ 실패해도 소리 내고 끝낸다(조용한 실패 금지)."""
    r = _ps("Start-Process powershell -ArgumentList "
            "'-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden',"
            f"'-File','{SUPERVISOR}'")
    time.sleep(6)
    up = wait_ready(60)
    _p(f"[격자] ★supervisor 복구★ rc={r.returncode} 백엔드={'OK' if up else '★안 뜸★'}")
    if not up:
        _p("[격자] ★수동 복구 필요★: powershell -ExecutionPolicy Bypass "
           f"-WindowStyle Hidden -File {SUPERVISOR}")
    return up


def kill_backend():
    _ps(f"Get-NetTCPConnection -LocalPort {PORT} -State Listen "
        "-ErrorAction SilentlyContinue | ForEach-Object { Stop-Process "
        "-Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }")
    for _ in range(40):
        if not _listening():
            return True
        time.sleep(0.5)
    return False


def _listening():
    r = _ps(f"if (Get-NetTCPConnection -LocalPort {PORT} -State Listen "
            "-ErrorAction SilentlyContinue) {'Y'} else {'N'}")
    return "Y" in (r.stdout or "")


def start_backend(envset, logpath):
    env = dict(os.environ)
    env.update(FIXED)
    env.update(envset)
    # 안 준 축은 ★키를 지운다★ — 앞 조합의 값이 남아 있으면 조용히 섞인다.
    for k in ("CCUT_N2_AXIS_A", "CCUT_N2_AXIS_B", "CCUT_N2_AXIS_C",
              "CCUT_N2_AXIS_D", "CCUT_N2_AXIS_H", "CCUT_NIGHT2_SHADOW"):
        if k not in envset:
            env.pop(k, None)
    os.makedirs(os.path.dirname(logpath), exist_ok=True)
    f = open(logpath, "a", encoding="utf-8", errors="replace", newline="")
    p = subprocess.Popen([PYTHON, "main.py"], cwd=BACKEND, env=env,
                         stdout=f, stderr=subprocess.STDOUT)
    return p, f


def wait_ready(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(H.API + "/night2/probe/axes", timeout=5) as r:
                if r.status == 200:
                    return json.loads(r.read().decode())
        except Exception:
            pass
        time.sleep(1)
    return None


# ── 조합 ──────────────────────────────────────────────────────────────
def env_for(combo):
    e = {"CCUT_N2_AXIS_A": combo["A"], "CCUT_N2_AXIS_B": combo["B"],
         "CCUT_N2_AXIS_C": combo["C"], "CCUT_N2_AXIS_D": combo["D"]}
    # ★C="unset" = env 키 자체를 안 준다(현행 보존 검증 전용). 코드가 기본값
    #   "json" 으로 가는지, 즉 C축 배선이 현행을 바꾸지 않았는지를 이걸로 잰다.
    if combo["C"] == "unset":
        e.pop("CCUT_N2_AXIS_C")
    if combo["E"] == "on":
        e["CCUT_NIGHT2_SHADOW"] = "1"
    if combo.get("H"):
        e["CCUT_N2_AXIS_H"] = combo["H"]
    return e


def axes_match(combo, live):
    """★의도한 축 값 == 실제★. is_default 로는 못 보는 것을 본다."""
    a = (live or {}).get("axes") or {}
    want = {"A": combo["A"], "B": combo["B"],
            "C": ("json" if combo["C"] == "unset" else combo["C"]),
            "D": combo["D"],
            "shadow": combo["E"] == "on", "H": combo.get("H", "on")}
    bad = {k: [v, a.get(k)] for k, v in want.items() if a.get(k) != v}
    return (not bad), bad, a


def combo_name(c):
    return f"A={c['A']}_B={c['B']}_C={c['C']}_D={c['D']}_E={c['E']}" + \
           (f"_H={c['H']}" if c.get("H") else "")


def qwen_evidence(logpath):
    """★큐원 0건 증거.★ ollama ps 로 지금 무엇이 떠 있는지 + 로그에서 qwen 몇 줄."""
    try:
        ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True,
                            timeout=20).stdout
    except Exception as e:
        ps = f"(ollama ps 실패: {e})"
    n = 0
    try:
        with open(logpath, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "qwen" in line.lower():
                    n += 1
    except Exception:
        n = -1
    return {"ollama_ps": ps.strip(), "log_qwen_lines": n,
            "gemma_only": ("qwen" not in ps.lower() and "gemma3:4b" in ps.lower())}


def write_progress(**kw):
    os.makedirs(OUT, exist_ok=True)
    try:
        with open(PROGRESS, "w", encoding="utf-8", newline="") as f:
            json.dump(kw, f, ensure_ascii=False, indent=1)
    except Exception as e:
        _p(f"[격자][WARN] progress 쓰기 실패: {e}")


def append_result(rec):
    os.makedirs(OUT, exist_ok=True)
    with open(RESULTS, "a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_combo(combo, only=None, turns_jsonl=None):
    """조합 하나. 반환은 grid_results.jsonl 에 그대로 들어갈 dict."""
    name = combo_name(combo)
    log = f"{LOGS}/{name}.log"
    t0 = time.time()
    rec = {"combo": combo, "name": name, "t_start": time.strftime("%F %T"),
           "log": log}
    kill_backend()
    proc, fh = start_backend(env_for(combo), log)
    try:
        live = wait_ready(150)
        if not live:
            rec.update(valid=False, why="백엔드가 안 떴다", sec=round(time.time() - t0))
            return rec
        ok, bad, actual = axes_match(combo, live)
        rec["axes_actual"] = actual
        if not ok:
            rec.update(valid=False, why=f"축 불일치 {bad}", sec=round(time.time() - t0))
            return rec
        if turns_jsonl:
            H.jsonl(turns_jsonl)
        rows, el, base = H.run_tasks(only, meta_extra={"combo": name}, verbose=True)
        s = H.summarize(rows)
        rec.update(valid=True, sec=round(time.time() - t0), tasks_sec=round(el),
                   qwen=qwen_evidence(log), **s)
        return rec
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=20)
        except Exception:
            kill_backend()
        try:
            fh.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true",
                    help="기준선 24과제 — 모든 축 기본값(is_default=true)")
    ap.add_argument("--cgate", action="store_true",
                    help="C축 게이트 검증 — json/xml/free × 지정 과제")
    ap.add_argument("--hcombo", action="store_true",
                    help="H축 별도 두 조합(on/off). ★NO_FALLBACK 을 끄고 돈다★ — "
                         "H 주입구(intent_router:200 · converse:318)가 둘 다 "
                         "★뒷사다리★에 있어서, 폴백을 끊으면 H 는 정의상 도달 0건이 "
                         "된다. 그러면 '도달 0'이 축의 성질인지 게이트 때문인지 "
                         "구별이 안 된다. 여기서만 폴백을 살려 진짜 도달을 잰다.")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip", type=int, default=0,
                    help="앞 N 조합 건너뛰기(중단 후 이어 돌 때)")
    ap.add_argument("--no-restore", action="store_true",
                    help="끝나도 supervisor 를 안 살린다(검증 중 연속 실행용)")
    a = ap.parse_args()

    os.makedirs(LOGS, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    turns = f"{OUT}/turns_grid_{stamp}.jsonl"
    stop_supervisor()

    if a.baseline:
        combos = [{"A": "on", "B": "on", "C": "json", "D": "full", "E": "off"}]
        # ★기준선은 밤의 조건도 안 건다 — '지금 CCUT 이 이렇다'의 기록이다.
        #   PROBE 만 켠다(기록은 동작을 안 바꾼다 — night2_probe 파일 머리 참조).
        FIXED.clear()
        FIXED["CCUT_NIGHT2_PROBE"] = "1"
    elif a.hcombo:
        combos = [{"A": "on", "B": "on", "C": "json", "D": "full", "E": "off",
                   "H": h} for h in ("on", "off")]
        FIXED.pop("CCUT_NIGHT2_NO_FALLBACK", None)
    elif a.cgate:
        # unset 을 앞에 둔다 — "C축 배선을 넣어도 현행이 그대로인가"가
        # 다른 무엇보다 먼저 통과해야 하는 관문이다.
        combos = [{"A": "on", "B": "on", "C": c, "D": "full", "E": "off"}
                  for c in ("unset", "json", "xml", "free")]
    else:
        combos = [dict(zip(AXES, v)) for v in itertools.product(*AXES.values())]

    combos = combos[a.skip:]
    if a.limit:
        combos = combos[:a.limit]

    _p(f"[격자] 조합 {len(combos)} · 과제 {len(a.only or H.TASKS)} · "
       f"결과 {RESULTS} · 진행 {PROGRESS}")
    done, t_all = 0, time.time()
    try:
        for i, c in enumerate(combos, 1):
            if os.path.exists(STOPFILE):
                _p("[격자] STOP 파일 감지 — 정상 종료한다")
                break
            write_progress(started=stamp, total=len(combos), done=done,
                           current=combo_name(c), i=i,
                           elapsed_s=round(time.time() - t_all),
                           eta_s=(round((time.time() - t_all) / done
                                        * (len(combos) - done)) if done else None),
                           results=RESULTS, turns=turns,
                           supervisor_restore=("powershell -ExecutionPolicy Bypass "
                                               f"-WindowStyle Hidden -File {SUPERVISOR}"))
            _p(f"\n=== [{i}/{len(combos)}] {combo_name(c)} ===")
            try:
                rec = run_combo(c, a.only, turns)
            except Exception as e:
                rec = {"combo": c, "name": combo_name(c), "valid": False,
                       "why": f"러너 예외 {type(e).__name__}: {e}"}
            append_result(rec)
            done += 1
            _p(f"--- {rec['name']} valid={rec.get('valid')} "
               f"{rec.get('why') or ''} 대상={rec.get('target')} "
               f"deskNone={rec.get('desk_none_count')} {rec.get('sec')}s")
        write_progress(started=stamp, total=len(combos), done=done,
                       current=None, finished=time.strftime("%F %T"),
                       elapsed_s=round(time.time() - t_all),
                       results=RESULTS, turns=turns)
    finally:
        if a.no_restore:
            _p("[격자] --no-restore — supervisor 를 살리지 않는다. "
               f"수동: powershell -ExecutionPolicy Bypass -WindowStyle Hidden "
               f"-File {SUPERVISOR}")
        else:
            restore_supervisor()
    _p(f"[격자] 끝 — {done}조합 {round(time.time() - t_all)}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
