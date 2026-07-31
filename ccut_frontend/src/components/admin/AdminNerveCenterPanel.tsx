import React, { useEffect, useState } from "react";
import { fetcher } from "@/services/api";

// [NERVE-1] 제작신경계 — 운영(상황실)과 제작 능력(편집연구실)을 한 화면에서 대조한다.
// 감사 C-1: 상황실은 운영 원장만 봐서 재료 3종이 0/812인 동안에도 초록이었다.
// 이 화면은 새로 계산하지 않는다. /admin/situation 한 번으로 전부 받는다
// (AI 보조 패널이 같은 API를 따로 부르다 상태가 갈린 사고를 되풀이하지 않는다).

interface EditCapability {
  status: "OK" | "UNKNOWN";
  error?: string;
  audited_at?: string;
  material_total?: number;
  material_missing?: number;
  material_missing_labels?: (string | null)[];
  rules_declared?: number;
  rules_registered?: number;
  rules_unregistered?: number;
  techniques_scope?: number;
  techniques_wired?: number;
  techniques_active?: number;
  techniques_wireable_unwired?: number;
  edges_total?: number;
  edges_broken?: number;
  evidence_missing?: number;
}

interface Situation {
  status: string;
  generated_at: string;
  global_state: { service_level: "normal" | "watch" | "critical" | "unknown"; reason: string | null };
  kpis: Record<string, number | null>;
  edit_capability: EditCapability;
  alerts: { severity: string; title: string; reason: string; recommended_action: string }[];
  action_queue: { kind: string; title: string; priority: string; target: string | null }[];
  probe_failures: { probe: string; error: string }[];
}

const KPI_LABELS: Record<string, string> = {
  source_count: "원본 영상",
  program_count: "프로젝트",
  proposal_count: "편집 제안",
  vault_event_count: "조각 사건(원장)",
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
  unknown: "bg-slate-500/20 text-slate-300 border-slate-400/40",
};

const SEV_STYLE: Record<string, string> = {
  P0: "bg-red-500/15 text-red-400 border-red-500/30",
  P1: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  P2: "bg-secondary/40 text-muted-foreground/70 border-border/20",
};

/** 능력 한 줄의 판정 — 값이 없으면 UNKNOWN. 0으로 위장하지 않는다. */
type RowState = "OK" | "WATCH" | "UNKNOWN";

const ROW_STATE_STYLE: Record<RowState, string> = {
  OK: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  WATCH: "text-amber-300 border-amber-500/30 bg-amber-500/10",
  UNKNOWN: "text-slate-300 border-slate-400/30 bg-slate-500/15",
};

const num = (v: number | undefined | null) => (typeof v === "number" ? v : null);

/** 편집연구실 5열을 각 1줄로 축약. 수치는 전부 /lab/audit 실측(상황실이 실어온 값). */
const capabilityRows = (cap: EditCapability): {
  column: string; state: RowState; headline: string; detail: string;
}[] => {
  const total = num(cap.material_total);
  const missing = num(cap.material_missing);
  const declared = num(cap.rules_declared);
  const registered = num(cap.rules_registered);
  const unregistered = num(cap.rules_unregistered);
  const scope = num(cap.techniques_scope);
  const wired = num(cap.techniques_wired);
  const active = num(cap.techniques_active);
  const wireable = num(cap.techniques_wireable_unwired);
  const broken = num(cap.edges_broken);
  const evidenceMissing = num(cap.evidence_missing);
  const labels = (cap.material_missing_labels ?? []).filter(Boolean).join(", ");

  return [
    {
      column: "재료",
      state: total == null || missing == null ? "UNKNOWN" : missing > 0 ? "WATCH" : "OK",
      headline: total == null || missing == null ? "미확인" : `${total - missing}/${total} 값 있음`,
      detail: missing ? `값 없는 재료: ${labels || "라벨 미확인"} — 이 재료를 요구하는 기법은 잠긴다` : "전 재료 값 보유",
    },
    {
      column: "측정 / 판단",
      state: evidenceMissing == null ? "UNKNOWN" : evidenceMissing > 0 ? "WATCH" : "OK",
      headline: evidenceMissing == null ? "미확인" : evidenceMissing > 0 ? `근거 MISSING ${evidenceMissing}건` : "선언 근거 전부 실재",
      detail: cap.audited_at ? `마지막 실측 ${new Date(cap.audited_at).toLocaleString()}` : "실측 시각 미확인",
    },
    {
      column: "하드룰",
      state: declared == null || unregistered == null ? "UNKNOWN" : unregistered > 0 ? "WATCH" : "OK",
      headline: declared == null ? "미확인" : `등록 ${registered ?? "?"}/${declared}`,
      detail: unregistered ? `검사기 없는 선언 ${unregistered}건 — 선언만으로는 집행되지 않는다` : "선언 전부 검사기 등록",
    },
    {
      column: "편집기법",
      state: scope == null || wired == null ? "UNKNOWN" : (wireable ?? 0) > 0 ? "WATCH" : "OK",
      headline: scope == null ? "미확인" : `가동 ${active ?? "?"} / 배선 ${wired} / 모수 ${scope}`,
      detail: wireable == null
        ? "즉시 배선 가능 수 미확인"
        : `즉시 배선 가능 ${wireable}건${broken ? ` · 끊긴 간선 ${broken}건` : ""}`,
    },
    {
      column: "결과검증",
      state: "UNKNOWN",
      headline: "미측정",
      detail: "편집 효과 검증은 아직 측정기가 없다 (LAB-2 범위) — 없는 값을 채우지 않는다",
    },
  ];
};

