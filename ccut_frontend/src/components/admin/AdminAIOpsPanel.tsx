import React, { useEffect, useState } from "react";
import { Sparkles, Send } from "lucide-react";
import { fetcher } from "@/services/api";

// [War Room v1] AI 운영실 — 로컬 hub 실측 상태 + 역할별 질의 + 실행 로그.
// v0 insights 질의 기능이 여기로 흡수됨. 외부 API AI는 disabled 슬롯만.

interface AIStatus {
  local: { model: string; url: string; reachable: boolean; error?: string };
  external: { status: string; note: string };
  runs_total: number;
  runs_failed: number;
  roles: string[];
}

interface AIRun {
  id: number;
  role: string;
  model_key: string;
  status: string;
  input_summary: string | null;
  output_summary: string | null;
  error: string | null;
  duration_ms: number | null;
  created_at: string;
}

interface QueryResult {
  role?: string;
  query?: string;
  result?: string;
  duration_ms?: number;
  error?: string;
  detail?: string;
}

export const AdminAIOpsPanel: React.FC = () => {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [runs, setRuns] = useState<AIRun[]>([]);
  const [role, setRole] = useState("ops_brief");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<QueryResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    fetcher("/admin/ai/status").then(setStatus).catch(e => setError(String(e)));
    fetcher("/admin/ai/runs?limit=30").then(r => setRuns(r.runs ?? [])).catch(e => setError(String(e)));
  };
  useEffect(load, []);

  const ask = async () => {
    const q = query.trim();
    if (!q || loading) return;
    setLoading(true);
    try {
      const r = await fetcher("/admin/ai/query", {
        method: "POST", body: JSON.stringify({ role, query: q }),
      }) as QueryResult;
      setResults(prev => [r, ...prev].slice(0, 10));
      setQuery("");
      load();
    } catch (e) {
      setResults(prev => [{ query: q, error: String(e) }, ...prev].slice(0, 10));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-bold text-foreground/90">AI 운영실</h1>
        <p className="text-[11px] text-muted-foreground/50 mt-0.5">
          한 번에 모델 1개 · 역할 1개 — 전 실행 admin_ai_runs 기록
        </p>
      </div>

      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {/* 상태 카드 */}
      <div className="grid grid-cols-2 gap-3">
        <div className={`rounded-lg border p-4 ${status?.local.reachable ? "border-emerald-500/25 bg-emerald-500/5" : "border-red-500/25 bg-red-500/5"}`}>
          <p className="text-[10px] font-semibold text-muted-foreground/50 uppercase">로컬 운영 AI</p>
          {status ? (
            <>
              <p className={`text-sm font-bold mt-1 ${status.local.reachable ? "text-emerald-400" : "text-red-400"}`}>
                {status.local.reachable ? "연결됨" : "연결 실패"}
              </p>
              <p className="text-[10px] text-muted-foreground/50 mt-0.5 font-mono">{status.local.model}</p>
              {status.local.error && <p className="text-[10px] text-red-400/80 mt-1">{status.local.error}</p>}
              <p className="text-[10px] text-muted-foreground/40 mt-1">
                실행 {status.runs_total}회 · 실패 {status.runs_failed}회
              </p>
            </>
          ) : <p className="text-[11px] text-muted-foreground/50 animate-pulse mt-1">확인 중...</p>}
        </div>
        <div className="rounded-lg border border-border/15 bg-card/20 p-4 opacity-60">
          <p className="text-[10px] font-semibold text-muted-foreground/50 uppercase">외부 API AI</p>
          <p className="text-sm font-bold text-muted-foreground/60 mt-1">disabled</p>
          <p className="text-[10px] text-muted-foreground/40 mt-0.5">{status?.external.note}</p>
        </div>
      </div>

      {/* 역할별 질의 */}
      <div className="flex gap-2">
        <select value={role} onChange={e => setRole(e.target.value)}
          className="h-9 rounded-md bg-secondary/30 border border-border/15 px-2 text-xs text-foreground/90 outline-none">
          {(status?.roles ?? ["ops_brief"]).map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") ask(); }}
          placeholder="운영 질의 입력..."
          className="flex-1 h-9 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40"
        />
        <button onClick={ask} disabled={loading}
          className="flex items-center gap-1.5 px-4 h-9 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors disabled:opacity-50">
          {loading ? <Sparkles size={13} className="animate-pulse" /> : <Send size={13} />}
          {loading ? "질의 중..." : "질의"}
        </button>
      </div>

      {results.map((r, i) => (
        <div key={i} className="rounded-lg border border-border/15 bg-card/20 p-4">
          <p className="text-[11px] font-semibold text-foreground/60">
            [{r.role}] Q. {r.query}
          </p>
          {r.error ? (
            <p className="text-xs text-red-400 mt-1">{r.error}{r.detail ? ` — ${r.detail}` : ""}</p>
          ) : (
            <p className="text-sm text-foreground/90 leading-relaxed mt-1">
              {r.result} <span className="text-[10px] text-muted-foreground/40">({r.duration_ms}ms)</span>
            </p>
          )}
        </div>
      ))}

      {/* 실행 로그 */}
      <div>
        <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">실행 로그</h2>
        {runs.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">아직 기록된 AI 실행이 없습니다.</p>
        ) : (
          <div className="rounded-lg border border-border/15 divide-y divide-border/10">
            {runs.map(r => (
              <div key={r.id} className="px-3 py-2 flex items-center gap-3 text-[11px]">
                <span className={`font-black ${r.status === "ok" ? "text-emerald-400" : "text-red-400"}`}>{r.status}</span>
                <span className="font-mono text-primary/70">{r.role}</span>
                <span className="text-foreground/70 truncate flex-1">{r.input_summary}</span>
                {r.duration_ms != null && <span className="text-muted-foreground/40">{r.duration_ms}ms</span>}
                <span className="text-muted-foreground/40 flex-shrink-0">{new Date(r.created_at).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
