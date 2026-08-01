import React, { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { fetcher } from "@/services/api";

// [War Room v1] 디자인/카피/메뉴 제어 — admin_surface_configs 설정 원장.
// v1 범위: 원장 + 승인 상태까지. 사용자 화면 실반영은 후속 단계 (상단 고지).
// 자유 HTML 입력 금지 — 백엔드에서도 차단.

interface SurfaceConfig {
  id: number;
  scope: string;
  key: string;
  value_json: string;
  status: string;
  created_at: string;
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-secondary/40 text-muted-foreground/70",
  approved: "bg-emerald-500/15 text-emerald-400",
  retired: "bg-secondary/20 text-muted-foreground/70",
};

export const AdminDesignPanel: React.FC = () => {
  const [configs, setConfigs] = useState<SurfaceConfig[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ scope: "workspace", key: "", value_json: "" });
  const [showForm, setShowForm] = useState(false);

  const load = () => {
    fetcher("/admin/design/configs")
      .then(r => setConfigs(r.configs ?? []))
      .catch(e => setError(String(e)));
  };
  useEffect(load, []);

  const create = async () => {
    if (!form.key.trim() || !form.value_json.trim()) return;
    const r = await fetcher("/admin/design/configs", {
      method: "POST", body: JSON.stringify(form),
    }).catch(e => ({ error: String(e) }));
    if (r.error) { setError(r.error); return; }
    setForm({ scope: "workspace", key: "", value_json: "" });
    setShowForm(false);
    setError(null);
    load();
  };

  const transition = async (id: number, status: string) => {
    const r = await fetcher(`/admin/design/configs/${id}/status`, {
      method: "POST", body: JSON.stringify({ status }),
    }).catch(e => ({ error: String(e) }));
    if (r.error) setError(r.error);
    load();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-foreground/90">디자인 제어</h1>
          <p className="text-[11px] text-muted-foreground/76 mt-0.5">
            admin_surface_configs 설정 원장 · 자유 HTML 금지
          </p>
        </div>
        <button onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-400 text-[11px] font-bold hover:bg-emerald-500/25 transition-colors">
          <Plus size={11} /> 설정 초안
        </button>
      </div>

      <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-4 py-2.5">
        <p className="text-[11px] text-amber-300/90">
          v1 범위: 설정 원장 + 승인 상태까지 — 사용자 화면 실반영은 후속 단계에서 연결됩니다.
        </p>
      </div>

      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {showForm && (
        <div className="rounded-lg border border-border/15 bg-card/20 p-4 grid grid-cols-3 gap-2">
          <select value={form.scope} onChange={e => setForm(f => ({ ...f, scope: e.target.value }))}
            className="h-8 rounded-md bg-secondary/30 border border-border/15 px-2 text-xs text-foreground/90 outline-none">
            {["workspace", "chat", "archive", "upload", "admin_notice", "menu_flag"].map(s =>
              <option key={s} value={s}>{s}</option>)}
          </select>
          <input value={form.key} onChange={e => setForm(f => ({ ...f, key: e.target.value }))}
            placeholder="key (예: empty_state_text)"
            className="h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
          <div className="flex gap-2">
            <input value={form.value_json} onChange={e => setForm(f => ({ ...f, value_json: e.target.value }))}
              placeholder="값 (텍스트/플래그)"
              className="flex-1 h-8 rounded-md bg-secondary/30 border border-border/15 px-3 text-xs text-foreground/90 outline-none focus:border-primary/40" />
            <button onClick={create}
              className="px-3 h-8 rounded-md bg-primary/15 hover:bg-primary/25 text-xs font-semibold text-primary transition-colors">
              등록
            </button>
          </div>
        </div>
      )}

      {configs.length === 0 ? (
        <p className="text-[11px] text-muted-foreground/70">설정 원장이 비어 있습니다.</p>
      ) : (
        <div className="rounded-lg border border-border/15 divide-y divide-border/10">
          {configs.map(c => (
            <div key={c.id} className="px-3 py-2.5 flex items-center gap-3 text-xs">
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-black ${STATUS_STYLE[c.status] ?? STATUS_STYLE.draft}`}>
                {c.status}
              </span>
              <span className="font-mono text-muted-foreground/76">{c.scope}.{c.key}</span>
              <span className="text-foreground/85 truncate flex-1">{c.value_json}</span>
              {c.status === "draft" && (
                <button onClick={() => transition(c.id, "approved")}
                  className="px-2 py-1 rounded-md bg-emerald-500/15 text-emerald-400 text-[10px] font-bold hover:bg-emerald-500/25 transition-colors">승인</button>
              )}
              {c.status !== "retired" && (
                <button onClick={() => transition(c.id, "retired")}
                  className="px-2 py-1 rounded-md bg-secondary/40 text-muted-foreground/60 text-[10px] font-bold hover:bg-secondary/70 transition-colors">폐기</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
