import React, { useEffect, useState } from "react";
import { fetcher } from "@/services/api";

// [War Room v1] 상황실 — 30초 안에 전군 상태 파악.
// 전 수치는 /admin/situation 실 DB 집계·규칙 기반. 원장 미도입 항목은 정직 표기.

interface Situation {
  status: string;
  generated_at: string;
  // [LAB-52 ①] unknown = 경보 점검 자체가 실패해 상태를 판정할 수 없음(정상 아님).
  global_state: { service_level: "normal" | "watch" | "critical" | "unknown"; reason: string | null };
  kpis: Record<string, number | null>;
  alerts: { severity: string; title: string; reason: string; recommended_action: string }[];
  action_queue: { kind: string; title: string; priority: string; target: string | null }[];
  recent_audit: { id: number; action: string; note: string | null; created_at: string }[];
}

const KPI_LABELS: Record<string, string> = {
  source_count: "원본 영상",
  program_count: "프로젝트",
  proposal_count: "편집 제안",
  vault_event_count: "조각 사건(원장)",
  // [NERVE-1] 조각 수 두 개는 테이블이 다르다 — 이름으로 갈라 표기(감사 C-2-c).
  fragment_vault_count: "인지 조각(아카이브)",
  semantic_fragment_count: "전체 조각(제작중)",
  export_success_count: "내보내기 성공",
  person_count: "등록 인물",
  storage_bytes: "저장소(원장 미도입)",
  api_cost_estimate: "API 비용(원장 미도입)",
};

const LEVEL_STYLE: Record<string, string> = {
  normal: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  watch: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
  // [LAB-52 ①] 판정 불가 — 초록·빨강과 헷갈리지 않는 색. 무색 배지 방지.
  unknown: "bg-slate-500/20 text-slate-300 border-slate-400/40",
};

const SEV_STYLE: Record<string, string> = {
  P0: "bg-red-500/15 text-red-400 border-red-500/30",
  P1: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  P2: "bg-secondary/40 text-muted-foreground/70 border-border/20",
};

export const AdminSituationPanel: React.FC = () => {
  const [data, setData] = useState<Situation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetcher("/admin/situation").then(setData).catch(e => setError(String(e)));
  }, []);

  if (error) return <p className="text-xs text-red-400">상황실 조회 실패: {error}</p>;
  if (!data) return <p className="text-xs text-muted-foreground/50 animate-pulse">상황 집계 중...</p>;

  const level = data.global_state.service_level;

  return (
    <div className="space-y-6">
      {/* 글로벌 상태 바 */}
      <div className={`rounded-lg border px-4 py-3 flex items-center gap-3 ${LEVEL_STYLE[level]}`}>
        <span className="w-2.5 h-2.5 rounded-full bg-current animate-pulse" />
        <p className="text-sm font-black uppercase tracking-wide">{level}</p>
        <p className="text-[11px] opacity-80">
          {data.global_state.reason ?? "전 지표 정상 범위"} · 생성 {new Date(data.generated_at).toLocaleString()}
        </p>
      </div>

      {/* KPI 그리드 */}
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

      {/* 긴급 경보 */}
      <div>
        <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">긴급 경보</h2>
        {data.alerts.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">현재 경보 없음</p>
        ) : (
          <div className="space-y-2">
            {data.alerts.map((a, i) => (
              <div key={i} className={`rounded-lg border px-3 py-2.5 ${SEV_STYLE[a.severity] ?? SEV_STYLE.P2}`}>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-black">{a.severity}</span>
                  <span className="text-xs font-bold">{a.title}</span>
                  <span className="text-[11px] opacity-70">{a.reason}</span>
                </div>
                <p className="text-[11px] opacity-80 mt-1">→ {a.recommended_action}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 오늘의 작전 큐 */}
      <div>
        <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">오늘의 작전 큐</h2>
        {data.action_queue.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">
            대기 작업 없음 — 작업은 감사/작업기록에서 등록합니다
          </p>
        ) : (
          <div className="rounded-lg border border-border/15 divide-y divide-border/10">
            {data.action_queue.map((w, i) => (
              <div key={i} className="px-3 py-2 flex items-center gap-3 text-[11px]">
                <span className="font-black text-primary/80">{w.priority}</span>
                <span className="font-mono text-muted-foreground/50">{w.kind}</span>
                <span className="text-foreground/80 truncate flex-1">{w.title}</span>
                {w.target && <span className="text-muted-foreground/40">{w.target}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 최근 관리자 활동 */}
      <div>
        <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">최근 관리자 활동</h2>
        {data.recent_audit.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">기록 없음</p>
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
