// [QWEN-DIRECT 2026-08-07] 국장↔큐원 직통 방.
// "큐원과 내가 그냥 직접 만나게 해줘"(국장) — 게이트·앵커·인격·위생·사전 전부 없음.
// 말이 그대로 가고 답이 그대로 온다. 저장 없음(새로고침 = 새 만남), 원장 무접촉.
// 여기서 관찰한 맨몸 큐원이 본선 채팅 구조(사다리 역전)의 실측 근거가 된다.
import { useEffect, useRef, useState } from "react";

type Msg = { role: "user" | "assistant" | "system"; content: string };

// [문패 실험] '프롬프트 없음'은 존재하지 않는다 — 아무것도 안 보내면 올라마가
// 알리바바의 공장 한 줄("You are Qwen, created by Alibaba Cloud...")을 깐다(실측).
// 그래서 선택지는 문패의 유무가 아니라 누구의 문패냐다. 이 문패는 사전도 게이트도
// 인격도 아니다 — 방이 쓰는 언어 하나만 정한다.
// ★강도가 관건(2026-08-07 실측, 국장 발견 유발 문장 기준): 약한 한 줄 3/4 혼입,
//   강화판 0/4. 예방은 문패, 치료는 NG 재촬영 — 오염 역사에선 강화판도 1/4 뚫린다.
// ★젬마판(2026-08-07 실측): 젬마의 표류는 중국어가 아니라 로마자 발음 표기·영어
//   번역 덧붙임이다. 첫 턴 씨앗 1/5 → 한 번 붙으면 4/4로 계속 물려받는다(큐원의
//   중국어와 같은 역사 오염 구조). 결정적 차이 — 젬마는 문패가 듣는다: 첫 턴 0/4,
//   오염 역사에서도 4/4→1/4. 그래서 이 방은 문패를 기본으로 켜고 시작한다.
const ROOM_LINE =
  "너는 한국어 사용자와 대화한다. 오직 한국어 문장만 출력한다. " +
  "로마자 발음 표기, 영어 번역, 괄호 병기, Translation 표기를 절대 덧붙이지 않는다. " +
  "중국어 글자도 쓰지 않는다. 답이 끝나면 그대로 끝낸다.";

// [NG 재촬영] 실측(2026-08-07): 주범은 역사 오염 — 중국어가 한 번 역사에 실리면
// 문패로도 못 막는다. ASR max-context 루프와 같은 구조. 해법도 같다: 오염을 문맥에
// 싣지 않는 것. 답을 죽이고 템플릿을 꽂는 게 아니라 같은 질문을 다시 — NG 컷은
// 본편(역사)에 안 싣고, 재촬영 때는 지적 한 줄을 얹는다(눈먼 재샘플보다 회수율 높음).
const NUDGE_LINE =
  "주의: 직전 시도에 군더더기(중국어 또는 로마자·번역 덧붙임)가 섞여 폐기됐다. " +
  "이번에는 한국어 문장만 답하라.";

