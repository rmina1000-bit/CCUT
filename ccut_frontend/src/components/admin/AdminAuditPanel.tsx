import React, { useEffect, useState } from "react";
import { fetcher } from "@/services/api";

// [Admin v0] 감사 로그 — admin_audit_log append-only 원장을 그대로 표시. cursor 페이징.
interface AuditLog {
  id: number;
  action: string;
  target_type: string | null;
  target_id: string | null;
  note: string | null;
  created_at: string;
}

export const AdminAuditPanel: React.FC = () => {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (reset: boolean) => {
    setLoading(true);
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
      setLoading(false);
    }
  };

  useEffect(() => { load(true); }, []);

  if (error) return <p className="text-xs text-red-400">audit 조회 실패: {error}</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-foreground/90">감사 로그</h1>
        <p className="text-[11px] text-muted-foreground/50 mt-0.5">
          admin_audit_log · append-only (관리자 자신도 감사 대상)
        </p>
      </div>

      {logs.length === 0 && !loading ? (
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
          <button
            onClick={() => load(false)}
            disabled={loading}
            className="px-4 py-2 rounded-md bg-secondary/40 hover:bg-secondary/70 text-xs font-semibold text-foreground/70 transition-colors disabled:opacity-50"
          >
            {loading ? "불러오는 중..." : "더보기"}
          </button>
        </div>
      )}
    </div>
  );
};
