import React, { useEffect, useState } from "react";
import { AdminLockedNotice } from "./AdminLockedNotice";
import { Plus } from "lucide-react";
import { fetcher } from "@/services/api";

// [War Room v1] 법무/수사공조 — 요청 원장·범위 기록·상태 관리까지.
// v1에서 데이터 추출/다운로드 기능 없음 (별도 승인 후 구현 — 상단 고지).

interface LegalRequest {
  id: number;
  requester: string;
  legal_basis: string | null;
  target_user_id: string | null;
  requested_range: string | null;
  status: string;
  data_scope_json: string | null;
  created_at: string;
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-secondary/40 text-muted-foreground/70",
  reviewing: "bg-amber-500/15 text-amber-400",
  approved: "bg-emerald-500/15 text-emerald-400",
  closed: "bg-secondary/20 text-muted-foreground/70",
};

export const AdminLegalPanel: React.FC = () => {
  const [requests, setRequests] = useState<LegalRequest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ requester: "", legal_basis: "", target_user_id: "", requested_range: "" });
  const [showForm, setShowForm] = useState(false);

  const load = () => {
    fetcher("/admin/legal/requests")
      .then(r => setRequests(r.requests ?? []))
      .catch(e => setError(String(e)));
  };
  useEffect(load, []);

  const create = async () => {
    if (!form.requester.trim()) return;
    const r = await fetcher("/admin/legal/requests", {
      method: "POST", body: JSON.stringify(form),
    }).catch(e => ({ error: String(e) }));
    if (r.error) { setError(r.error); return; }
    setForm({ requester: "", legal_basis: "", target_user_id: "", requested_range: "" });
    setShowForm(false);
    load();
  };

  const transition = async (id: number, status: string) => {
    const r = await fetcher(`/admin/legal/requests/${id}/status`, {
      method: "POST", body: JSON.stringify({ status }),
    }).catch(e => ({ error: String(e) }));
    if (r.error) setError(r.error);
    load();
  };

  return (
    <div className="space-y-5">
      <AdminLockedNotice tab="legal" />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-foreground/90">법무/수사공조</h1>
          <p className="text-[11px] text-muted-foreground/76 mt-0.5">
            admin_legal_requests 요청 원장
          </p>
        </div>
        <button onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-400 text-[11px] font-bold hover:bg-emerald-500/25 transition-colors">
          <Plus size={11} /> 요청 등록
        </button>
      </div>

      <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-4 py-2.5">
        <p className="text-[11px] text-amber-300/90">
          v1은 요청 기록·범위·상태 관리까지 — 데이터 추출 기능은 없습니다 (별도 승인 후 구현).
        </p>
      </div>

      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {showForm && (
        <div className="rounded-lg border border-border/15 bg-card/20 p-4 grid grid-cols-2 gap-2">
          <input value={form.requester} onChange={e => setForm(f => ({ ...f, requester: e.target.value }))}
            placeholder="요청자/기관 (필수)"
            className="h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
          <input value={form.legal_basis} onChange={e => setForm(f => ({ ...f, legal_basis: e.target.value }))}
            placeholder="법적 근거 (사건번호 등)"
            className="h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
          <input value={form.target_user_id} onChange={e => setForm(f => ({ ...f, target_user_id: e.target.value }))}
            placeholder="대상 사용자 ID"
            className="h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
          <div className="flex gap-2">
            <input value={form.requested_range} onChange={e => setForm(f => ({ ...f, requested_range: e.target.value }))}
              placeholder="요청 기간 (예: 2026-01~2026-06)"
              className="flex-1 h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
            <button onClick={create}
              className="px-3 h-8 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors">
              등록
            </button>
          </div>
        </div>
      )}

      {requests.length === 0 ? (
        <p className="text-[11px] text-muted-foreground/70">등록된 법무/수사공조 요청이 없습니다.</p>
      ) : (
        <div className="rounded-lg border border-border/15 divide-y divide-border/10">
          {requests.map(r => (
            <div key={r.id} className="px-3 py-2.5 flex items-center gap-3 text-xs">
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-black ${STATUS_STYLE[r.status] ?? STATUS_STYLE.draft}`}>
                {r.status}
              </span>
              <span className="text-foreground/85 truncate flex-1">{r.requester}</span>
              {r.legal_basis && <span className="font-mono text-muted-foreground/76">{r.legal_basis}</span>}
              {r.target_user_id && <span className="text-muted-foreground/76">대상: {r.target_user_id}</span>}
              {r.requested_range && <span className="text-muted-foreground/70">{r.requested_range}</span>}
              {r.status === "draft" && (
                <button onClick={() => transition(r.id, "reviewing")}
                  className="px-2 py-1 rounded-md bg-amber-500/15 text-amber-400 text-[10px] font-bold hover:bg-amber-500/25 transition-colors">검토</button>
              )}
              {r.status === "reviewing" && (
                <button onClick={() => transition(r.id, "approved")}
                  className="px-2 py-1 rounded-md bg-emerald-500/15 text-emerald-400 text-[10px] font-bold hover:bg-emerald-500/25 transition-colors">승인</button>
              )}
              {r.status !== "closed" && (
                <button onClick={() => transition(r.id, "closed")}
                  className="px-2 py-1 rounded-md bg-secondary/40 text-muted-foreground/60 text-[10px] font-bold hover:bg-secondary/70 transition-colors">종결</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
