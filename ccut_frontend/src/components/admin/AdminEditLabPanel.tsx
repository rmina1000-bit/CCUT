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
}

type EdgeStatus = "LIVE" | "LOCKED" | "BROKEN" | "UNDECLARED";

interface RuleAudit {
  id: string;
  declared_in: string | null;
  registered: boolean;
  checks_materials: string[] | "UNDECLARED";
  evidence: string | null;
}

interface TechniqueAudit {
  id: string;
  wired: boolean;
  declared_in: string | null;
  requires_materials: string[] | "UNDECLARED";
  requires_rules: string[] | "UNDECLARED";
  failure_check: string | null;
}

interface AuditEdge {
  from: string;
  to: string;
  kind: "material→rule" | "material→technique" | "rule→technique" | "technique→verify";
  status: EdgeStatus;
  evidence: string | null;
}

interface LabAudit {
  audited_at: string;
  duration_ms: number;
  materials: MaterialAudit[];
  rules: {
    declared: number;
    registered: number;
    unregistered: number;
    registered_ids: string[];
    items: RuleAudit[];
  };
  techniques: {
    declared: number;
    wired: number;
    wired_ids: string[];
    items: TechniqueAudit[];
  };
  edges: AuditEdge[];
}

const STATUS_STYLE: Record<EdgeStatus, { stroke: string; dash?: string; label: string }> = {
  LIVE: { stroke: "#34d399", label: "LIVE" },
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
          <th className="px-3 py-2 text-right font-semibold">보유</th>
          <th className="px-3 py-2 text-right font-semibold">구분값</th>
          <th className="px-3 py-2 text-right font-semibold">읽는 곳</th>
          <th className="px-3 py-2 text-right font-semibold">만드는 곳</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border/10">
        {materials.map(item => (
          <tr key={item.id} className="hover:bg-secondary/10">
            <td className="px-3 py-2 text-foreground/85">{item.label}</td>
            <td className="px-3 py-2 text-right font-mono">{item.non_null}/{item.total}</td>
            <td className="px-3 py-2 text-right font-mono">{item.distinct || "—"}</td>
            <td className="px-3 py-2 text-right font-mono">{item.consumer_count}</td>
            <td className="px-3 py-2 text-right font-mono">{item.producer_count}</td>
          </tr>
        ))}
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
        fill={status === "LIVE" ? "#102820" : status === "BROKEN" ? "#291a12" : "#171a20"}
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
          return (
            <Node
              key={item.id}
              x={colX[0]} y={rowY(index)}
              title={item.label}
              subtitle={`${item.non_null}/${item.total} · 구분 ${item.distinct || 0}`}
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
            subtitle={item.registered ? "검사기 등록" : "미등록 · 관계 미선언"}
            status={item.registered ? "LIVE" : "BROKEN"}
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

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-foreground/90">편집연구실</h1>
          <p className="text-[11px] text-muted-foreground/50 mt-0.5">
            {audit
              ? `재료 ${audit.materials.length - missingMaterials} 값 있음 / ${missingMaterials} 값 없음 · 하드룰 ${audit.rules.declared} 선언 / ${audit.rules.registered} 등록 · 기법 ${audit.techniques.declared} 선언 / ${audit.techniques.wired} 배선`
              : "측정 결과 없음"}
          </p>
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
                <p className="text-sm font-semibold">{selectedMaterial.label} {selectedMaterial.non_null}/{selectedMaterial.total}</p>
                <p>구분값 {selectedMaterial.distinct} · producers {selectedMaterial.producer_count} · consumers {selectedMaterial.consumer_count}</p>
                <p className="text-muted-foreground/60 break-all">producers: {selectedMaterial.producers.join(" / ") || "없음"}</p>
                <p className="text-muted-foreground/60 break-all">consumers: {selectedMaterial.consumers.join(" / ") || "없음"}</p>
                <p>{selectedMaterial.non_null === 0
                  ? `${selectedMaterial.label} ${selectedMaterial.non_null}/${selectedMaterial.total} → 생산기 없음 → 명시적으로 요구하는 하위 기법 잠김`
                  : `${selectedMaterial.label} 값이 존재하며 선언 또는 코드 참조가 있는 관계만 표시합니다.`}</p>
              </div>
            )}
            {selectedRule && (
              <div className="space-y-1 text-[11px]">
                <p className="text-sm font-semibold">{selectedRule.id}</p>
                <p>{selectedRule.registered ? "검사기 등록" : "검사기 미등록"} · 검사 재료 {Array.isArray(selectedRule.checks_materials) ? selectedRule.checks_materials.join(", ") : "관계 미선언"}</p>
                <p className="text-muted-foreground/60 break-all">근거: {selectedRule.evidence || selectedRule.declared_in || "없음"}</p>
              </div>
            )}
            {selectedTechnique && (
              <div className="space-y-1 text-[11px]">
                <p className="text-sm font-semibold">{selectedTechnique.id}</p>
                <p>{selectedTechnique.wired ? "실제 배선" : "미배선"} · 요구 재료 {Array.isArray(selectedTechnique.requires_materials) ? selectedTechnique.requires_materials.join(", ") : "관계 미선언"}</p>
                <p>요구 룰 {Array.isArray(selectedTechnique.requires_rules) ? selectedTechnique.requires_rules.join(", ") : "관계 미선언"}</p>
                <p className="text-muted-foreground/60 break-all">근거: {selectedTechnique.declared_in || "없음"}</p>
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

          <details className="border-t border-border/15 pt-4 group">
            <summary className="cursor-pointer list-none flex items-center gap-2 text-xs font-black tracking-widest uppercase text-muted-foreground/55">
              <ChevronDown size={13} className="group-open:rotate-180 transition-transform" />
              감사 원표
            </summary>
            <div className="mt-3 space-y-5">
              <MaterialTable materials={audit.materials} />
              <p className="text-[11px] text-muted-foreground/60">
                하드룰 선언 {audit.rules.declared} · 검사기 등록 {audit.rules.registered} · 미등록 {audit.rules.unregistered}
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
