"""
GEMMA4-PROBE — 젬마 4 맨몸 시험. CCUT 무접촉.

ollama /api/chat 직통. CCUT 코드·DB 안 건드린다. 결과는 raw 로만 찍는다.
python -X utf8 gyeol_lab/probe_g4.py
"""
import hashlib
import json
import subprocess
import sys
import time
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OLLAMA = "http://127.0.0.1:11434"
G4 = "gemma4:e4b-it-qat"
G3 = "gemma3:4b"


def chat(model, messages, tools=None, options=None, think=None, timeout=600):
    body = {"model": model, "messages": messages, "stream": False}
    if tools:
        body["tools"] = tools
    if options:
        body["options"] = options
    if think is not None:
        body["think"] = think
    req = urllib.request.Request(
        OLLAMA + "/api/chat", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_err": str(e), "_sec": round(time.time() - t0, 1)}
    j["_sec"] = round(time.time() - t0, 1)
    return j


def ps():
    try:
        return subprocess.run(["ollama", "ps"], capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except Exception as e:
        return "ps 실패: %s" % e


def hr(t):
    print("\n" + "=" * 74)
    print(" " + t)
    print("=" * 74)


# ── 1. 첫 로드 · 공존 ────────────────────────────────────────────────
hr("1. 첫 로드 · gemma3:4b 와 공존하는가 (8GB)")
print("[before] ps:\n%s" % ps())

r = chat(G3, [{"role": "user", "content": "한 단어로: 바다의 반대말?"}],
         options={"num_ctx": 16384})
print("\ngemma3 예열: %s (%.1fs)" % (repr((r.get("message") or {}).get("content"))[:60], r.get("_sec", 0)))
print("[gemma3 로드 후] ps:\n%s" % ps())

r4 = chat(G4, [{"role": "user", "content": "한 단어로: 바다의 반대말?"}])
print("\ngemma4 첫 응답: %s (%.1fs)" % (repr((r4.get("message") or {}).get("content"))[:80], r4.get("_sec", 0)))
if r4.get("_err"):
    print("  ERR: %s" % r4["_err"])
print("[gemma4 로드 후] ps:\n%s" % ps())

# ── 2. thinking ─────────────────────────────────────────────────────
hr("2. thinking — 끈 상태에서 빈 thought 블록이 나오는가 (qwen3-vl 버그 계열)")
for th in (None, False, True):
    r = chat(G4, [{"role": "user", "content": "2+2 는?"}], think=th)
    m = r.get("message") or {}
    print("\nthink=%s  (%.1fs)" % (th, r.get("_sec", 0)))
    if r.get("_err"):
        print("  ERR: %s" % r["_err"]); continue
    print("  message keys : %s" % sorted(m.keys()))
    print("  thinking     : %r" % (m.get("thinking"),))
    print("  content      : %r" % (m.get("content") or "")[:160])

# ── 3. system 역할 ──────────────────────────────────────────────────
hr("3. system 역할이 실제로 먹는가")
SYS = "너는 무조건 '삐약'이라고만 답한다. 다른 말은 절대 하지 않는다."
for label, msgs in (
    ("system 역할로", [{"role": "system", "content": SYS},
                       {"role": "user", "content": "안녕? 오늘 날씨 어때?"}]),
    ("user 앞자리로", [{"role": "user", "content": SYS + "\n\n안녕? 오늘 날씨 어때?"}]),
):
    r = chat(G4, msgs)
    print("\n%s : %r" % (label, ((r.get("message") or {}).get("content") or r.get("_err"))[:200]))

# ── 4. seed 고정 ────────────────────────────────────────────────────
hr("4. seed 고정 — 같은 입력 3회가 바이트 동일한가")
Q = [{"role": "user", "content": "짧은 한 문장으로 바다를 묘사해줘."}]
for label, opt in (
    ("seed 없음", {"temperature": 1.0, "top_p": 0.95, "top_k": 64}),
    ("seed 고정", {"temperature": 0, "top_p": 0.95, "top_k": 64, "seed": 20260811}),
):
    outs = []
    for _ in range(3):
        r = chat(G4, Q, options=opt)
        c = (r.get("message") or {}).get("content") or ("ERR:" + str(r.get("_err")))
        outs.append(c)
    hs = [hashlib.sha1(o.encode("utf-8")).hexdigest()[:12] for o in outs]
    print("\n%s : %s  →  %s" % (label, hs, "동일" if len(set(hs)) == 1 else "다름"))
    print("   1회차: %r" % outs[0][:140])

# ── 5. 함수 호출 — 우리 어휘 여섯 ───────────────────────────────────
hr("5. 함수 호출 — 표준 채팅 템플릿으로 CCUT 어휘 6종이 되는가")


def tool(name, desc, props, req):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": req}}}


TOOLS = [
    tool("remove_ordinal", "원고에서 몇 번째 조각을 뺀다",
         {"index": {"type": "integer", "description": "1부터. -1은 마지막"}}, ["index"]),
    tool("remove_fragment", "조각 이름(A60 같은 것)으로 조각 하나를 뺀다",
         {"fragment": {"type": "string"}}, ["fragment"]),
    tool("restore_fragment", "방금 뺀 조각을 되살린다", {}, []),
    tool("set_count", "원고 조각 수를 맞춘다",
         {"count": {"type": "integer"}}, ["count"]),
    tool("trim_boundary", "조각의 앞이나 뒤를 말한 만큼 다듬는다",
         {"fragment": {"type": "string"}, "side": {"type": "string", "enum": ["start", "end"]},
          "amount_ms": {"type": "integer"}}, ["fragment", "side", "amount_ms"]),
    tool("exclude_range", "조각 가운데 한 구간을 도려낸다",
         {"fragment": {"type": "string"}, "start_ms": {"type": "integer"},
          "end_ms": {"type": "integer"}}, ["fragment", "start_ms", "end_ms"]),
]

CASES = [
    ("3번째 조각 빼줘", "remove_ordinal"),
    ("A60 빼줘", "remove_fragment"),
    ("방금 뺀 거 다시 살려줘", "restore_fragment"),
    ("조각 5개로 맞춰줘", "set_count"),
    ("2번째 조각 앞 2초 잘라줘", "trim_boundary"),
    ("2번째 조각 가운데 2초 빼줘", "exclude_range"),
    ("3번쨰 조각 빼줘", "remove_ordinal"),      # 오타
    ("좀 더 짧게", "(되묻기)"),                  # 도구 없음이 정답
    ("2배속으로 해줘", "(없는 일)"),             # 도구 없음이 정답
]

hit = 0
for text, want in CASES:
    r = chat(G4, [{"role": "user", "content": text}], tools=TOOLS)
    m = r.get("message") or {}
    calls = m.get("tool_calls") or []
    got = [c.get("function", {}).get("name") for c in calls]
    args = [c.get("function", {}).get("arguments") for c in calls]
    ok = (want in got) if want.startswith(("r", "s", "t", "e")) else (not got)
    hit += 1 if ok else 0
    print("\nINPUT %-28r -> want %-18s got %s  %s" % (text, want, got or "(없음)", "O" if ok else "X"))
    if args:
        print("   args   : %s" % json.dumps(args, ensure_ascii=False)[:180])
    if m.get("content"):
        print("   content: %r" % m["content"][:140])
print("\n함수 호출 %d/%d" % (hit, len(CASES)))

hr("끝 — ps 최종")
print(ps())
