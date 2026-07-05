import React, { useEffect, useState } from "react";
import { fetcher } from "@/services/api";

// [Admin v0] 운영 대시보드 — 전 KPI는 /admin/overview 실 DB 집계값만 표시 (하드코딩 금지).
interface Overview {
  kpis: Record<string, number | null>;
  latest_shot_date: string | null;
  recent_audit: { id: number; action: string; target_type: string | null; note: string | null; created_at: string }[];
  generated_at: string;
}

const KPI_LABELS: Record<string, string> = {
  source_count: "원본 영상",
  program_count: "프로젝트",
  proposal_count: "편집 제안",
  vault_event_count: "조각 사건(원장)",
  fragment_vault_count: "인지 조각",
  export_success_count: "내보내기 성공",
  person_count: "등록 인물",
};

export const AdminOverviewPanel: React.FC = () => {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetcher("/admin/overview")
      .then(setData)
      .catch(e => setError(String(e)));
  }, []);

  if (error) return <p className="text-xs text-red-400">overview 조회 실패: {error}</p>;
  if (!data) return <p className="text-xs text-muted-foreground/50 animate-pulse">집계 중...</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-foreground/90">운영 대시보드</h1>
        <p className="text-[11px] text-muted-foreground/50 mt-0.5">
          실 DB 집계 · 생성 {new Date(data.generated_at).toLocaleString()}
          {data.latest_shot_date && <> · 최근 촬영일 {data.latest_shot_date}</>}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {Object.entries(data.kpis).map(([k, v]) => (
          <div key={k} className="rounded-lg border border-border/15 bg-card/20 p-4">
            <p className="text-[10px] font-semibold text-muted-foreground/50 uppercase tracking-wide">
              {KPI_LABELS[k] ?? k}
            </p>
            <p className="text-xl font-bold text-foreground/90 mt-1">
              {v == null ? "—" : v.toLocaleString()}
            </p>
          </div>
        ))}
      </div>

      <div>
        <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">
          최근 관리자 활동
        </h2>
        {data.recent_audit.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">아직 기록된 관리자 활동이 없습니다.</p>
        ) : (
          <div className="rounded-lg border border-border/15 divide-y divide-border/10">
            {data.recent_audit.map(a => (
              <div key={a.id} className="px-3 py-2 flex items-center gap-3 text-[11px]">
                <span className="font-mono text-primary/80">{a.action}</span>
                <span className="text-foreground/70 truncate flex-1">{a.note ?? ""}</span>
                <span className="text-muted-foreground/40 flex-shrink-0">
                  {new Date(a.created_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
