import React, { useEffect, useState } from "react";
import { Plus, ShieldOff } from "lucide-react";
import { fetcher } from "@/services/api";

// [War Room v1] 보안 관제 — admin_security_events 원장.
// v1에서 자동 차단 금지: 차단/제재 버튼은 존재하되 disabled (승인형 실행은 후속 트랙).

interface SecurityEvent {
  id: number;
  event_type: string;
  severity: string;
  user_id: string | null;
  target_type: string | null;
  target_id: string | null;
  detail_json: string | null;
  status: string;
  created_at: string;
}

const SEV_STYLE: Record<string, string> = {
  P0: "bg-red-500/15 text-red-400 border-red-500/25",
  P1: "bg-amber-500/15 text-amber-400 border-amber-500/25",
  P2: "bg-secondary/40 text-muted-foreground/70 border-border/20",
  P3: "bg-secondary/20 text-muted-foreground/50 border-border/15",
};

export const AdminSecurityPanel: React.FC = () => {
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [statusFilter, setStatusFilter] = useState<"open" | "all">("open");
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ event_type: "", severity: "P2" });
  const [showForm, setShowForm] = useState(false);

  const load = () => {
    fetcher(`/admin/security/events?status=${statusFilter}`)
      .then(r => setEvents(r.events ?? []))
      .catch(e => setError(String(e)));
  };
  useEffect(load, [statusFilter]);

  const create = async () => {
    if (!form.event_type.trim()) return;
    const r = await fetcher("/admin/security/events", {
      method: "POST", body: JSON.stringify(form),
    }).catch(e => ({ error: String(e) }));
    if (r.error) { setError(r.error); return; }
    setForm({ event_type: "", severity: "P2" });
    setShowForm(false);
    load();
  };

  const setStatus = async (id: number, status: string) => {
    const r = await fetcher(`/admin/security/events/${id}/status`, {
      method: "POST", body: JSON.stringify({ status }),
    }).catch(e => ({ error: String(e) }));
    if (r.error) setError(r.error);
    load();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-foreground/90">보안 관제</h1>
          <p className="text-[11px] text-muted-foreground/50 mt-0.5">
            admin_security_events 원장 · v1 자동 차단 금지
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
            <Plus size={11} /> 이벤트 등록
          </button>
        </div>
      </div>

      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {showForm && (
        <div className="rounded-lg border border-border/15 bg-card/20 p-4 flex items-center gap-2">
          <input value={form.event_type} onChange={e => setForm(f => ({ ...f, event_type: e.target.value }))}
            placeholder="event_type (예: upload_burst, render_fail_repeat)"
            className="flex-1 h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
          <select value={form.severity} onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}
            className="h-8 rounded-md bg-secondary/30 border border-border/15 px-2 text-xs text-foreground/90 outline-none">
            {["P0", "P1", "P2", "P3"].map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <button onClick={create}
            className="px-3 h-8 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors">
            등록
          </button>
        </div>
      )}

      {events.length === 0 ? (
        <p className="text-[11px] text-muted-foreground/40">
          보안 이벤트 원장이 비어 있습니다 — 자동 감지 파이프라인은 후속 단계에서 연결됩니다.
        </p>
      ) : (
        <div className="rounded-lg border border-border/15 divide-y divide-border/10">
          {events.map(ev => (
            <div key={ev.id} className="px-3 py-2.5 flex items-center gap-3">
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-black border ${SEV_STYLE[ev.severity] ?? SEV_STYLE.P2}`}>
                {ev.severity}
              </span>
              <span className="text-xs font-mono text-foreground/85 truncate flex-1">{ev.event_type}</span>
              <span className="text-[10px] font-mono text-muted-foreground/40">{ev.status}</span>
              <span className="text-[10px] text-muted-foreground/40">{new Date(ev.created_at).toLocaleString()}</span>
              {ev.status === "open" && (
                <button onClick={() => setStatus(ev.id, "triaged")}
                  className="px-2 py-1 rounded-md bg-amber-500/15 text-amber-400 text-[10px] font-bold hover:bg-amber-500/25 transition-colors">
                  triage
                </button>
              )}
              {ev.status !== "closed" && (
                <button onClick={() => setStatus(ev.id, "closed")}
                  className="px-2 py-1 rounded-md bg-secondary/40 text-muted-foreground/70 text-[10px] font-bold hover:bg-secondary/70 transition-colors">
                  닫기
                </button>
              )}
              <button disabled title="승인형 실행은 후속 트랙 — v1에서 자동 차단 금지"
                className="flex items-center gap-1 px-2 py-1 rounded-md bg-red-500/10 text-red-400/50 text-[10px] font-bold opacity-50 cursor-not-allowed">
                <ShieldOff size={10} /> 차단
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