export const AdminNerveCenterPanel: React.FC = () => {
  const [data, setData] = useState<Situation | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    fetcher("/admin/situation")
      .then(d => { setData(d); setError(null); })
      .catch(e => { setData(null); setError(String(e)); });
  };
  useEffect(load, []);

  // 실패·측정 전·정상을 각각 다르게 말한다 (LAB-52 ② 규칙).
  if (error) {
    return (
      <div className="space-y-3">
        <p className="text-xs text-red-400">제작신경계 조회 실패 — {error}</p>
        <button onClick={load}
          className="px-3 h-8 rounded-md bg-secondary/40 hover:bg-secondary/70 text-xs font-semibold text-foreground/70 transition-colors">
          다시 조회
        </button>
      </div>
    );
  }
  if (!data) return <p className="text-xs text-muted-foreground/50 animate-pulse">집계 중...</p>;

  const level = data.global_state.service_level;
  const cap = data.edit_capability ?? { status: "UNKNOWN" as const };
  const rows = capabilityRows(cap);

  return (
    <div className="space-y-5">
      <p className="border-b border-cyan-500/20 pb-2 text-[11px] font-semibold text-cyan-200/80">
        /admin/nerve ── 요약 축: 지금 전체가 건강한가
      </p>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-foreground/90">제작신경계</h1>
          <p className="text-[11px] text-muted-foreground/50 mt-0.5">
            운영 원장 + 편집 능력 실측을 한 화면에서 대조 · 조회 1회(/admin/situation)
          </p>
        </div>
        <button onClick={load}
          className="px-3 h-8 rounded-md bg-secondary/30 hover:bg-secondary/60 text-[11px] font-semibold text-foreground/70 transition-colors">
          다시 조회
        </button>
      </div>

      {/* 상단 상태등 — 편집 결손도 반영된 판정 */}
      <div className={`rounded-lg border px-4 py-3 flex items-center gap-3 ${LEVEL_STYLE[level] ?? LEVEL_STYLE.unknown}`}>
        <span className="w-2.5 h-2.5 rounded-full bg-current animate-pulse" />
        <p className="text-sm font-black uppercase tracking-wide">{level}</p>
        <p className="text-[11px] opacity-80">
          {data.global_state.reason ?? "운영·제작 전 지표 정상 범위"} · 생성 {new Date(data.generated_at).toLocaleString()}
        </p>
      </div>

      {data.probe_failures?.length > 0 && (
        <p className="text-[11px] text-slate-300 border border-slate-400/30 bg-slate-500/10 px-3 py-2 rounded-md">
          점검 실패 {data.probe_failures.length}건 — {data.probe_failures.map(f => f.probe).join(", ")} · 해당 지표는 판정 불가
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* 좌측: 운영 KPI */}
        <section>
          <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">운영 원장</h2>
          <div className="grid grid-cols-2 gap-2.5">
            {Object.entries(data.kpis).map(([k, v]) => (
              <div key={k} className="rounded-lg border border-border/15 bg-card/20 p-3">
                <p className="text-[10px] font-semibold text-muted-foreground/50 uppercase tracking-wide">
                  {KPI_LABELS[k] ?? k}
                </p>
                <p className="text-lg font-bold text-foreground/90 mt-0.5">
                  {v == null ? "—" : v.toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* 우측: 편집 능력지도 요약 */}
        <section>
          <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">편집 능력</h2>
          {cap.status !== "OK" ? (
            <div className="rounded-lg border border-slate-400/30 bg-slate-500/10 p-4">
              <p className="text-sm font-bold text-slate-200">편집 능력 실측 조회 실패</p>
              <p className="text-[11px] text-muted-foreground/60 mt-1">{cap.error ?? "사유 미확인"}</p>
              <p className="text-[11px] text-muted-foreground/50 mt-1">
                값이 없다는 뜻이 아니다 — 판정 불가다. 편집연구실에서 직접 확인하십시오.
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-border/15 divide-y divide-border/10">
              {rows.map(row => (
                <div key={row.column} className="px-3 py-2.5 flex items-start gap-3">
                  <span className="w-16 flex-shrink-0 text-[10px] font-semibold text-muted-foreground/50 pt-0.5">
                    {row.column}
                  </span>
                  <span className={`px-1.5 py-0.5 rounded border text-[9px] font-black flex-shrink-0 ${ROW_STATE_STYLE[row.state]}`}>
                    {row.state}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-bold text-foreground/85">{row.headline}</p>
                    <p className="text-[10px] text-muted-foreground/55 leading-snug mt-0.5">{row.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="text-[10px] text-muted-foreground/40 mt-2">
            수치 출처는 편집연구실 실측(/lab/audit) 그대로 — 이 화면에서 다시 계산하지 않는다.
          </p>
        </section>
      </div>

      {/* 하단: 긴급 경보 */}
      <section>
        <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/50 mb-2">긴급 경보</h2>
        {data.alerts.length === 0 ? (
          <p className="text-[11px] text-muted-foreground/40">현재 경보 없음</p>
        ) : (
          <div className="space-y-2">
            {data.alerts.map((a, i) => (
              <div key={i} className={`rounded-lg border px-3 py-2.5 ${SEV_STYLE[a.severity] ?? SEV_STYLE.P2}`}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] font-black">{a.severity}</span>
                  <span className="text-xs font-bold">{a.title}</span>
                  <span className="text-[11px] opacity-70">{a.reason}</span>
                </div>
                <p className="text-[11px] opacity-80 mt-1">→ {a.recommended_action}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 하단: 오늘의 작전 큐 */}
      <section>
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
      </section>
    </div>
  );
};
