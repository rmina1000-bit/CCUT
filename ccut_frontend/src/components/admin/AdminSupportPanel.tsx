import React, { useEffect, useState } from "react";
import { Sparkles, Plus, ChevronDown, ChevronUp } from "lucide-react";
import { fetcher } from "@/services/api";

// [War Room v1] 지원/문의 — 문의·불만·아이디어·버그 단일 접수 큐.
// 분류는 로컬 AI만(/classify). 원장 비어 있으면 정직 표기.

interface SupportCase {
  id: number;
  source: string;
  user_id: string | null;
  category: string | null;
  severity: string;
  status: string;
  title: string;
  body: string | null;
  ai_summary: string | null;
  ai_tags: string | null;
  created_at: string;
}

const SEV_STYLE: Record<string, string> = {
  high: "bg-red-500/15 text-red-400 border-red-500/25",
  normal: "bg-secondary/40 text-muted-foreground/70 border-border/20",
  low: "bg-secondary/20 text-muted-foreground/50 border-border/15",
};

export const AdminSupportPanel: React.FC = () => {
  const [cases, setCases] = useState<SupportCase[]>([]);
  const [statusFilter, setStatusFilter] = useState<"open" | "all">("open");
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [form, setForm] = useState({ title: "", body: "", severity: "normal" });
  const [showForm, setShowForm] = useState(false);

  const load = () => {
    fetcher(`/admin/support/cases?status=${statusFilter}`)
      .then(r => setCases(r.cases ?? []))
      .catch(e => setError(String(e)));
  };
  useEffect(load, [statusFilter]);

  const create = async () => {
    if (!form.title.trim()) return;
    const r = await fetcher("/admin/support/cases", {
      method: "POST", body: JSON.stringify(form),
    }).catch(e => ({ error: String(e) }));
    if (r.error) { setError(r.error); return; }
    setForm({ title: "", body: "", severity: "normal" });
    setShowForm(false);
    load();
  };

  const classify = async (id: number) => {
    setBusy(id);
    try {
      const r = await fetcher(`/admin/support/cases/${id}/classify`, { method: "POST" });
      if (r.error) setError(`분류 실패: ${r.error}${r.detail ? ` — ${r.detail}` : ""}`);
      load();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-foreground/90">지원/문의</h1>
          <p className="text-[11px] text-muted-foreground/50 mt-0.5">
            admin_support_cases 원장 · 분류는 로컬 AI만
          </p>
        </div>
        <div className="flex items-center gap-2">
          {(["open", "all"] as const).map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-all ${statusFilter === s ? "bg-primary/20 text-primary" : "bg-secondary/30 text-muted-foreground/60"}`}>
              {s === "open" ? "미처리" : "전체"}
            </button>
          ))}
          <button onClick={() => setShowForm(v => !v)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-400 text-[11px] font-bold hover:bg-emerald-500/25 transition-colors">
            <Plus size={11} /> 케이스 등록
          </button>
        </div>
      </div>

      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {showForm && (
        <div className="rounded-lg border border-border/15 bg-card/20 p-4 space-y-2">
          <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            placeholder="제목"
            className="w-full h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
          <textarea value={form.body} onChange={e => setForm(f => ({ ...f, body: e.target.value }))}
            placeholder="내용"
            className="w-full h-20 rounded-md bg-secondary/30 border border-border/15 px-3 py-2 text-xs text-foreground/90 outline-none focus:border-primary/40 resize-none" />
          <div className="flex items-center gap-2">
            <select value={form.severity} onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}
              className="h-8 rounded-md bg-secondary/30 border border-border/15 px-2 text-xs text-foreground/90 outline-none">
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
            </select>
            <button onClick={create}
              className="px-3 h-8 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors">
              등록
            </button>
          </div>
        </div>
      )}

      {cases.length === 0 ? (
        <p className="text-[11px] text-muted-foreground/40">
          접수 원장이 비어 있습니다 — 사용자 문의 유입 경로는 후속 단계에서 연결됩니다.
        </p>
      ) : (
        <div className="rounded-lg border border-border/15 divide-y divide-border/10">
          {cases.map(c => (
            <div key={c.id}>
              <button onClick={() => setExpanded(expanded === c.id ? null : c.id)}
                className="w-full px-3 py-2.5 flex items-center gap-3 text-left hover:bg-secondary/10 transition-colors">
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-black border ${SEV_STYLE[c.severity] ?? SEV_STYLE.normal}`}>
                  {c.severity}
                </span>
                <span className="text-[10px] font-mono text-muted-foreground/40">{c.status}</span>
                <span className="text-xs text-foreground/85 truncate flex-1">{c.title}</span>
                {c.category && <span className="text-[10px] font-mono text-primary/70">{c.category}</span>}
                {expanded === c.id ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              </button>
              {expanded === c.id && (
                <div className="px-4 pb-3 space-y-2 text-[11px]">
                  <p className="text-foreground/70 whitespace-pre-wrap">{c.body || "(본문 없음)"}</p>
                  {c.ai_summary && (
                    <p className="text-primary/80">AI 요약: {c.ai_summary} {c.ai_tags && <span className="text-muted-foreground/50">{c.ai_tags}</span>}</p>
                  )}
                  <button onClick={() => classify(c.id)} disabled={busy === c.id}
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-primary/15 hover:bg-primary/25 text-[11px] font-semibold text-primary transition-colors disabled:opacity-50">
                    <Sparkles size={11} className={busy === c.id ? "animate-pulse" : ""} />
                    {busy === c.id ? "분류 중..." : "로컬 AI 분류"}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
