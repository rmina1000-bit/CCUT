import React, { useEffect, useState } from "react";
import { ChevronDown, LockKeyhole, RefreshCw } from "lucide-react";
import { fetcher } from "@/services/api";

interface MaterialAudit {
  id: string;
  label: string;
  total: number;
  non_null: number;
  distinct: number;
  consumer_count: number;
  producer_count: number;
  consumers: string[];
  producers: string[];
  storage_unit: "semantic_fragment" | "evidence_chunk" | "source_timeline";
  fragment_consumer_contract: boolean;
  projection: string;
  projection_evidence: string | null;
  consumption: {
    unit: "semantic_fragment";
    non_null: number;
    total: number;
    method: string;
    evidence: string | null;
    same_as_storage: boolean;
  };
}

const STORAGE_UNIT_LABEL: Record<MaterialAudit["storage_unit"], string> = {
  semantic_fragment: "조각 단위",
  evidence_chunk: "청크 단위",
  source_timeline: "소스 시간축",
};

/** 소비 분모를 앞에 세우고, 저장 기준 수치는 부기로 남긴다. */
const materialCounts = (item: MaterialAudit) => ({
  consumed: `${item.consumption.non_null}/${item.consumption.total}`,
  stored: `${item.non_null}/${item.total}`,
  storedUnit: STORAGE_UNIT_LABEL[item.storage_unit],
});

type EdgeStatus = "LIVE" | "REGISTERED" | "LOCKED" | "BROKEN" | "UNDECLARED";
type RuleState = "DECLARED" | "REGISTERED" | "ACTING";
type RuleAction = "NONE" | "CORRECTIVE" | "VETO";

interface RuleAudit {
  id: string;
  declared_in: string | null;
  registered: boolean;
  acts: boolean;
  state: RuleState;
  checks_materials: string[] | "UNDECLARED";
  evidence: string | null;
  actions: RuleAction[];
  corrective_evidence: string | null;
  corrective_entry: string | null;
  corrective_gate: { env: string; value: string | null; on: boolean } | null;
  veto_evidence: string | null;
  veto_unreachable: { declared_in: string; reason: string; evidence: string } | null;
  no_action_reason: string | null;
}

const ACTION_LABEL: Record<RuleAction, string> = {
  NONE: "무동작",
  CORRECTIVE: "보정",
  VETO: "veto",
};

/** 룰이 실제로 무엇을 하는지 한 줄로. '집행'이라는 단일 표기는 쓰지 않는다. */
const ruleActionText = (item: RuleAudit) => {
  const acting = item.actions.filter(a => a !== "NONE").map(a => ACTION_LABEL[a]);
  if (acting.length === 0) return item.registered ? "등록 · 무동작" : "선언만";
  const gateOff = item.corrective_gate && !item.corrective_gate.on;
  return acting.join(" + ") + (gateOff ? " (게이트 OFF)" : "");
};

interface TechniqueAudit {
  id: string;
  wired: boolean;
  declared_in: string | null;
  requires_materials: string[] | "UNDECLARED";
  requires_rules: string[] | "UNDECLARED";
  relationship_source: "DERIVED" | "DIRECTOR" | "UNDECLARED";
  relationship_source_detail: {
    derived_from?: string[];
    approved_at?: string;
  };
  failure_check: string | null;
  blockers: Array<{ kind: string; detail: string }>;
  wireable_now: boolean;
}

interface AuditEdge {
  from: string;
  to: string;
  kind: "material→rule" | "material→technique" | "rule→technique" | "technique→verify";
  status: EdgeStatus;
  evidence: string | null;
}

interface CandidateMeasurement {
  회차: string;
  날짜: string;
  조건: string;
  정확도지표: string;
  조각당ms: number | "UNKNOWN";
  "83소스환산초": number | "UNKNOWN";
  UNKNOWN비율: string;
  raw파일경로: string;
}

interface LabCandidate {
  candidate_id: string;
  표시명: string;
  evidence_kind: "visual" | "motion" | "speech" | "prosody" | "acoustic" | "quality";
  환경상태: "INSTALLED" | "MODULE_MISSING" | "MODEL_MISSING";
  측정이력: CandidateMeasurement[];
  분류: string[];
  연결후보: string;
  재시도허용: { value: boolean; 사유: string };
  국장판정: { 상태: "미판정" | "채택" | "보류" | "폐기"; 날짜: string | null };
}

