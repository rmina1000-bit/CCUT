import React, { useEffect, useState } from "react";
import { fetcher } from "@/services/api";

// [Admin v0] 수익/정산 — daily_service_metrics 실집계.
// 데이터 없으면 "준비 중" 정직 표시 (stub 명시, 0 하드코딩 금지).
interface RevenueSummary {
  status: string;
  total?: number | null;
  message?: string;
  metrics?: { metric_key: string; days: number; total: number }[];
  metric_days_recorded?: number;
}

export const AdminRevenuePanel: React.FC = () => {
  const [data, setData] = useState<RevenueSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetcher("/admin/revenue/summary")
      .then(setData)
      .catch(e => setError(String(e)));
  }, []);

  if (error) return <p className="text-xs text-red-400">revenue 조회 실패: {error}</p>;
  if (!data) return <p className="text-xs text-muted-foreground/50 animate-pulse">집계 중...</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-foreground/90">수익/정산</h1>
        <p className="text-[11px] text-muted-foreground/50 mt-0.5">
          daily_service_metrics 기반 집계
        </p>
      </div>

      {data.status === "준비 중" ? (
        <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 p-5">
          <p className="text-sm font-bold text-amber-300">구독 데이터 준비 중</p>
          <p className="text-[11px] text-muted-foreground/60 mt-1 leading-relaxed">
            {data.message}
          </p>
          <p className="text-[10px] text-muted-foreground/40 mt-2">
            기록된 지표 일수: {data.metric_days_recorded ?? 0}일 · total: {String(data.total)}
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-border/15 divide-y divide-border/10">
          {(data.metrics ?? []).map(m => (
            <div key={m.metric_key} className="px-4 py-3 flex items-center justify-between text-xs">
              <span className="font-mono text-foreground/80">{m.metric_key}</span>
              <span className="text-muted-foreground/50">{m.days}일</span>
              <span className="font-bold text-foreground/90">{m.total?.toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