// 검문 — 한자만 보던 것을 넓혔다(제 측정 구멍이었다: 젬마 0/13 통과는 로마자·번역을
// 안 세었기 때문). 기술어·코드는 정상이므로 'Translation' 표기와 긴 로마자 괄호만 본다.
const CJK_RE = /[一-鿿]/;
const ROMAJI_RE = /\([A-Z][a-z]+[A-Za-z\s\-!?,.0-9']{15,}\)/;
const isDirty = (t: string) =>
  CJK_RE.test(t) || /\bTranslation\s*:/.test(t) || ROMAJI_RE.test(t);

// [꼬리 자르기] 덧붙인 군더더기(로마자 병기·영어 번역)만 뗀다 — 모델의 한국어 본문은
// 한 글자도 건드리지 않는다. 말을 죽이고 템플릿을 꽂는 필터와 다르다.
// 이 잘린 답이 그대로 역사가 되므로 다음 턴이 형식을 물려받지 않는다(실측: 5턴 대화
// 3회 반복에서 현행 1/5 → 위생 0/5. 오염 역사에선 문패+재촬영도 4/5 실패했다).
const trimTail = (t: string) =>
  t.split(/\n\s*Translation\s*:/)[0]
    .replace(new RegExp(ROMAJI_RE.source, "g"), "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

// [VOICE 2026-08-07] 국장 결정: 대화창에서 큐원 퇴출, 젬마로 간다.
//   실측 근거 — 큐원2.5는 기획·목록 어조에서 중국어로 표류하고(독립 재현 3회),
//   문패·재촬영 어느 것도 그 자리를 못 막았다(강화 문패 3/4 혼입). 프롬프트 층의
//   병이 아니라 모델 성질이라 목소리를 바꾼다. 이해·판단(비가시 JSON)은 별건.
//   젬마 실측(2026-08-07, 큐원이 무너진 세 자리 + 오염 역사): 중국어 0/13. 문패도
//   NG 재촬영도 없이 민낯으로. 두 스위치는 이제 비교·역사 보존용이다.
const VOICES = [
  { id: "gemma3:4b", label: "젬마" },
  { id: "qwen2.5:7b-instruct", label: "큐원(퇴출 예정)" },
];

const QwenDirect = () => {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voice, setVoice] = useState(VOICES[0].id);
  // 문패·재촬영 기본 ON — 젬마에는 둘 다 듣는다(실측). 국장이 방에 들어오자마자
  // 한국어만 나오는 것이 기본값이어야 한다. 끄면 민낯 그대로 볼 수 있다.
  const [koreanRoom, setKoreanRoom] = useState(true);
  const [ngRetake, setNgRetake] = useState(true);
  const [hygiene, setHygiene] = useState(true);
  const [ngNote, setNgNote] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setError(null);
    const history: Msg[] = [...messages, { role: "user", content: text }];
    setMessages([...history, { role: "assistant", content: "" }]);
    setBusy(true);
    setNgNote(null);

    const streamOnce = async (outbound: Msg[]): Promise<string> => {
      const res = await fetch("/api/qwen/direct/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: outbound, model: voice }),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let accum = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        for (;;) {
          const cut = buf.indexOf("\n\n");
          if (cut < 0) break;
          const raw = buf.slice(0, cut).trim();
          buf = buf.slice(cut + 2);
          if (!raw.startsWith("data:")) continue;
          const ev = JSON.parse(raw.slice(5));
          if (ev.type === "token" && typeof ev.text === "string") {
            accum += ev.text;
            const snapshot = accum;
            setMessages([...history, { role: "assistant", content: snapshot }]);
          } else if (ev.type === "error") {
            throw new Error(String(ev.message || "stream error"));
          }
        }
      }
      return accum;
    };

    try {
      // 한국어 방 ON = 우리 문패가 공장 문패를 대체한다 (화면에는 안 그린다)
      const outbound: Msg[] = koreanRoom
        ? [{ role: "system", content: ROOM_LINE }, ...history]
        : history;
      const maxTakes = ngRetake ? 3 : 1;
      let accum = "";
      let currentOutbound = outbound;
      for (let take = 1; take <= maxTakes; take++) {
        accum = await streamOnce(currentOutbound);
        if (!ngRetake || !isDirty(accum)) break;
        if (take < maxTakes) {
          // NG 컷은 본편(역사)에 싣지 않는다 — 지적 한 줄을 얹고 같은 질문을 다시.
          setNgNote(`NG ${take}회 — 중국어 혼입, 다시 찍는 중`);
          setMessages([...history, { role: "assistant", content: "" }]);
          currentOutbound = koreanRoom
            ? [{ role: "system", content: ROOM_LINE }, { role: "system", content: NUDGE_LINE }, ...history]
            : [{ role: "system", content: NUDGE_LINE }, ...history];
        } else {
          setNgNote("NG 한도(3테이크) 도달 — 마지막 테이크를 그대로 보입니다");
        }
      }
      if (accum) {
        // 화면에도 역사에도 '꼬리 뗀' 본문이 들어간다 — 다음 턴이 물려받을 것이 없다.
        setMessages([...history, { role: "assistant", content: hygiene ? trimTail(accum) : accum }]);
      } else {
        setMessages(history); // 빈 답이면 빈 말풍선을 남기지 않는다
        setError("답이 비었습니다 (모델이 아무 토큰도 내지 않음)");
      }
    } catch (e: any) {
      setMessages(history);
      setError(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col items-center">
      <div className="w-full max-w-2xl flex flex-col h-screen">
        <header className="px-4 py-3 border-b border-border/20 flex items-center gap-3 flex-wrap">
          <h1 className="text-base font-semibold">목소리 직통</h1>
          <span className="text-[11px] text-muted-foreground/70">
            게이트 없음 · 필터 없음 · 저장 없음
          </span>
          <div className="ml-auto flex items-center gap-2">
            <select
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              className="px-2 py-1 rounded-lg text-[11px] bg-secondary/10 border border-border/20 outline-none"
              title="대화 목소리 모델"
            >
              {VOICES.map((v) => (
                <option key={v.id} value={v.id}>{v.label}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setKoreanRoom((v) => !v)}
              className={
                koreanRoom
                  ? "px-3 py-1 rounded-lg text-[11px] bg-primary/25 border border-primary/40 transition-colors"
                  : "px-3 py-1 rounded-lg text-[11px] bg-secondary/10 border border-border/20 text-muted-foreground hover:text-foreground transition-colors"
              }
              title={koreanRoom ? ROOM_LINE : "지금은 알리바바 공장 문패(You are Qwen...)가 깔려 있다"}
            >
              {koreanRoom ? "문패: 한국어 방" : "문패: 공장(민낯)"}
            </button>
            <button
              type="button"
              onClick={() => setNgRetake((v) => !v)}
              className={
                ngRetake
                  ? "px-3 py-1 rounded-lg text-[11px] bg-primary/25 border border-primary/40 transition-colors"
                  : "px-3 py-1 rounded-lg text-[11px] bg-secondary/10 border border-border/20 text-muted-foreground hover:text-foreground transition-colors"
              }
              title="중국어가 섞인 테이크는 역사에 싣지 않고 같은 질문을 다시 한다 (최대 3테이크)"
            >
              {ngRetake ? "NG 재촬영: ON" : "NG 재촬영: OFF"}
            </button>
            <button
              type="button"
              onClick={() => setHygiene((v) => !v)}
              className={
                hygiene
                  ? "px-3 py-1 rounded-lg text-[11px] bg-primary/25 border border-primary/40 transition-colors"
                  : "px-3 py-1 rounded-lg text-[11px] bg-secondary/10 border border-border/20 text-muted-foreground hover:text-foreground transition-colors"
              }
              title="덧붙인 로마자 병기·영어 번역만 떼고 본문은 그대로 둔다. 잘린 답이 역사가 되어 다음 턴이 형식을 물려받지 않는다"
            >
              {hygiene ? "꼬리 자르기: ON" : "꼬리 자르기: OFF"}
            </button>
            <button
              type="button"
              onClick={() => { setMessages([]); setError(null); setNgNote(null); }}
              className="px-3 py-1 rounded-lg text-[11px] bg-secondary/10 border border-border/20 text-muted-foreground hover:text-foreground transition-colors"
            >
              새로 만나기
            </button>
          </div>
        </header>
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-[12px] text-muted-foreground/60 pt-8 text-center">
              첫 마디를 건네 보세요. 여기서는 아무도 끼어들지 않습니다.
              <br />
              목소리는 젬마입니다 — 큐원은 비교용으로만 남겨 뒀습니다.
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={
                  m.role === "user"
                    ? "max-w-[85%] px-4 py-2 rounded-2xl bg-primary/15 whitespace-pre-wrap text-[13px]"
                    : "max-w-[85%] px-4 py-2 rounded-2xl bg-secondary/10 border border-border/10 whitespace-pre-wrap text-[13px]"
                }
              >
                {m.content || (busy && i === messages.length - 1 ? "…" : "")}
              </div>
            </div>
          ))}
          {ngNote && (
            <div className="text-[11px] text-primary/70 text-center">{ngNote}</div>
          )}
          {error && (
            <div className="text-[11px] text-destructive/80 text-center">{error}</div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-border/20 flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder="그대로 전달됩니다"
            className="flex-1 resize-none rounded-xl bg-secondary/10 border border-border/20 px-3 py-2 text-[13px] outline-none focus:border-primary/40"
          />
          <button
            type="button"
            onClick={send}
            disabled={busy || !input.trim()}
            className="px-4 py-2 rounded-xl text-[13px] bg-primary/20 hover:bg-primary/30 disabled:opacity-40 transition-colors"
          >
            보내기
          </button>
        </div>
      </div>
    </div>
  );
};

export default QwenDirect;