interface LedgerRecord {
  기록id: string;
  회차: string;
  제목: string;
  사실: string;
  주의?: string;
  근거: string[];
}

interface LabAudit {
  audited_at: string;
  duration_ms: number;
  materials: MaterialAudit[];
  rules: {
    declared: number;
    registered: number;
    corrective: number;
    veto: number;
    veto_unreachable: number;
    identity_overlap: number;
    unregistered: number;
    registered_ids: string[];
    items: RuleAudit[];
  };
  evidence_audit: {
    checked: number;
    exists: number;
    missing: number;
    moved: number;
    not_a_code_ref: number;
    items: Array<{
      source: string;
      field: string;
      declared: string;
      status: "MISSING" | "MOVED" | "NOT_A_CODE_REF";
      found_at: string | null;
      detail?: string | null;
    }>;
  };
  techniques: {
    declared: number;
    wired: number;
    wired_ids: string[];
    items: TechniqueAudit[];
    wireable_unwired: number;
    blocker_counts: Record<string, number>;
  };
  edges: AuditEdge[];
  candidates: LabCandidate[];
  ledger_records: LedgerRecord[];
  candidate_ledger_guard?: {
    status: "APPEND_ONLY";
    baseline: "git_HEAD";
    checked_candidates: number;
  };
  sensor_contract?: {
    exists: boolean;
    path: string;
    schema_version: number;
    required_fields: string[];
    sensor_count: number;
  };
  emotion_evidence: {
    legacy_node: { id: "emotion_score"; status: "재설계" };
    items: Array<{ id: string; status: "VALUE" | "UNKNOWN" }>;
    aggregation: "금지";
  };
}

const STATUS_STYLE: Record<EdgeStatus, { stroke: string; dash?: string; label: string }> = {
  LIVE: { stroke: "#34d399", label: "LIVE" },
  REGISTERED: { stroke: "#f59e0b", dash: "4 3", label: "등록·경고" },
  LOCKED: { stroke: "#64748b", label: "LOCKED" },
  BROKEN: { stroke: "#f97316", dash: "7 6", label: "BROKEN" },
  UNDECLARED: { stroke: "#64748b", dash: "2 7", label: "관계 미선언" },
};

const shortId = (value: string) => value
  .replace(/^RULE_/, "")
  .replace(/_/g, " ")
  .toLowerCase();

