"""
GYEOL-LAB — 젬마 맨몸 실험창.

CCUT 무접촉. 이 파일은 ccut_backend / ccut_frontend 를 import 하지 않고,
CCUT DB 를 열지 않고, CCUT 포트를 쓰지 않는다.

  · ollama /api/chat 에 직접 붙는다
  · 시스템 프롬프트 0 · 프롬프트 주입 0 · 안내서 0 · 검문 0 · 후처리 0
  · 사용자가 친 글자 그대로 messages 에 쌓아 그대로 보낸다
  · 젬마 답도 그대로 화면에 뿌린다 (영어가 섞여도 안 지운다)
  · num_ctx 명시 · ollama ps 의 CONTEXT 표시 · 매 턴 프롬프트 토큰 수 표시

실행:  python gyeol_lab/lab.py
열기:  http://127.0.0.1:8781
"""

import json
import subprocess
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Windows 콘솔이 cp949 라 한글·em-dash 로그에서 죽는다. 출력만 UTF-8 로 돌린다.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PORT = 8781
OLLAMA = "http://127.0.0.1:11434"

# CCUT 이 쓰는 값과 같게 둔다. 다른 값을 쓰면 ollama 가 별개 러너를 띄워
# CCUT 의 상주 모델을 축출한다(8GiB GPU, 2026-08-09 실측).
DEFAULT_MODEL = "gemma3:4b"
DEFAULT_NUM_CTX = 16384


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>GYEOL-LAB — 젬마 맨몸</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#272c36;--fg:#e6e8ee;--dim:#98a0b3;
      --you:#1e2836;--gyeol:#1b2420;--accent:#6ea8fe;--warn:#ffb454}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:14px/1.65 "Malgun Gothic","Segoe UI",system-ui,sans-serif;
     display:flex;flex-direction:column;height:100vh}
header{padding:9px 16px;border-bottom:1px solid var(--line);background:var(--panel);
       display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:12.5px}
h1{font-size:14px;margin:0;font-weight:600;letter-spacing:.2px}
.badge{color:var(--dim)}
.badge b{color:var(--fg);font-weight:600;font-variant-numeric:tabular-nums}
input,select,button{background:#222836;color:var(--fg);border:1px solid var(--line);
       border-radius:6px;padding:5px 9px;font:inherit;font-size:12.5px}
input[type=number]{width:88px}
button{cursor:pointer}
button:hover{background:#2b3242}
button.primary{background:var(--accent);color:#06101f;border-color:var(--accent);font-weight:600}
main{flex:1;display:flex;min-height:0}
#log{flex:1;overflow-y:auto;padding:16px 18px}
#side{width:340px;border-left:1px solid var(--line);background:var(--panel);
      overflow-y:auto;padding:12px 14px;font-size:12px}
#side h2{font-size:12px;margin:14px 0 6px;color:var(--dim);font-weight:600}
#side h2:first-child{margin-top:0}
#side button{display:block;width:100%;text-align:left;margin:3px 0;font-size:11.5px;
             white-space:normal;line-height:1.4}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font-family:inherit}
.turn{margin-bottom:16px}
.who{font-size:11px;color:var(--dim);margin-bottom:3px}
.bubble{padding:9px 13px;border-radius:9px;border:1px solid var(--line)}
.you .bubble{background:var(--you)}
.gyeol .bubble{background:var(--gyeol)}
.meta{font-size:11px;color:var(--dim);margin-top:4px;font-variant-numeric:tabular-nums}
.meta b{color:var(--fg)}
footer{border-top:1px solid var(--line);background:var(--panel);padding:10px 16px;
       display:flex;gap:9px;align-items:flex-end}
textarea{flex:1;background:#11141a;color:var(--fg);border:1px solid var(--line);
         border-radius:8px;padding:9px 11px;font:inherit;resize:vertical;min-height:62px}
.note{color:var(--dim);font-size:11.5px;padding:0 16px 9px}
details{margin-top:6px}
summary{cursor:pointer;color:var(--dim);font-size:11px}
details pre{background:#11141a;border:1px solid var(--line);border-radius:6px;
            padding:8px 10px;margin-top:5px;font-size:11px;color:var(--dim)}
