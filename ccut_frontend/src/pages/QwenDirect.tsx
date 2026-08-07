// [QWEN-DIRECT 2026-08-07] 국장↔큐원 직통 방.
// "큐원과 내가 그냥 직접 만나게 해줘"(국장) — 게이트·앵커·인격·위생·사전 전부 없음.
// 말이 그대로 가고 답이 그대로 온다. 저장 없음(새로고침 = 새 만남), 원장 무접촉.
// 여기서 관찰한 맨몸 큐원이 본선 채팅 구조(사다리 역전)의 실측 근거가 된다.
import { useEffect, useRef, useState } from "react";

type Msg = { role: "user" | "assistant"; content: string };

const QwenDirect = () => {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    try {
      const res = await fetch("/api/qwen/direct/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
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
      if (!accum) {
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
        <header className="px-4 py-3 border-b border-border/20 flex items-baseline gap-3">
          <h1 className="text-base font-semibold">큐원 직통</h1>
          <span className="text-[11px] text-muted-foreground/70">
            게이트 없음 · 프롬프트 없음 · 필터 없음 · 저장 없음 — 있는 그대로의 모델
          </span>
        </header>
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-[12px] text-muted-foreground/60 pt-8 text-center">
              첫 마디를 건네 보세요. 여기서는 아무도 끼어들지 않습니다.
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
            placeholder="큐원에게 그대로 전달됩니다"
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
