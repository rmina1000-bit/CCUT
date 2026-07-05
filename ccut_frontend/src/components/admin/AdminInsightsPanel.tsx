import React, { useState } from "react";
import { Sparkles, Send } from "lucide-react";
import { fetcher } from "@/services/api";

// [Admin v0] 세분 분석실 — 운영 질의창. 로컬 hub(qwen2.5) 실질의만, mock 금지.
// hub 미응답 시 백엔드가 {"error":"hub 응답 없음"}을 반환하고 그대로 표시한다.
interface InsightResult {
  query?: string;
  result?: string;
  sources_referenced?: number;
  context_used?: Record<string, unknown>;
  error?: string;
  detail?: string;
}

export const AdminInsightsPanel: React.FC = () => {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<InsightResult[]>([]);

  const ask = async () => {
    const q = query.trim();
    if (!q || loading) return;
    setLoading(true);
    try {
      const r = await fetcher("/admin/insights/query", {
        method: "POST",
        body: JSON.stringify({ query: q }),
      }) as InsightResult;
      setHistory(prev => [r, ...prev]);
      setQuery("");
    } catch (e) {
      setHistory(prev => [{ query: q, error: String(e) }, ...prev]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-foreground/90">세분 분석실</h1>
        <p className="text-[11px] text-muted-foreground/50 mt-0.5">
          자연어 운영 질의 → 실 DB 집계 컨텍스트 + 로컬 운영 AI(qwen2.5) 응답
        </p>
      </div>

      <div className="flex gap-2">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") ask(); }}
          placeholder='예: "현재 원본 영상 수는?" / "최근 7일 내보내기 추이는?"'
          className="flex-1 h-9 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40"
        />
        <button
          onClick={ask}
          disabled={loading}
          className="flex items-center gap-1.5 px-4 h-9 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors disabled:opacity-50"
        >
          {loading ? <Sparkles size={13} className="animate-pulse" /> : <Send size={13} />}
          {loading ? "질의 중..." : "질의"}
        </button>
      </div>

      <div className="space-y-3">
        {history.map((h, i) => (
          <div key={i} className="rounded-lg border border-border/15 bg-card/20 p-4 space-y-2">
            <p className="text-[11px] font-semibold text-foreground/60">Q. {h.query}</p>
            {h.error ? (
              <p className="text-xs text-red-400">
                {h.error}{h.detail ? ` — ${h.detail}` : ""}
              </p>
            ) : (
              <>
                <p className="text-sm text-foreground/90 leading-relaxed">{h.result}</p>
                <p className="text-[10px] text-muted-foreground/40">
                  참조 지표 {h.sources_referenced}개
                  {h.context_used && <> · {Object.entries(h.context_used).map(([k, v]) => `${k}=${v}`).join(" · ")}</>}
                </p>
              </>
            )}
          </div>
        ))}
        {history.length === 0 && !loading && (
          <p className="text-[11px] text-muted-foreground/40">
            아직 질의가 없습니다. 질의는 admin_saved_queries에 저장되고 감사 로그에 기록됩니다.
          </p>
        )}
      </div>
    </div>
  );
};