</style></head><body>

<header>
  <h1>GYEOL-LAB</h1>
  <span class="badge">모델 <select id="model"><option>gemma3:4b</option></select></span>
  <span class="badge">num_ctx <input type="number" id="numctx" value="16384" step="1024"></span>
  <span class="badge">ollama ps CONTEXT: <b id="psctx">—</b></span>
  <span class="badge">턴 <b id="turns">0</b></span>
  <span class="badge">직전 프롬프트 토큰 <b id="ptok">—</b></span>
  <button id="refresh">ps 새로고침</button>
  <button id="reset">대화 초기화</button>
  <button id="copyall">전문 복사</button>
</header>

<div class="note">
  시스템 프롬프트 없음 · 주입 없음 · 후처리 없음. 아래 <b>보낸 것 그대로</b>를 펼치면 실제 payload 가 보입니다.
</div>

<main>
  <div id="log"></div>
  <div id="side">
    <h2>0단계 — 무대 깔기</h2>
    <button data-fill="stage">조각 6개 목록 붙여넣기</button>
    <h2>1단계 — 순번 (오타 포함)</h2>
    <button data-fill="s1a">3번쨰 조각 앞 2초 잘라줘.</button>
    <button data-fill="s1b">4번째 조각 빼줘</button>
    <button data-fill="s1c">두번째 조각 가운데 2초 빼줘.</button>
    <h2>2단계 — 라벨·흘림</h2>
    <button data-fill="s2a">a69 조각 앞 2초 잘라줘</button>
    <button data-fill="s2b">A60 빼줘</button>
    <button data-fill="s2c">아까 그 낚시하는거 좀 짧게 해줘</button>
    <h2>3단계 — 정정 ★핵심</h2>
    <button data-fill="s3a">두번째 조각 빼줘</button>
    <button data-fill="s3b">아니야. 두번째조각은 a60이야.</button>
    <h2>4단계 — 흐릿한 말</h2>
    <button data-fill="s4a">음.. 그거 말고 그 앞에꺼</button>
    <button data-fill="s4b">아까 그거 되돌려줘</button>
    <button data-fill="s4c">좀 더 짧게</button>
    <button data-fill="s4d">그럼 다시</button>
    <h2>5단계 — 못 하는 일</h2>
    <button data-fill="s5a">2배속으로 해줘</button>
    <button data-fill="s5b">1080p로 뽑아줘</button>
    <button data-fill="s5c">노이즈 좀 없애줘</button>
    <h2>6단계 — 주제로 모으기</h2>
    <button data-fill="s6a">바다 나오는것만 남겨줘</button>
    <button data-fill="s6b">먹는 장면만 모아줘</button>
    <h2>7단계 — 누적·기억 ★핵심</h2>
    <button data-fill="s7a">조각 3개로 맞춰줘</button>
    <button data-fill="s7b">아까 앞에 2초 자른거 아직 살아있지?</button>
    <button data-fill="s7c">지금 몇 조각이야?</button>
    <h2>8단계 — 잡담 섞기</h2>
    <button data-fill="s8a">근데 넌 이름이 뭐야?</button>
    <button data-fill="s8b">아 맞다. 3번 다시 원래대로</button>
  </div>
</main>

<footer>
  <textarea id="box" placeholder="여기에 쳐서 Ctrl+Enter (또는 보내기)"></textarea>
  <button class="primary" id="send">보내기</button>
</footer>

