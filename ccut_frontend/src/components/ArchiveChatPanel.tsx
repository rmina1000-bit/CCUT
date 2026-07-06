import React, { useState, useRef, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { fetcher } from "@/services/api";
import { Send, Film, Clock } from "lucide-react";

// [아카이브 채팅 MVP] read-only 자연어 조회 전용 — 기존 프로젝트 채팅/제안 엔진과 무관.
// [RED-2] 결과 단위는 source가 아니라 fragment card.

interface FragmentCard {
  fragment_id: string;
  source_id: string;
  display_name: string | null;
  thumbnail_url: string | null;
  video_url: string | null;
  start: number | null;
  end: number | null;
  people: string | null;
  places: string | null;
  evidence: Record<string, any> | null;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text?: string;
  resultType?: string;
  results?: FragmentCard[];
}

const RESULT_TYPE_LABEL: Record<string, string> = {
  person: "인물 검색 결과",
  place: "장소 검색 결과",
  scene: "장면 검색 결과",
  keyword: "키워드 검색 결과",
  unmatched: "일치하는 결과를 찾지 못했습니다",
};

const formatTime = (sec: number | null) => {
  if (sec == null) return "";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

export const ArchiveChatPanel: React.FC<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
}> = ({ open, onOpenChange }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const query = input.trim();
    if (!query || loading) return;
    setInput("");
    const userMsg: ChatMessage = { id: `u_${Date.now()}`, role: "user", text: query };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);
    try {
      const r = await fetcher("/archive/chat", {
        method: "POST",
        body: JSON.stringify({ query }),
      }) as { result_set_id: string | null; result_type: string; results: FragmentCard[] };
      setMessages(prev => [...prev, {
        id: `a_${Date.now()}`,
        role: "assistant",
        resultType: r.result_type,
        results: r.results,
      }]);
    } catch (e) {
      console.error("[ArchiveChatPanel] 조회 실패:", e);
      setMessages(prev => [...prev, {
        id: `a_${Date.now()}`,
        role: "assistant",
        text: "조회 중 오류가 발생했습니다.",
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl h-[70vh] flex flex-col p-0 gap-0 bg-[hsl(228,12%,11%)] border-border/20">
        <DialogHeader className="px-5 py-4 border-b border-border/10">
          <DialogTitle className="text-sm font-bold text-foreground/90">아카이브 대화 검색</DialogTitle>
        </DialogHeader>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {messages.length === 0 && (
            <p className="text-xs text-muted-foreground/50">
              "실내 장면 보여줘", "한미숙 나오는 영상 있나?" 처럼 자연어로 물어보세요.
            </p>
          )}
          {messages.map(m => (
            <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              {m.role === "user" ? (
                <div className="max-w-[80%] px-3 py-2 rounded-xl bg-primary/20 text-foreground/90 text-sm">
                  {m.text}
                </div>
              ) : (
                <div className="max-w-[90%] w-full space-y-2">
                  {m.text && (
                    <div className="px-3 py-2 rounded-xl bg-secondary/30 text-foreground/80 text-sm inline-block">
                      {m.text}
                    </div>
                  )}
                  {m.resultType && (
                    <p className="text-[11px] font-semibold text-muted-foreground/60">
                      {RESULT_TYPE_LABEL[m.resultType] ?? m.resultType} {m.results?.length ? `(조각 ${m.results.length}개)` : ""}
                    </p>
                  )}
                  {m.results && m.results.length > 0 && (
                    <div className="grid grid-cols-2 gap-2">
                      {m.results.map(r => (
                        <div key={r.fragment_id} className="flex items-center gap-2 p-2 rounded-lg bg-card/30 border border-border/10">
                          <div className="w-14 h-10 flex-shrink-0 rounded-md bg-primary/10 flex items-center justify-center overflow-hidden">
                            {r.thumbnail_url ? (
                              <img src={r.thumbnail_url} className="w-full h-full object-cover" draggable={false} />
                            ) : (
                              <Film size={14} className="text-primary" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-foreground/85 truncate">
                              {r.display_name || r.fragment_id}
                            </p>
                            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/50 flex-wrap">
                              {(r.start != null || r.end != null) && (
                                <span className="flex items-center gap-0.5"><Clock size={9} />{formatTime(r.start)}–{formatTime(r.end)}</span>
                              )}
                              {r.people && <span className="text-foreground/60">인물: {r.people}</span>}
                              {r.places && <span className="text-foreground/60">장소: {r.places}</span>}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="px-3 py-2 rounded-xl bg-secondary/30 text-muted-foreground/50 text-xs animate-pulse">
                검색 중...
              </div>
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t border-border/10 flex items-center gap-2">
          <Input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") send(); }}
            placeholder="예: 실내 장면 보여줘"
            className="h-9 bg-secondary/30 border-border/10 text-sm"
            disabled={loading}
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary/20 hover:bg-primary/30 text-primary disabled:opacity-40 transition-colors flex-shrink-0"
          >
            <Send size={14} />
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
