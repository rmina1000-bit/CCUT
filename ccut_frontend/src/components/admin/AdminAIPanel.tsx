import React, { useEffect, useState } from "react";
import { Sparkles, Send, PanelRightClose, PanelRightOpen } from "lucide-react";
import { fetcher } from "@/services/api";

// [War Room v1] 공통 AI 보조 패널 — 전 관리자 화면 우측에 부착.
// read/query only: 이 패널에서 write 액션 실행 금지 (지시서 §STEP1).
// 권장 행동은 /admin/situation 실황(경보·작전큐)에서 도출 — mock 아님.
// 질의는 로컬 hub 실질의. 실패 시 정직 표시.

interface QueryResult {
  query?: string;
  result?: string;
  error?: string;
  detail?: string;
}

interface SituationLite {
  alerts?: { severity: string; title: string; recommended_action: string }[];
  action_queue?: { kind: string; title: string; priority: string }[];
}

export const AdminAIPanel: React.FC<{ screen: string }> = ({ screen }) => {
  const [open, setOpen] = useState(true);
  const [situation, setSituation] = useState<SituationLite | null>(null);
  const [situationError, setSituationError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<QueryResult[]>([]);

  useEffect(() => {
    fetcher("/admin/situation")
      .then(setSituation)
      .catch(e => setSituationError(String(e)));
  }, []);

  const ask = async () => {
    const q = query.trim();
    if (!q || loading) return;
    setLoading(true);
    try {
      const r = await fetcher("/admin/ai/query", {
        method: "POST",
        body: JSON.stringify({ role: "ops_brief", query: `[화면: ${screen}] ${q}` }),
      }) as QueryResult;
      setHistory(prev => [r, ...prev].slice(0, 10));
      setQuery("");
    } catch (e) {
      setHistory(prev => [{ query: q, error: String(e) }, ...prev].slice(0, 10));
    } finally {
      setLoading(false);
    }
  };

  const recommended = [
    ...(situation?.alerts ?? []).map(a => `[${a.severity}] ${a.recommended_action}`),
    ...(situation?.action_queue ?? []).map(w => `[${w.priority}] ${w.title}`),
  ].slice(0, 3);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="AI 보조 패널 열기"
        className="w-9 flex-shrink-0 border-l border-border/15 bg-[hsl(228_12%_9%)] flex items-start justify-center pt-4 text-muted-foreground/50 hover:text-primary transition-colors"
      >
        <PanelRightOpen size={15} />
      </button>
    );
  }

  return (
    <aside className="w-72 flex-shrink-0 border-l border-border/15 bg-[hsl(228_12%_9%)] flex flex-col">
      <div className="px-4 py-3 border-b border-border/15 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sparkles size={13} className="text-primary" />
          <p className="text-xs font-bold text-foreground/90">AI 보조</p>
        </div>
        <button onClick={() => setOpen(false)} title="접기"
          className="text-muted-foreground/40 hover:text-foreground/80 transition-colors">
          <PanelRightClose size={14} />
        </button>
      </div>

      <div className="px-4 py-3 border-b border-border/10">
        <p className="text-[10px] font-semibold text-muted-foreground/50 uppercase">현재 화면</p>
        <p className="text-xs font-bold text-foreground/80 mt-0.5">{screen}</p>
      </div>

      <div className="px-4 py-3 border-b border-border/10">
        <p className="text-[10px] font-semibold text-muted-foreground/50 uppercase mb-1.5">권장 다음 행동</p>
        {situationError ? (
          <p className="text-[11px] text-muted-foreground/40">상황실 데이터 연결 실패 — {situationError}</p>
        ) : recommended.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">현재 경보·대기 작업 없음</p>
        ) : (
          <ul className="space-y-1">
            {recommended.map((r, i) => (
              <li key={i} className="text-[11px] text-foreground/70 leading-snug">· {r}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="px-4 py-3 flex gap-1.5">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") ask(); }}
          placeholder="운영 질의..."
          className="flex-1 h-8 rounded-md bg-secondary/30 border border-border/15 px-2.5 text-[11px] text-foreground/90 outline-none focus:border-primary/40"
        />
        <button onClick={ask} disabled={loading}
          className="px-2.5 h-8 rounded-md bg-primary/15 hover:bg-primary/25 text-primary transition-colors disabled:opacity-50">
          {loading ? <Sparkles size={12} className="animate-pulse" /> : <Send size={12} />}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
        {history.map((h, i) => (
          <div key={i} className="rounded-md border border-border/10 bg-card/20 p-2.5">
            <p className="text-[10px] text-muted-foreground/50 truncate">Q. {h.query}</p>
            {h.error ? (
              <p className="text-[11px] text-red-400 mt-1">{h.error}{h.detail ? ` — ${h.detail}` : ""}</p>
            ) : (
              <p className="text-[11px] text-foreground/80 mt-1 leading-snug">{h.result}</p>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
};