const MaterialTable: React.FC<{ materials: MaterialAudit[] }> = ({ materials }) => (
  <div className="overflow-x-auto border border-border/15">
    <table className="w-full text-[11px]">
      <thead className="bg-secondary/20 text-muted-foreground/60">
        <tr>
          <th className="px-3 py-2 text-left font-semibold">이름</th>
          <th className="px-3 py-2 text-right font-semibold">보유 (조각 단위)</th>
          <th className="px-3 py-2 text-right font-semibold">저장 기준</th>
          <th className="px-3 py-2 text-right font-semibold">구분값</th>
          <th className="px-3 py-2 text-right font-semibold">읽는 곳</th>
          <th className="px-3 py-2 text-right font-semibold">만드는 곳</th>
          <th className="px-3 py-2 text-left font-semibold">저장 단위</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border/10">
        {materials.map(item => {
          const counts = materialCounts(item);
          return (
            <tr key={item.id} className="hover:bg-secondary/10">
              <td className="px-3 py-2 text-foreground/85">{item.label}</td>
              <td className="px-3 py-2 text-right font-mono">{counts.consumed}</td>
              <td className={`px-3 py-2 text-right font-mono ${item.consumption.same_as_storage ? "text-muted-foreground/40" : "text-amber-300/70"}`}>
                {counts.stored}
              </td>
              <td className="px-3 py-2 text-right font-mono">{item.distinct || "—"}</td>
              <td className="px-3 py-2 text-right font-mono">{item.consumer_count}</td>
              <td className="px-3 py-2 text-right font-mono">{item.producer_count}</td>
              <td className="px-3 py-2 font-mono">{item.storage_unit}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

const CapabilityMap: React.FC<{
  audit: LabAudit;
  onSelect: (selection: { kind: string; id: string }) => void;
}> = ({ audit, onSelect }) => {
  const materials = audit.materials;
  const rules = audit.rules.items;
  const techniques = audit.techniques.items;
  const activeTechniqueIds = new Set(
    audit.edges.filter(edge => edge.kind.endsWith("technique")).map(edge => edge.to),
  );
  const visibleTechniques = techniques.filter(
    item => item.wired || activeTechniqueIds.has(item.id),
  );
  const nodeWidth = 172;
  const nodeHeight = 48;
  const colX = [20, 248, 476, 704, 932];
  const rowY = (index: number) => 68 + index * 64;
  const height = Math.max(
    540,
    rowY(Math.max(materials.length, rules.length, visibleTechniques.length)) + 16,
  );
  const positions = new Map<string, { x: number; y: number }>();
  materials.forEach((item, index) => positions.set(item.id, { x: colX[0], y: rowY(index) }));
  rules.forEach((item, index) => positions.set(item.id, { x: colX[2], y: rowY(index) }));
  visibleTechniques.forEach((item, index) => positions.set(item.id, { x: colX[3], y: rowY(index) }));

  const visibleEdges = audit.edges.filter(
    edge => positions.has(edge.from) && positions.has(edge.to),
  );
  const Node = ({
    x, y, title, subtitle, status, locked, onClick,
  }: {
    x: number; y: number; title: string; subtitle: string;
    status: EdgeStatus; locked?: boolean; onClick: () => void;
  }) => (
    <g onClick={onClick} className="cursor-pointer" role="button" tabIndex={0}>
      <rect
        x={x} y={y} width={nodeWidth} height={nodeHeight}
        rx={4}
        fill={status === "LIVE" ? "#102820" : status === "REGISTERED" ? "#2a2110" : status === "BROKEN" ? "#291a12" : "#171a20"}
        stroke={STATUS_STYLE[status].stroke}
        strokeWidth={status === "LIVE" ? 1.5 : 1}
        strokeDasharray={STATUS_STYLE[status].dash}
      />
      {locked && (
        <foreignObject x={x + 10} y={y + 14} width={18} height={18}>
          <LockKeyhole size={14} className="text-slate-500" />
        </foreignObject>
      )}
      <text x={x + (locked ? 32 : 12)} y={y + 20} fill="#e5e7eb" fontSize="11" fontWeight="700">
        {title}
      </text>
      <text x={x + 12} y={y + 37} fill="#94a3b8" fontSize="9">
        {subtitle}
      </text>
    </g>
  );

  return (
    <div className="border border-border/20 bg-[#0c0f13] overflow-x-auto">
      <svg
        viewBox={`0 0 1124 ${height}`}
        className="block min-w-[1040px] w-full"
        aria-label="편집 능력지도"
      >
        {["재료", "측정 / 판단", "하드룰", "편집기법", "결과검증"].map((label, index) => (
          <g key={label}>
            <text x={colX[index]} y={28} fill="#94a3b8" fontSize="11" fontWeight="700">{label}</text>
            <line x1={colX[index]} y1={40} x2={colX[index] + nodeWidth} y2={40} stroke="#29313d" />
          </g>
        ))}

        {visibleEdges.map((edge, index) => {
          const from = positions.get(edge.from)!;
          const to = positions.get(edge.to)!;
          const style = STATUS_STYLE[edge.status];
          const x1 = from.x + nodeWidth;
          const y1 = from.y + nodeHeight / 2;
          const x2 = to.x;
          const y2 = to.y + nodeHeight / 2;
          const mid = (x1 + x2) / 2;
          return (
            <g key={`${edge.from}-${edge.to}-${index}`}>
              <path
                d={`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`}
                fill="none"
                stroke={style.stroke}
                strokeWidth={edge.status === "LIVE" ? 1.7 : 1.2}
                strokeDasharray={style.dash}
                opacity={edge.status === "LIVE" ? 0.9 : 0.65}
              />
            </g>
          );
        })}

        {materials.map((item, index) => {
          const locked = item.non_null === 0;
          const counts = materialCounts(item);
          return (
            <Node
              key={item.id}
              x={colX[0]} y={rowY(index)}
              title={item.label}
              subtitle={item.consumption.same_as_storage
                ? `${counts.consumed} · 조각 단위`
                : `${counts.consumed} 조각 · 저장 ${counts.stored}`}
              status={locked ? "LOCKED" : "LIVE"}
              locked={locked}
              onClick={() => onSelect({ kind: "material", id: item.id })}
            />
          );
        })}

        <Node
          x={colX[1]} y={rowY(0)}
          title="실데이터 감사"
          subtitle={`${audit.duration_ms}ms · read-only`}
          status="LIVE"
          onClick={() => onSelect({ kind: "measure", id: "lab_audit" })}
        />
        <Node
          x={colX[1]} y={rowY(1)}
          title="관계 판정"
          subtitle="선언 또는 코드 참조만"
          status="LIVE"
          onClick={() => onSelect({ kind: "measure", id: "edge_audit" })}
        />

        {rules.map((item, index) => (
          <Node
            key={item.id}
            x={colX[2]} y={rowY(index)}
            title={shortId(item.id)}
            subtitle={ruleActionText(item)}
            status={item.acts ? "LIVE" : item.state === "REGISTERED" ? "REGISTERED" : "UNDECLARED"}
            onClick={() => onSelect({ kind: "rule", id: item.id })}
          />
        ))}

        {visibleTechniques.map((item, index) => {
          const incoming = visibleEdges.filter(edge => edge.to === item.id);
          const locked = incoming.some(edge => edge.status === "LOCKED");
          const status: EdgeStatus = locked ? "LOCKED" : item.wired ? "LIVE" : "BROKEN";
          return (
            <Node
              key={item.id}
              x={colX[3]} y={rowY(index)}
              title={shortId(item.id)}
              subtitle={item.wired ? "실제 배선" : "미배선"}
              status={status}
              locked={locked}
              onClick={() => onSelect({ kind: "technique", id: item.id })}
            />
          );
        })}

        <Node
          x={colX[4]} y={rowY(0)}
          title="효과 검증"
          subtitle="미측정 · LAB-2"
          status="UNDECLARED"
          onClick={() => onSelect({ kind: "verify", id: "unmeasured" })}
        />
      </svg>
    </div>
  );
};

export const AdminEditLabPanel: React.FC = () => {
  const [audit, setAudit] = useState<LabAudit | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<{ kind: string; id: string } | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);

  const load = async (rerun = false) => {
    setLoading(true);
    setError(null);
    try {
      setAudit(await fetcher(rerun ? "/lab/audit/run" : "/lab/audit", rerun ? { method: "POST" } : undefined));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading && !audit) return <p className="text-xs text-muted-foreground/50">측정 중...</p>;
  if (error && !audit) return <p className="text-xs text-red-400">편집연구실 조회 실패: {error}</p>;

  const missingMaterials = audit?.materials.filter(item => item.non_null === 0).length ?? 0;
  const selectedMaterial = selection?.kind === "material"
    ? audit?.materials.find(item => item.id === selection.id)
    : null;
  const selectedRule = selection?.kind === "rule"
    ? audit?.rules.items.find(item => item.id === selection.id)
    : null;
  const selectedTechnique = selection?.kind === "technique"
    ? audit?.techniques.items.find(item => item.id === selection.id)
    : null;
  const selectedEdges = audit?.edges.filter(
    edge => edge.from === selection?.id || edge.to === selection?.id,
  ) ?? [];
  const selectedCandidate = audit?.candidates.find(
    candidate => candidate.candidate_id === selectedCandidateId,
  );

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-foreground/90">편집연구실</h1>
          <p className="text-[11px] text-muted-foreground/50 mt-0.5">
            {audit
              ? `재료 ${audit.materials.length - missingMaterials} 값 있음 / ${missingMaterials} 값 없음 · 하드룰 ${audit.rules.declared} 선언 / ${audit.rules.registered} 등록 / ${audit.rules.corrective} 보정 / ${audit.rules.veto} veto · 기법 ${audit.techniques.declared} 선언 / ${audit.techniques.wired} 배선`
              : "측정 결과 없음"}
          </p>
          {audit?.sensor_contract && audit.candidate_ledger_guard && (
            <div className="mt-2 flex flex-wrap gap-2 text-[9px] font-mono">
              <span className="border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-emerald-200/80">
                Sensor Contract v{audit.sensor_contract.schema_version} · {audit.sensor_contract.sensor_count} sensors
              </span>
              <span className="border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-sky-200/80">
                측정이력 {audit.candidate_ledger_guard.status} · {audit.candidate_ledger_guard.baseline}
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          {audit && (
            <span className="text-[10px] text-muted-foreground/40">
              마지막 측정 {new Date(audit.audited_at).toLocaleTimeString()} · {audit.duration_ms}ms
            </span>
          )}
          <button
            onClick={() => load(true)}
            disabled={loading}
            title="다시 측정"
            className="h-8 w-8 inline-flex items-center justify-center border border-border/15 bg-secondary/20 text-muted-foreground/70 hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && <p className="text-[11px] text-red-400">{error}</p>}

      {audit && (
        <>
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/55">능력지도</h2>
              <div className="flex gap-3 text-[9px] font-mono text-muted-foreground/60">
                {(Object.keys(STATUS_STYLE) as EdgeStatus[]).map(status => (
                  <span key={status} className="inline-flex items-center gap-1">
                    <i
                      className="block w-5 border-t"
                      style={{
                        borderColor: STATUS_STYLE[status].stroke,
                        borderStyle: status === "LIVE" || status === "LOCKED" ? "solid" : "dashed",
                      }}
                    />
                    {STATUS_STYLE[status].label}
                  </span>
                ))}
              </div>
            </div>
            <CapabilityMap audit={audit} onSelect={setSelection} />
          </section>

          <section className="border border-border/15 bg-secondary/10 p-4 min-h-28">
            <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/55 mb-3">선택 상세</h2>
            {!selection && <p className="text-[11px] text-muted-foreground/45">노드를 선택하면 근거가 표시됩니다.</p>}
            {selectedMaterial && (
              <div className="space-y-1 text-[11px]">
                <p className="text-sm font-semibold">
                  {selectedMaterial.label} {materialCounts(selectedMaterial).consumed}
                  <span className="ml-1 text-[10px] font-normal text-muted-foreground/55">조각 단위 · 실제 소비 기준</span>
                </p>
                <p className={selectedMaterial.consumption.same_as_storage ? "text-muted-foreground/60" : "text-amber-300/75"}>
                  저장 기준 {materialCounts(selectedMaterial).stored} ({materialCounts(selectedMaterial).storedUnit})
                  {selectedMaterial.consumption.same_as_storage
                    ? " · 소비 분모와 동일"
                    : " · 소비 분모와 다름 — 저장 기준 수치는 과장이다"}
                </p>
                <p className="text-muted-foreground/60 break-all">
                  소비 측정법 {selectedMaterial.consumption.method} · 근거: {selectedMaterial.consumption.evidence || "저장 단위 = 소비 단위 (투영 없음)"}
                </p>
                <p>구분값 {selectedMaterial.distinct} · producers {selectedMaterial.producer_count} · consumers {selectedMaterial.consumer_count}</p>
                <p>저장 단위 {selectedMaterial.storage_unit} · 조각 소비 계약 {selectedMaterial.fragment_consumer_contract ? selectedMaterial.projection : "없음"}</p>
                <p className="text-muted-foreground/60 break-all">투영 근거(선언): {selectedMaterial.projection_evidence || "없음"}</p>
                <p className="text-muted-foreground/60 break-all">producers: {selectedMaterial.producers.join(" / ") || "없음"}</p>
                <p className="text-muted-foreground/60 break-all">consumers: {selectedMaterial.consumers.join(" / ") || "없음"}</p>
                <p>{selectedMaterial.non_null === 0
                  ? `${selectedMaterial.label} ${materialCounts(selectedMaterial).consumed} → 생산기 없음 → 명시적으로 요구하는 하위 기법 잠김`
                  : `${selectedMaterial.label} 값이 존재하며 선언 또는 코드 참조가 있는 관계만 표시합니다.`}</p>
              </div>
            )}
            {selectedRule && (
              <div className="space-y-1 text-[11px]">
                <p className="text-sm font-semibold">
                  {selectedRule.id}
                  <span className="ml-2 text-[10px] font-normal text-foreground/70">{ruleActionText(selectedRule)}</span>
                </p>
                <p>검사 재료 {Array.isArray(selectedRule.checks_materials) ? selectedRule.checks_materials.join(", ") : "관계 미선언"}</p>
                {selectedRule.corrective_evidence && (
                  <p className="text-muted-foreground/60 break-all">
                    보정 근거: {selectedRule.corrective_evidence}
                    {selectedRule.corrective_entry && ` · 진입 ${selectedRule.corrective_entry}`}
                  </p>
                )}
                {selectedRule.corrective_gate && (
                  <p className={selectedRule.corrective_gate.on ? "text-emerald-300/75" : "text-amber-300/75"}>
                    보정 게이트 {selectedRule.corrective_gate.env}={selectedRule.corrective_gate.value ?? "미설정"} ·{" "}
                    {selectedRule.corrective_gate.on ? "ON — 보정이 실제로 돈다" : "OFF — 코드는 있으나 돌지 않는다"}
                  </p>
                )}
                {selectedRule.veto_evidence && (
                  <p className="text-muted-foreground/60 break-all">veto 근거: {selectedRule.veto_evidence}</p>
                )}
                {selectedRule.veto_unreachable && (
                  <p className="text-amber-300/75 break-all">
                    veto 선언 · 도달 불가: {selectedRule.veto_unreachable.reason} (선언 {selectedRule.veto_unreachable.declared_in} / 근거 {selectedRule.veto_unreachable.evidence})
                  </p>
                )}
                {selectedRule.no_action_reason && (
                  <p className="text-muted-foreground/60 break-all">무동작 사유: {selectedRule.no_action_reason}</p>
                )}
                <p className="text-muted-foreground/60 break-all">선언 위치: {selectedRule.declared_in || "없음"}</p>
              </div>
            )}
            {selectedTechnique && (
              <div className="space-y-1 text-[11px]">
                <p className="text-sm font-semibold">{selectedTechnique.id}</p>
                <p>{selectedTechnique.wired ? "실제 배선" : "미배선"} · 요구 재료 {Array.isArray(selectedTechnique.requires_materials) ? selectedTechnique.requires_materials.join(", ") : "관계 미선언"}</p>
                <p>요구 룰 {Array.isArray(selectedTechnique.requires_rules) ? selectedTechnique.requires_rules.join(", ") : "관계 미선언"}</p>
                <p>관계 출처 {selectedTechnique.relationship_source}</p>
                {selectedTechnique.relationship_source_detail.derived_from && (
                  <p className="text-muted-foreground/60 break-all">유도 근거: {selectedTechnique.relationship_source_detail.derived_from.join(" / ")}</p>
                )}
                <p className="text-muted-foreground/60 break-all">근거: {selectedTechnique.declared_in || "없음"}</p>
                <p>차단: {selectedTechnique.blockers.map(item => `${item.kind}(${item.detail})`).join(" / ") || "없음"}</p>
              </div>
            )}
            {selection && !selectedMaterial && !selectedRule && !selectedTechnique && (
              <p className="text-[11px] text-muted-foreground/55">
                {selection.kind === "verify"
                  ? "결과 검증은 LAB-2 범위입니다. 현재 전부 미측정입니다."
                  : "감사기는 운영 DB와 명시된 코드 참조를 read-only로 측정합니다."}
              </p>
            )}
            {selectedEdges.length > 0 && (
              <div className="mt-3 border-t border-border/15 pt-2 space-y-1">
                {selectedEdges.map((edge, index) => (
                  <p key={`${edge.from}-${edge.to}-${index}`} className="text-[10px] font-mono text-muted-foreground/60 break-all">
                    {edge.from} → {edge.to} · {edge.status} · {edge.evidence}
                  </p>
                ))}
              </div>
            )}
          </section>

          <section className="space-y-3 border-t border-border/15 pt-4">
            <div>
              <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/55">기법 배선 관문</h2>
              <p className="mt-1 text-[10px] text-muted-foreground/45">
                현재 미배선 중 즉시 가능 {audit.techniques.wireable_unwired} · {Object.entries(audit.techniques.blocker_counts).map(([key, value]) => `${key} ${value}`).join(" / ")}
              </p>
            </div>
            <div className="overflow-x-auto border border-border/15">
              <table className="w-full text-[11px]">
                <thead className="bg-secondary/20 text-muted-foreground/60">
                  <tr><th className="px-3 py-2 text-left">기법</th><th className="px-3 py-2 text-left">관계 출처</th><th className="px-3 py-2 text-left">상태</th><th className="px-3 py-2 text-left">막힌 사유</th></tr>
                </thead>
                <tbody className="divide-y divide-border/10">
                  {audit.techniques.items.map(item => (
                    <tr key={item.id}>
                      <td className="px-3 py-2 font-mono">{item.id}</td>
                      <td className="px-3 py-2 font-mono">{item.relationship_source}</td>
                      <td className="px-3 py-2">{item.wired ? "배선됨" : item.wireable_now ? "배선 가능" : "차단"}</td>
                      <td className="px-3 py-2 text-muted-foreground/65">{item.blockers.map(blocker => `${blocker.kind}: ${blocker.detail}`).join(" / ") || "없음"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-3 border-t border-border/15 pt-4">
            <div>
              <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/55">센서 후보 장부</h2>
              <p className="mt-1 text-[10px] text-muted-foreground/45">측정 사실과 분류·국장 판정을 분리해 보존합니다.</p>
            </div>
            <div className="overflow-x-auto border border-border/15">
              <table className="w-full text-[11px]">
                <thead className="bg-secondary/20 text-muted-foreground/60">
                  <tr>
                    <th className="px-3 py-2 text-left">후보</th>
                    <th className="px-3 py-2 text-left">종류</th>
                    <th className="px-3 py-2 text-left">환경상태</th>
                    <th className="px-3 py-2 text-left">분류</th>
                    <th className="px-3 py-2 text-left">최근 측정</th>
                    <th className="px-3 py-2 text-left">국장판정</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/10">
                  {audit.candidates.map(candidate => {
                    const latest = candidate.측정이력.at(-1);
                    return (
                      <tr
                        key={candidate.candidate_id}
                        onClick={() => setSelectedCandidateId(candidate.candidate_id)}
                        className="cursor-pointer hover:bg-secondary/15"
                      >
                        <td className="px-3 py-2 font-semibold text-foreground/85">{candidate.표시명}</td>
                        <td className="px-3 py-2 font-mono text-muted-foreground/60">{candidate.evidence_kind}</td>
                        <td className="px-3 py-2">
                          <span className="border border-border/20 px-1.5 py-0.5 font-mono text-[9px]">{candidate.환경상태}</span>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex flex-wrap gap-1">
                            {candidate.분류.map(tag => (
                              <span key={tag} className="border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[9px] text-amber-200/80">{tag}</span>
                            ))}
                          </div>
                        </td>
                        <td className="px-3 py-2 font-mono text-muted-foreground/65">
                          {latest ? `${latest.회차} · ${latest.조각당ms}ms` : "측정 없음"}
                        </td>
                        <td className="px-3 py-2">{candidate.국장판정.상태}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {selectedCandidate && (
              <div className="border border-border/15 bg-secondary/10 p-4 space-y-3">
                <div>
                  <p className="text-sm font-semibold">{selectedCandidate.표시명}</p>
                  <p className="text-[10px] text-muted-foreground/60">연결 후보: {selectedCandidate.연결후보}</p>
                  {!selectedCandidate.재시도허용.value && (
                    <p className="mt-1 text-[10px] text-amber-300/75">재시도 잠금: {selectedCandidate.재시도허용.사유}</p>
                  )}
                </div>
                <div className="space-y-2">
                  {selectedCandidate.측정이력.length === 0 && (
                    <p className="text-[10px] text-muted-foreground/45">측정이력 없음</p>
                  )}
                  {selectedCandidate.측정이력.map(item => (
                    <div key={`${selectedCandidate.candidate_id}-${item.회차}`} className="border-t border-border/10 pt-2 text-[10px]">
                      <p className="font-mono text-foreground/75">{item.회차} · {item.날짜}</p>
                      <p>조건: {item.조건}</p>
                      <p>정확도: {item.정확도지표}</p>
                      <p>조각당 {item.조각당ms}ms · 83소스 {item["83소스환산초"]}초 · UNKNOWN {item.UNKNOWN비율}</p>
                      <p className="break-all text-muted-foreground/55">raw: {item.raw파일경로}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="space-y-3 border-t border-border/15 pt-4">
            <div>
              <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/55">근거 실재 점검</h2>
              <p className="mt-1 text-[10px] text-muted-foreground/45">
                config가 지목한 코드 근거 {audit.evidence_audit.checked}건 ·
                실재 {audit.evidence_audit.exists} ·
                <span className={audit.evidence_audit.missing > 0 ? "text-red-400/80 font-semibold" : ""}> 없음 {audit.evidence_audit.missing}</span> ·
                <span className={audit.evidence_audit.moved > 0 ? "text-amber-300/80" : ""}> 이동 {audit.evidence_audit.moved}</span> ·
                코드참조 아님 {audit.evidence_audit.not_a_code_ref}
              </p>
            </div>
            <div className="overflow-x-auto border border-border/15">
              <table className="w-full text-[11px]">
                <thead className="bg-secondary/20 text-muted-foreground/60">
                  <tr>
                    <th className="px-3 py-2 text-left">판정</th>
                    <th className="px-3 py-2 text-left">선언 위치</th>
                    <th className="px-3 py-2 text-left">선언된 근거</th>
                    <th className="px-3 py-2 text-left">실재 위치</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/10">
                  {audit.evidence_audit.items.map((item, index) => (
                    <tr key={`${item.field}-${index}`}>
                      <td className={`px-3 py-2 font-mono ${item.status === "MISSING" ? "text-red-400/85" : item.status === "MOVED" ? "text-amber-300/80" : "text-muted-foreground/45"}`}>
                        {item.status}
                      </td>
                      <td className="px-3 py-2 font-mono text-[9px] text-muted-foreground/60 break-all">{item.source} · {item.field}</td>
                      <td className="px-3 py-2 break-all text-foreground/70">{item.declared}</td>
                      <td className="px-3 py-2 break-all font-mono text-[9px] text-muted-foreground/60">
                        {item.found_at || item.detail || "—"}
                      </td>
                    </tr>
                  ))}
                  {audit.evidence_audit.items.length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-2 text-muted-foreground/45">전부 실재</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-3 border-t border-border/15 pt-4">
            <div>
              <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/55">장부 기록</h2>
              <p className="mt-1 text-[10px] text-muted-foreground/45">
                수리가 아니라 사실이다. 지우지 않고 쌓는다.
              </p>
            </div>
            <div className="space-y-px border border-border/15 bg-border/10">
              {(audit.ledger_records ?? []).map(record => (
                <div key={record.기록id} className="bg-background/70 p-3 space-y-1">
                  <p className="text-[11px] font-semibold text-foreground/85">
                    <span className="mr-2 border border-border/25 px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground/60">{record.회차}</span>
                    {record.제목}
                  </p>
                  <p className="text-[11px] text-foreground/70">{record.사실}</p>
                  {record.주의 && (
                    <p className="text-[10px] text-amber-300/70">주의: {record.주의}</p>
                  )}
                  <ul className="space-y-0.5">
                    {record.근거.map(item => (
                      <li key={item} className="break-all font-mono text-[9px] text-muted-foreground/50">{item}</li>
                    ))}
                  </ul>
                </div>
              ))}
              {(audit.ledger_records ?? []).length === 0 && (
                <p className="bg-background/70 p-3 text-[10px] text-muted-foreground/45">기록 없음</p>
              )}
            </div>
          </section>

          <section className="space-y-3 border-t border-border/15 pt-4">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-black tracking-widest uppercase text-muted-foreground/55">독립 Evidence</h2>
              <span className="border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[9px] text-amber-200/80">
                emotion_score · 재설계
              </span>
            </div>
            <p className="text-[10px] text-muted-foreground/50">독립 증거를 합산하지 않습니다.</p>
            <div className="grid grid-cols-2 gap-px border border-border/15 bg-border/10 sm:grid-cols-5">
              {audit.emotion_evidence.items.map(item => (
                <div key={item.id} className="bg-background/70 p-3">
                  <p className="break-all font-mono text-[10px] text-foreground/75">{item.id}</p>
                  <p className={`mt-1 text-[10px] font-semibold ${item.status === "VALUE" ? "text-emerald-400" : "text-muted-foreground/40"}`}>
                    {item.status}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <details className="border-t border-border/15 pt-4 group">
            <summary className="cursor-pointer list-none flex items-center gap-2 text-xs font-black tracking-widest uppercase text-muted-foreground/55">
              <ChevronDown size={13} className="group-open:rotate-180 transition-transform" />
              감사 원표
            </summary>
            <div className="mt-3 space-y-5">
              <MaterialTable materials={audit.materials} />
              <p className="text-[11px] text-muted-foreground/60">
                하드룰 선언 {audit.rules.declared} · 런타임 등록 {audit.rules.registered} · 보정 {audit.rules.corrective} · veto {audit.rules.veto} · veto 선언·도달 불가 {audit.rules.veto_unreachable} · ID 교집합 {audit.rules.identity_overlap}
              </p>
              <p className="text-[11px] text-muted-foreground/60">
                편집기법 선언 {audit.techniques.declared} · 실제 배선 {audit.techniques.wired}
              </p>
            </div>
          </details>
        </>
      )}
    </div>
  );
};