<script>
const FILL = {
  stage: `영상 편집 중인데 좀 도와줘.
지금 조각 6개로 잘라놨어.

1. 12.5초 · A39 · 갯벌에서 뭐 줍는 장면
2. 13.2초 · A60 · 방에서 생선 튀김 먹는 장면 "이거라도 먹어야겠어요"
3. 17.7초 · A45 · 바닷가에서 낚시하는 장면 "우리는 이놀래기라고 하지"
4. 16.5초 · A59 · 침대에서 일어나는 장면
5. 14.8초 · A4 · 바다 보면서 "나 오늘 굶는 건가"
6. 17.5초 · A6 · 실내에서 낚싯대 정리

내가 뭐 시키면 뭘 어떻게 할 건지 말해줘.
실제로 바뀐 결과도 같이 보여주고.`,
  s1a:"3번쨰 조각 앞 2초 잘라줘.", s1b:"4번째 조각 빼줘",
  s1c:"두번째 조각 가운데 2초 빼줘.",
  s2a:"a69 조각 앞 2초 잘라줘", s2b:"A60 빼줘",
  s2c:"아까 그 낚시하는거 좀 짧게 해줘",
  s3a:"두번째 조각 빼줘", s3b:"아니야. 두번째조각은 a60이야.",
  s4a:"음.. 그거 말고 그 앞에꺼", s4b:"아까 그거 되돌려줘",
  s4c:"좀 더 짧게", s4d:"그럼 다시",
  s5a:"2배속으로 해줘", s5b:"1080p로 뽑아줘", s5c:"노이즈 좀 없애줘",
  s6a:"바다 나오는것만 남겨줘", s6b:"먹는 장면만 모아줘",
  s7a:"조각 3개로 맞춰줘", s7b:"아까 앞에 2초 자른거 아직 살아있지?",
  s7c:"지금 몇 조각이야?",
  s8a:"근데 넌 이름이 뭐야?", s8b:"아 맞다. 3번 다시 원래대로",
};

const messages = [];            // 시스템 메시지 없음. 사용자가 친 것과 젬마 답만.
const log = document.getElementById('log');
const box = document.getElementById('box');
let busy = false;

function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

function addTurn(who, text){
  const d = document.createElement('div');
  d.className = 'turn ' + who;
  d.innerHTML = '<div class="who">' + (who==='you'?'국장':'젬마') +
                '</div><div class="bubble"><pre></pre></div>';
  d.querySelector('pre').textContent = text;
  log.appendChild(d); log.scrollTop = log.scrollHeight;
  return d;
}

document.querySelectorAll('[data-fill]').forEach(b=>{
  b.onclick = () => { box.value = FILL[b.dataset.fill]; box.focus(); };
});

async function refreshPs(){
  try{
    const r = await fetch('/api/ps'); const t = await r.text();
    const line = t.split('\n').find(l => l.trim() && !l.startsWith('NAME'));
    document.getElementById('psctx').textContent = line ? line.trim() : '(상주 없음)';
  }catch(e){ document.getElementById('psctx').textContent = 'ps 실패: ' + e; }
}

async function send(){
  const text = box.value;
  if(!text.trim() || busy) return;
  busy = true; box.value = '';
  addTurn('you', text);

  // ★ 사용자가 친 글자 그대로. 다듬지 않는다.
  messages.push({role:'user', content:text});

  const payload = {
    model: document.getElementById('model').value,
    messages: messages,
    stream: true,
    options: { num_ctx: parseInt(document.getElementById('numctx').value, 10) }
  };

  const turn = addTurn('gyeol', '');
  const pre = turn.querySelector('pre');
  let acc = '', final = null;

  try{
    const res = await fetch('/api/chat', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const reader = res.body.getReader(); const dec = new TextDecoder();
    let buf = '';
    while(true){
      const {done, value} = await reader.read();
      if(done) break;
      buf += dec.decode(value, {stream:true});
      let nl;
      while((nl = buf.indexOf('\n')) >= 0){
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl+1);
        if(!line) continue;
        let j; try{ j = JSON.parse(line); }catch(e){ continue; }
        if(j.error){ acc += '\n[ollama error] ' + j.error; pre.textContent = acc; continue; }
        if(j.message && j.message.content){ acc += j.message.content; pre.textContent = acc;
          log.scrollTop = log.scrollHeight; }
        if(j.done) final = j;
      }
    }
  }catch(e){ acc += '\n[lab error] ' + e; pre.textContent = acc; }

  // ★ 젬마 답도 그대로. 영어가 섞여도 안 지운다.
  messages.push({role:'assistant', content:acc});

  const m = document.createElement('div');
  m.className = 'meta';
  if(final){
    const pt = final.prompt_eval_count ?? '—', ot = final.eval_count ?? '—';
    const ms = final.total_duration ? Math.round(final.total_duration/1e6) : '—';
    m.innerHTML = '프롬프트 토큰 <b>'+pt+'</b> · 출력 토큰 <b>'+ot+'</b> · <b>'+ms+'</b>ms';
    document.getElementById('ptok').textContent = pt;
  } else { m.textContent = '(완료 정보 없음)'; }

  const det = document.createElement('details');
  det.innerHTML = '<summary>보낸 것 그대로 (payload)</summary><pre>' +
                  esc(JSON.stringify(payload, null, 1)) + '</pre>';
  m.appendChild(det);
  turn.appendChild(m);

  document.getElementById('turns').textContent = messages.filter(x=>x.role==='user').length;
  busy = false; refreshPs();
}

