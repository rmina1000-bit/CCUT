import React, { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { fetcher } from "@/services/api";

// [War Room v1] 감사/작업기록 통합 — 감사 로그(append-only) + 작업 큐 + AI 실행 로그.
// 보안 이벤트/법무 요청은 각 관제 화면에서 관리 (여기서는 링크 성격의 안내만).

interface AuditLog {
  id: number;
  action: string;
  target_type: string | null;
  target_id: string | null;
  note: string | null;
  created_at: string;
}

interface WorkItem {
  id: number;
  kind: string;
  title: string;
  status: string;
  priority: string;
  next_action: string | null;
  created_at: string;
  closed_at: string | null;
}

interface AIRun {
  id: number;
  role: string;
  status: string;
  input_summary: string | null;
  duration_ms: number | null;
  created_at: string;
}

type AuditTab = "logs" | "work" | "ai";

const WORK_STATUS_STYLE: Record<string, string> = {
  open: "bg-amber-500/15 text-amber-400",
  in_progress: "bg-primary/15 text-primary",
  blocked: "bg-red-500/15 text-red-400",
  closed: "bg-secondary/20 text-muted-foreground/40",
};

export const AdminAuditPanel: React.FC = () => {
  const [tab, setTab] = useState<AuditTab>("logs");
  const [error, setError] = useState<string | null>(null);

  // 감사 로그
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);

  // 작업 큐
  const [items, setItems] = useState<WorkItem[]>([]);
  const [workForm, setWorkForm] = useState({ kind: "ops", title: "", priority: "P2" });
  const [showWorkForm, setShowWorkForm] = useState(false);

  // AI 실행
  const [runs, setRuns] = useState<AIRun[]>([]);

  const loadLogs = async (reset: boolean) => {
    setLogsLoading(true);
    try {
      const params = new URLSearchParams({ limit: "20" });
      if (!reset && cursor) params.set("cursor", String(cursor));
      const r = await fetcher(`/admin/audit/logs?${params.toString()}`) as
        { logs: AuditLog[]; next_cursor: number | null };
      setLogs(prev => reset ? r.logs : [...prev, ...r.logs]);
      setCursor(r.next_cursor);
    } catch (e) {
      setError(String(e));
    } finally {
      setLogsLoading(false);
    }
  };

  const loadWork = () =>
    fetcher("/admin/work-items?status=all&limit=50")
      .then(r => setItems(r.items ?? []))
      .catch(e => setError(String(e)));

  const loadRuns = () =>
    fetcher("/admin/ai/runs?limit=50")
      .then(r => setRuns(r.runs ?? []))
      .catch(e => setError(String(e)));

  useEffect(() => {
    if (tab === "logs") loadLogs(true);
    if (tab === "work") loadWork();
    if (tab === "ai") loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const createWork = async () => {
    if (!workForm.title.trim()) return;
    const r = await fetcher("/admin/work-items", {
      method: "POST", body: JSON.stringify(workForm),
    }).catch(e => ({ error: String(e) }));
    if (r.error) { setError(r.error); return; }
    setWorkForm({ kind: "ops", title: "", priority: "P2" });
    setShowWorkForm(false);
    loadWork();
  };

  const transitionWork = async (id: number, status: string) => {
    const r = await fetcher(`/admin/work-items/${id}/transition`, {
      method: "POST", body: JSON.stringify({ status }),
    }).catch(e => ({ error: String(e) }));
    if (r.error) setError(r.error);
    loadWork();
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-bold text-foreground/90">감사/작업기록</h1>
        <p className="text-[11px] text-muted-foreground/50 mt-0.5">
          append-only — 관리자 자신도 감사 대상 · 보안/법무는 각 관제 화면에서
        </p>
      </div>

      <div className="flex items-center gap-1.5 bg-secondary/30 rounded-lg p-0.5 w-fit">
        {([["logs", "감사 로그"], ["work", "작업 큐"], ["ai", "AI 실행"]] as const).map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-3.5 py-1.5 rounded-md text-xs font-medium transition-colors ${tab === k ? "bg-primary/20 text-primary" : "text-muted-foreground/60 hover:text-foreground/80"}`}>
            {l}
          </button>
        ))}
      </div>

      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {/* ── 감사 로그 ── */}
      {tab === "logs" && (
        <>
          {logs.length === 0 && !logsLoading ? (
            <p className="text-[11px] text-muted-foreground/40">기록된 관리자 행동이 없습니다.</p>
          ) : (
            <div className="rounded-lg border border-border/15 overflow-hidden">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="bg-secondary/20 text-muted-foreground/50 text-left">
                    <th className="px-3 py-2 font-semibold">#</th>
                    <th className="px-3 py-2 font-semibold">action</th>
                    <th className="px-3 py-2 font-semibold">target</th>
                    <th className="px-3 py-2 font-semibold">note</th>
                    <th className="px-3 py-2 font-semibold">시각</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/10">
                  {logs.map(l => (
                    <tr key={l.id} className="hover:bg-secondary/10">
                      <td className="px-3 py-2 font-mono text-muted-foreground/40">{l.id}</td>
                      <td className="px-3 py-2 font-mono text-primary/80">{l.action}</td>
                      <td className="px-3 py-2 text-foreground/60">
                        {l.target_type ? `${l.target_type}${l.target_id ? `:${l.target_id}` : ""}` : "—"}
                      </td>
                      <td className="px-3 py-2 text-foreground/80 max-w-[300px] truncate">{l.note ?? "—"}</td>
                      <td className="px-3 py-2 text-muted-foreground/40 whitespace-nowrap">
                        {new Date(l.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {cursor && (
            <div className="flex justify-center">
              <button onClick={() => loadLogs(false)} disabled={logsLoading}
                className="px-4 py-2 rounded-md bg-secondary/40 hover:bg-secondary/70 text-xs font-semibold text-foreground/70 transition-colors disabled:opacity-50">
                {logsLoading ? "불러오는 중..." : "더보기"}
              </button>
            </div>
          )}
        </>
      )}

      {/* ── 작업 큐 ── */}
      {tab === "work" && (
        <>
          <div className="flex justify-end">
            <button onClick={() => setShowWorkForm(v => !v)}
              className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-400 text-[11px] font-bold hover:bg-emerald-500/25 transition-colors">
              <Plus size={11} /> 작업 등록
            </button>
          </div>
          {showWorkForm && (
            <div className="rounded-lg border border-border/15 bg-card/20 p-4 flex items-center gap-2">
              <select value={workForm.kind} onChange={e => setWorkForm(f => ({ ...f, kind: e.target.value }))}
                className="h-8 rounded-md bg-secondary/30 border border-border/15 px-2 text-xs text-foreground/90 outline-none">
                {["ops", "support", "security", "billing", "review"].map(k => <option key={k} value={k}>{k}</option>)}
              </select>
              <input value={workForm.title} onChange={e => setWorkForm(f => ({ ...f, title: e.target.value }))}
                placeholder="작업 제목"
                className="flex-1 h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
              <select value={workForm.priority} onChange={e => setWorkForm(f => ({ ...f, priority: e.target.value }))}
                className="h-8 rounded-md bg-secondary/30 border border-border/15 px-2 text-xs text-foreground/90 outline-none">
                {["P0", "P1", "P2", "P3"].map(p => <option key={p} value={p}>{p}</option>)}
              </select>
              <button onClick={createWork}
                className="px-3 h-8 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors">
                등록
              </button>
            </div>
          )}
          {items.length === 0 ? (
            <p className="text-[11px] text-muted-foreground/40">작업 큐가 비어 있습니다.</p>
          ) : (
            <div className="rounded-lg border border-border/15 divide-y divide-border/10">
              {items.map(w => (
                <div key={w.id} className="px-3 py-2.5 flex items-center gap-3 text-xs">
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-black ${WORK_STATUS_STYLE[w.status] ?? WORK_STATUS_STYLE.open}`}>
                    {w.status}
                  </span>
                  <span className="font-black text-primary/80">{w.priority}</span>
                  <span className="font-mono text-muted-foreground/50">{w.kind}</span>
                  <span className="text-foreground/85 truncate flex-1">{w.title}</span>
                  {w.status === "open" && (
                    <button onClick={() => transitionWork(w.id, "in_progress")}
                      className="px-2 py-1 rounded-md bg-primary/15 text-primary text-[10px] font-bold hover:bg-primary/25 transition-colors">착수</button>
                  )}
                  {w.status !== "closed" && (
                    <button onClick={() => transitionWork(w.id, "closed")}
                      className="px-2 py-1 rounded-md bg-secondary/40 text-muted-foreground/60 text-[10px] font-bold hover:bg-secondary/70 transition-colors">닫기</button>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── AI 실행 ── */}
      {tab === "ai" && (
        runs.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">기록된 AI 실행이 없습니다.</p>
        ) : (
          <div className="rounded-lg border border-border/15 divide-y divide-border/10">
            {runs.map(r => (
              <div key={r.id} className="px-3 py-2 flex items-center gap-3 text-[11px]">
                <span className={`font-black ${r.status === "ok" ? "text-emerald-400" : "text-red-400"}`}>{r.status}</span>
                <span className="font-mono text-primary/70">{r.role}</span>
                <span className="text-foreground/70 truncate flex-1">{r.input_summary}</span>
                {r.duration_ms != null && <span className="text-muted-foreground/40">{r.duration_ms}ms</span>}
                <span className="text-muted-foreground/40 flex-shrink-0">{new Date(r.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
};
