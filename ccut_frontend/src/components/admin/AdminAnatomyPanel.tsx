import React, { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { fetcher } from "@/services/api";
import {
  ANATOMY_EDGES,
  ANATOMY_NODES,
  ANATOMY_STATUS,
  AnatomyNodeDefinition,
  AnatomyNodeId,
  AnatomyStatus,
} from "./adminAnatomyConfig";

interface ProjectSummary {
  program_id: string;
  name: string;
}

interface SourcedMetric {
  value: number | null;
  source: string;
}

interface AnatomyPayload {
  status: string;
  gate: { enabled: boolean; value: string };
  project: { program_id: string; name: string | null };
  operations: {
    source: string;
    generated_at: string | null;
    metrics: Record<string, SourcedMetric>;
    alerts: unknown[];
  };
  capability: {
    source: string;
    audited_at: string | null;
    edges: unknown;
  };
  dialogue_edit: {
    state_source: string;
    receipt_source: string;
    state_read: "OK" | "UNKNOWN";
    receipt_read: "OK" | "UNKNOWN";
    states: unknown[];
    receipts: unknown[];
    error?: string;
  };
  qwen: {
    source: string;
    read: "OK" | "UNKNOWN";
    generation: Record<string, unknown> | null;
    rough_cut_created_at: string | null;
    first_occurrence: "UNKNOWN";
    latest_success: "UNKNOWN";
    retry_count: "UNKNOWN";
    error?: string;
  };
}

/** [BOUNDARY-MAP] 경계 카드 — 오늘 잡은 여섯 건이 전부 노드가 아니라 **노드 사이**에서 났다.
 *  새 탭을 만들지 않는다(절벽 ①): anatomy 안의 확대다. 노드보다 화살표가 주인공이다. */
interface BoundaryProbe {
  value: unknown;
  where?: string;
  why?: string;
  label?: string;
  side?: string;
}
interface BoundaryCard {
  id: string;
  from: AnatomyNodeId;
  to: AnatomyNodeId;
  label: string;
  kind: string;
  found: string;
  status: string;
  fixed_by: string;
  user_decision_overwritten: boolean;
  static: { order: string; authority: string; source: string };
  extracted: Record<string, BoundaryProbe>;
  constants?: BoundaryProbe[];
  asymmetry?: BoundaryProbe[];
  ledger: Record<string, unknown>;
}

const UNEXTRACTED = "미추출";

const probeText = (p: BoundaryProbe) =>
  p.value === UNEXTRACTED || p.value == null ? UNEXTRACTED : String(p.value);

/** 미추출은 점선·흐림으로. 채워 넣지 않는다(절벽 ③⑤). */
const probeClass = (p: BoundaryProbe) =>
  probeText(p) === UNEXTRACTED
    ? "border-dashed border-zinc-500/50 text-zinc-500"
    : "border-border/20 text-cyan-100/75";

const BoundaryRow: React.FC<{ name: string; probe: BoundaryProbe }> = ({ name, probe }) => (
  <div className={`border px-2 py-1.5 ${probeClass(probe)}`}>
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-[10px] font-bold text-foreground/70">{name}</span>
      <span className="shrink-0 font-mono text-[8px] text-muted-foreground/50">
        {probe.where ?? "UNKNOWN"}
      </span>
    </div>
    <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-4">
      {probeText(probe)}
      {probe.why ? `  (${probe.why})` : ""}
    </pre>
  </div>
);

const STATUS_STYLE: Record<AnatomyStatus, string> = {
  normal: "border-emerald-500/55 bg-emerald-500/10 text-emerald-200",
  slow: "border-amber-500/55 bg-amber-500/10 text-amber-200",
  broken: "border-red-500/60 bg-red-500/10 text-red-200",
  idle: "border-zinc-500/50 bg-zinc-500/10 text-zinc-300",
  processing: "border-cyan-500/55 bg-cyan-500/10 text-cyan-200",
  unmeasured: "border-zinc-500/60 border-dashed bg-transparent text-zinc-300",
};

function dialogueEditStatus(data: AnatomyPayload | null): AnatomyStatus {
  const slice = data?.dialogue_edit;
  if (!slice || slice.state_read !== "OK" || slice.receipt_read !== "OK") {
    return "unmeasured";
  }
  if (slice.states.length === 0 && slice.receipts.length === 0) return "idle";
  if (slice.states.length > 0 && slice.receipts.length > 0) return "normal";
  return "broken";
}

function qwenStatus(data: AnatomyPayload | null): AnatomyStatus {
  const slice = data?.qwen;
  if (!slice || slice.read !== "OK") return "unmeasured";
  if (!slice.generation) {
    return slice.rough_cut_created_at ? "unmeasured" : "idle";
  }
  const reason = String(slice.generation.reason ?? "");
  if (/failed|exhausted|ungrounded|not_shortened/i.test(reason)) return "broken";
  return slice.generation.kind ? "normal" : "unmeasured";
}

function nodeStatus(id: AnatomyNodeId, data: AnatomyPayload | null): AnatomyStatus {
  if (id === "edit") return dialogueEditStatus(data);
  if (id === "story") return qwenStatus(data);
  return "unmeasured";
}

function technicalEvidence(node: AnatomyNodeDefinition, data: AnatomyPayload | null) {
  if (!data) return { status: "UNKNOWN" };
  if (node.id === "edit") return data.dialogue_edit;
  if (node.id === "story") return data.qwen;
  if (node.metricKey) {
    return {
      operations_source: data.operations.source,
      metric: data.operations.metrics[node.metricKey] ?? "UNKNOWN",
      generated_at: data.operations.generated_at,
      alerts: data.operations.alerts,
    };
  }
  if (["transcript", "fragment", "render"].includes(node.id)) {
    return {
      capability_source: data.capability.source,
      audited_at: data.capability.audited_at,
      note: "능력 상태를 흐름 상태로 재판정하지 않음",
    };
  }
  return {
    status: "UNKNOWN",
    reason: "이 단계의 현재 흐름을 증명하는 영속 영수증이 없음",
  };
}

const FlowConnector: React.FC<{ index: number }> = ({ index }) => {
  const edge = ANATOMY_EDGES[index];
  return (
    <div className="relative flex h-10 w-full items-center justify-center lg:h-auto lg:w-12 lg:flex-none">
      <div
        className={`h-full border-l-2 lg:h-0 lg:w-full lg:border-l-0 lg:border-t-2 ${
          edge.declared ? "border-emerald-500/45" : "border-zinc-500/55 border-dashed"
        }`}
      />
      {!edge.declared && (
        <span className="absolute bg-[hsl(228_12%_9%)] px-1 text-[8px] font-bold text-zinc-500">
          UNDECLARED
        </span>
      )}
    </div>
  );
};

export const AdminAnatomyPanel: React.FC = () => {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [programId, setProgramId] = useState("");
  const [data, setData] = useState<AnatomyPayload | null>(null);
  const [selectedId, setSelectedId] = useState<AnatomyNodeId>("story");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // [BOUNDARY-MAP] 확대 보기 — 탭이 아니라 이 화면 안에서 펼친다.
  const [boundaries, setBoundaries] = useState<BoundaryCard[] | null>(null);
  const [boundaryError, setBoundaryError] = useState<string | null>(null);
  const [openBoundaryId, setOpenBoundaryId] = useState<string | null>(null);

  useEffect(() => {
    fetcher("/admin/anatomy/boundaries")
      .then((r) => setBoundaries((r.boundaries ?? []) as BoundaryCard[]))
      .catch((reason) => {
        setBoundaries(null);
        setBoundaryError(String(reason));
      });
  }, []);

  useEffect(() => {
    fetcher("/projects")
      .then((response) => {
        const next = (response.projects ?? []) as ProjectSummary[];
        setProjects(next);
        setProgramId((current) => current || next[0]?.program_id || "");
        if (next.length === 0) setLoading(false);
      })
      .catch((reason) => {
        setError(String(reason));
        setLoading(false);
      });
  }, []);

  const load = useCallback(async () => {
    if (!programId) return;
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetcher(`/admin/anatomy/project/${encodeURIComponent(programId)}`),
      );
    } catch (reason) {
      setData(null);
      setError(String(reason));
    } finally {
      setLoading(false);
    }
  }, [programId]);

  useEffect(() => {
    load();
  }, [load]);

  const selected =
    ANATOMY_NODES.find((node) => node.id === selectedId) ?? ANATOMY_NODES[0];
  const selectedStatus = nodeStatus(selected.id, data);
  const related = useMemo(
    () =>
      selected.related
        .map((id) => ANATOMY_NODES.find((node) => node.id === id)?.label)
        .filter(Boolean),
    [selected],
  );
  const qwen = data?.qwen;
  // 선택 노드에 **닿는** 경계 — 나가는 것만이 아니라 들어오는 것도 그 부위의 사고다.
  const nodeBoundaries = useMemo(
    () => (boundaries ?? []).filter((b) => b.from === selected.id || b.to === selected.id),
    [boundaries, selected],
  );

  return (
    <div className="space-y-6">
      <p className="border-b border-cyan-500/20 pb-2 text-[11px] font-semibold text-cyan-200/80">
        /admin/anatomy ── 흐름 축: 데이터가 어디를 지나 어디서 멈추는가
      </p>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-foreground/90">생체 관제실</h1>
          <p className="mt-0.5 text-[11px] text-muted-foreground/55">
            실제 원장과 API가 증명한 흐름만 표시
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`border px-2 py-1 text-[10px] font-bold ${
              data?.gate.enabled
                ? "border-emerald-500/40 text-emerald-300"
                : "border-zinc-500/40 text-zinc-400"
            }`}
          >
            GATE {data?.gate.enabled ? "ON" : "OFF"}
          </span>
          <select
            aria-label="관측 프로젝트"
            value={programId}
            onChange={(event) => setProgramId(event.target.value)}
            className="h-8 min-w-52 border border-border/25 bg-secondary/20 px-2 text-xs text-foreground/80 outline-none focus:border-cyan-500/50"
          >
            {projects.map((project) => (
              <option key={project.program_id} value={project.program_id}>
                {project.name || project.program_id}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={load}
            disabled={loading || !programId}
            title="다시 조회"
            aria-label="다시 조회"
            className="grid h-8 w-8 place-items-center border border-border/25 text-muted-foreground/70 hover:bg-secondary/30 hover:text-foreground disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && (
        <p className="border border-red-500/35 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          관측 실패: {error}
        </p>
      )}
      {!programId && !error && (
        <p className="text-xs text-muted-foreground/55">관측할 프로젝트가 없습니다.</p>
      )}

      <div className="flex flex-wrap gap-x-4 gap-y-2 border-y border-border/15 py-3">
        {(Object.keys(ANATOMY_STATUS) as AnatomyStatus[]).map((status) => (
          <div key={status} className="flex items-center gap-1.5 text-[10px]">
            <span
              className={`h-2.5 w-2.5 border ${
                status === "unmeasured" ? "border-dashed" : ""
              } ${STATUS_STYLE[status]}`}
            />
            <span className="font-semibold text-foreground/70">
              {ANATOMY_STATUS[status].label}
            </span>
            <span className="text-muted-foreground/45">
              {ANATOMY_STATUS[status].meaning}
            </span>
          </div>
        ))}
      </div>

      <section className="overflow-x-auto py-2" aria-label="CCUT 제작 흐름">
        <div className="flex min-w-0 flex-col items-stretch lg:min-w-[1180px] lg:flex-row lg:items-center">
          {ANATOMY_NODES.map((node, index) => {
            const status = nodeStatus(node.id, data);
            const metric = node.metricKey
              ? data?.operations.metrics[node.metricKey]
              : null;
            return (
              <React.Fragment key={node.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(node.id)}
                  className={`min-h-28 w-full flex-none border p-3 text-left transition-colors lg:w-32 ${
                    STATUS_STYLE[status]
                  } ${selectedId === node.id ? "ring-1 ring-cyan-300/70" : ""}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-sm font-bold">{node.label}</span>
                    <span className="text-[9px] font-semibold">
                      {ANATOMY_STATUS[status].label}
                    </span>
                  </span>
                  {node.metricKey && (
                    <span className="mt-3 block text-[11px] font-semibold text-foreground/80">
                      {node.metricLabel}{" "}
                      {metric?.value == null ? "UNKNOWN" : metric.value.toLocaleString()}
                    </span>
                  )}
                  {node.metricKey && (
                    <span className="mt-1 block break-words text-[8px] leading-3 text-muted-foreground/55">
                      출처: {metric?.source ?? "UNKNOWN"}
                    </span>
                  )}
                  {node.id === "story" && (
                    <span className="mt-3 block text-[9px] leading-4 text-muted-foreground/70">
                      kind: {String(qwen?.generation?.kind ?? "UNKNOWN")}
                      <br />
                      reason: {String(qwen?.generation?.reason ?? "UNKNOWN")}
                    </span>
                  )}
                </button>
                {index < ANATOMY_EDGES.length && <FlowConnector index={index} />}
              </React.Fragment>
            );
          })}
        </div>
      </section>

      {/* [BOUNDARY-MAP] 노드 클릭 -> 그 노드에 닿는 **경계(화살표)** 확대.
          노드보다 화살표가 주인공이므로 여기가 화면의 중심이다. */}
      <section className="border-t border-border/20 pt-5" aria-label="경계 확대 보기">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-[10px] font-bold uppercase text-muted-foreground/45">
            경계 — {selected.label}에 닿는 화살표
          </p>
          <p className="text-[9px] text-muted-foreground/40">
            사고는 노드 안이 아니라 노드 사이에서 난다
          </p>
        </div>

        {boundaryError && (
          <p className="mt-3 border border-red-500/35 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            경계 지도 조회 실패: {boundaryError}
          </p>
        )}
        {!boundaryError && boundaries === null && (
          <p className="mt-3 text-xs text-muted-foreground/55">경계 지도 UNKNOWN — 아직 읽지 못함</p>
        )}

        {boundaries !== null && (
          <div className="mt-3 space-y-2">
            {nodeBoundaries.length === 0 && (
              <p className="text-xs text-muted-foreground/55">
                이 부위에 기장된 경계가 없습니다 — 없는 것은 UNKNOWN, 채워 넣지 않습니다.
              </p>
            )}
            {nodeBoundaries.map((b) => {
              const open = openBoundaryId === b.id;
              const danger = b.user_decision_overwritten;
              return (
                <div key={b.id} className="border border-border/20">
                  <button
                    type="button"
                    onClick={() => setOpenBoundaryId(open ? null : b.id)}
                    className={`flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left transition-colors hover:bg-secondary/25 ${
                      danger ? "border-l-4 border-l-red-500/70" : "border-l-4 border-l-emerald-500/50"
                    }`}
                  >
                    <span className="font-mono text-[10px] text-muted-foreground/55">
                      {b.from} → {b.to}
                    </span>
                    <span className="text-xs font-bold text-foreground/85">{b.label}</span>
                    <span className={`border px-1.5 py-0.5 text-[9px] font-semibold ${
                      danger ? "border-red-500/50 text-red-300" : "border-zinc-500/40 text-zinc-400"
                    }`}>
                      {b.kind}
                    </span>
                    {danger && (
                      <span className="text-[9px] font-bold text-red-300">사용자 결정 덮음</span>
                    )}
                    <span className="ml-auto font-mono text-[9px] text-muted-foreground/45">
                      {b.status === "fixed" ? `수리 ${b.fixed_by}` : b.status}
                    </span>
                  </button>

                  {open && (
                    <div className="grid gap-4 border-t border-border/15 bg-black/15 p-3 lg:grid-cols-2">
                      <div className="space-y-2">
                        <p className="text-[9px] font-bold uppercase text-muted-foreground/45">
                          정적 (코드에서) — 발견: {b.found}
                        </p>
                        <div className="border border-amber-500/30 px-2 py-1.5">
                          <span className="text-[10px] font-bold text-amber-200/80">★순서</span>
                          <p className="mt-1 text-[10px] leading-4 text-foreground/70">{b.static.order}</p>
                        </div>
                        <div className="border border-amber-500/30 px-2 py-1.5">
                          <span className="text-[10px] font-bold text-amber-200/80">★권위</span>
                          <p className="mt-1 text-[10px] leading-4 text-foreground/70">{b.static.authority}</p>
                        </div>
                        <p className="text-[8px] text-muted-foreground/40">
                          출처: {b.static.source} — 자동 추출 불가 항목
                        </p>
                        {Object.entries(b.extracted).map(([name, probe]) => (
                          <BoundaryRow key={name} name={name} probe={probe} />
                        ))}
                        {b.constants && b.constants.length > 0 && (
                          <div className="border border-cyan-500/25 p-2">
                            <p className="text-[10px] font-bold text-cyan-200/80">
                              ★상수 나란히 보기
                            </p>
                            <div className="mt-1.5 space-y-1">
                              {b.constants.map((c, i) => (
                                <div key={i} className="flex items-baseline justify-between gap-2 text-[10px]">
                                  <span className="text-foreground/70">{c.label}</span>
                                  <span className="font-mono text-cyan-100/80">{probeText(c)}</span>
                                  <span className="shrink-0 font-mono text-[8px] text-muted-foreground/45">
                                    {c.where}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {b.asymmetry && b.asymmetry.length > 0 && (
                          <div className="border border-fuchsia-500/30 p-2">
                            <p className="text-[10px] font-bold text-fuchsia-200/80">
                              ★비대칭 — 같은 계열 두 자리 대조
                            </p>
                            <div className="mt-1.5 space-y-1.5">
                              {b.asymmetry.map((a, i) => (
                                <div key={i}>
                                  <div className="flex items-baseline justify-between gap-2">
                                    <span className="text-[10px] font-bold text-foreground/70">{a.side}</span>
                                    <span className="font-mono text-[8px] text-muted-foreground/45">{a.where}</span>
                                  </div>
                                  <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-fuchsia-100/70">
                                    {probeText(a)}
                                  </pre>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="min-w-0">
                        <p className="text-[9px] font-bold uppercase text-muted-foreground/45">
                          원장 (failure_ledger)
                        </p>
                        <pre className="mt-2 max-h-72 overflow-auto border border-border/20 bg-black/25 p-2 text-[10px] leading-5 text-cyan-100/70">
                          {JSON.stringify(b.ledger, null, 2)}
                        </pre>
                        <p className="mt-1 text-[8px] text-muted-foreground/40">
                          원장이 비면 UNKNOWN — 실패가 없었다는 뜻이 아닙니다. 첫 행이 들어오면 채워집니다.
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="grid gap-6 border-t border-border/20 pt-5 lg:grid-cols-[minmax(240px,0.8fr)_minmax(0,1.4fr)]">
        <div>
          <p className="text-[10px] font-bold uppercase text-muted-foreground/45">
            일반 설명
          </p>
          <div className="mt-3 flex items-center gap-2">
            <h2 className="text-base font-bold text-foreground/90">{selected.label}</h2>
            <span className={`border px-1.5 py-0.5 text-[9px] ${STATUS_STYLE[selectedStatus]}`}>
              {ANATOMY_STATUS[selectedStatus].label}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-foreground/70">
            {selected.description}
          </p>
          <dl className="mt-5 grid grid-cols-[92px_1fr] gap-x-3 gap-y-2 text-[11px]">
            <dt className="text-muted-foreground/45">관련 부위</dt>
            <dd className="text-foreground/70">{related.join(" · ") || "UNKNOWN"}</dd>
            <dt className="text-muted-foreground/45">최초 발생</dt>
            <dd className="font-mono text-foreground/65">
              {selected.id === "story" ? qwen?.first_occurrence ?? "UNKNOWN" : "UNKNOWN"}
            </dd>
            <dt className="text-muted-foreground/45">최근 성공</dt>
            <dd className="font-mono text-foreground/65">
              {selected.id === "story" ? qwen?.latest_success ?? "UNKNOWN" : "UNKNOWN"}
            </dd>
            <dt className="text-muted-foreground/45">재시도</dt>
            <dd className="font-mono text-foreground/65">
              {selected.id === "story" ? qwen?.retry_count ?? "UNKNOWN" : "UNKNOWN"}
            </dd>
          </dl>
        </div>

        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase text-muted-foreground/45">
            기술 증거
          </p>
          <pre className="mt-3 max-h-80 overflow-auto border border-border/20 bg-black/20 p-3 text-[10px] leading-5 text-cyan-100/70">
            {JSON.stringify(technicalEvidence(selected, data), null, 2)}
          </pre>
        </div>
      </section>
    </div>
  );
};