document.getElementById('send').onclick = send;
box.addEventListener('keydown', e => {
  if(e.key === 'Enter' && (e.ctrlKey || e.metaKey)){ e.preventDefault(); send(); }
});
document.getElementById('refresh').onclick = refreshPs;
document.getElementById('reset').onclick = () => {
  messages.length = 0; log.innerHTML = '';
  document.getElementById('turns').textContent = '0';
  document.getElementById('ptok').textContent = '—';
};
document.getElementById('copyall').onclick = () => {
  const t = messages.map(m => (m.role==='user'?'국장: ':'젬마: ') + m.content).join('\n\n');
  navigator.clipboard.writeText(t);
};

(async () => {
  try{
    const r = await fetch('/api/tags'); const j = await r.json();
    const sel = document.getElementById('model');
    const names = (j.models||[]).map(m=>m.name);
    if(names.length){
      sel.innerHTML = names.map(n=>'<option>'+n+'</option>').join('');
      if(names.includes('gemma3:4b')) sel.value = 'gemma3:4b';
    }
  }catch(e){}
  refreshPs();
})();
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[LAB] " + fmt % args)

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/ps":
            try:
                out = subprocess.run(["ollama", "ps"], capture_output=True,
                                     text=True, timeout=10).stdout
            except Exception as e:
                out = "ps 실패: %s" % e
            self._send(200, out)
        elif self.path == "/api/tags":
            try:
                with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=10) as r:
                    self._send(200, r.read(), "application/json")
            except Exception as e:
                self._send(200, json.dumps({"models": [], "error": str(e)}),
                           "application/json")
        else:
            self._send(404, "no")

    def do_POST(self):
        if self.path != "/api/chat":
            self._send(404, "no")
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))

        # 여기서 payload 를 건드리지 않는다. 화면이 만든 것을 그대로 ollama 로.
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send(400, json.dumps({"error": "bad json: %s" % e}))
            return
        n_user = sum(1 for m in body.get("messages", []) if m.get("role") == "user")
        print("[LAB] → ollama  model=%s  num_ctx=%s  messages=%d (user %d)  system=%d"
              % (body.get("model"), (body.get("options") or {}).get("num_ctx"),
                 len(body.get("messages", [])), n_user,
                 sum(1 for m in body.get("messages", []) if m.get("role") == "system")))

        req = urllib.request.Request(
            OLLAMA + "/api/chat", data=raw,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            up = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            self._send(502, json.dumps({"error": e.read().decode("utf-8", "replace")}))
            return
        except Exception as e:
            self._send(502, json.dumps({"error": str(e)}))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while True:
                chunk = up.readline()
                if not chunk:
                    break
                self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except Exception as e:
            print("[LAB] stream 끊김: %s" % e)


if __name__ == "__main__":
    print("=" * 62)
    print(" GYEOL-LAB — 젬마 맨몸 실험창")
    print("   http://127.0.0.1:%d" % PORT)
    print("   ollama %s · 기본 %s · num_ctx %d" % (OLLAMA, DEFAULT_MODEL, DEFAULT_NUM_CTX))
    print("   시스템 프롬프트 0 · 주입 0 · 후처리 0 · CCUT 무접촉")
    print("=" * 62)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
