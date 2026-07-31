import React, { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { fetcher } from "@/services/api";
import {
  ANATOMY_CHAT_NODES,
  ANATOMY_NODES,
  ANATOMY_STATUS,
  AnatomyNodeDefinition,
  AnatomyNodeId,
  AnatomyStatus,
} from "./adminAnatomyConfig";
import { AnatomyMap, MapLineState } from "./AnatomyMap";

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
  /** 선의 문법 (국장 확정): 실선=정상뿐 / 점선=문제 있음 / 미계측·조회실패는 둘 중 어느 것도 아니다. */
  state?: { line: "실선" | "점선" | "미계측" | "조회실패"; thickness: null; why: string; caution?: string };
  ledger_match?: { domain: string } | null;
  ledger_granularity?: { unit: string; shared_with: string[]; note: string };
  extracted: Record<string, BoundaryProbe>;
  constants?: BoundaryProbe[];
  asymmetry?: BoundaryProbe[];
  ledger: Record<string, unknown>;
}

const UNEXTRACTED = "미추출";

/** 선의 문법 — 중간이 없다. 실선은 오직 문제가 없을 때만.
 *  굵기(실패 많음 + 해결 많음 = 검증된 길)는 이번 차수 구현하지 않는다. 자리만 비워 둔다. */
const LINE_STYLE: Record<string, { border: string; text: string; label: string }> = {
  실선: { border: "border-emerald-400/70", text: "text-emerald-300", label: "정상" },
  점선: { border: "border-red-500/80 border-dashed", text: "text-red-300", label: "문제 있음" },
  미계측: { border: "border-zinc-500/60 border-dotted", text: "text-zinc-400", label: "미계측" },
  조회실패: { border: "border-amber-500/70 border-dashed", text: "text-amber-300", label: "원장 조회 실패" },
};
const lineStyle = (line?: string) => LINE_STYLE[line ?? ""] ?? LINE_STYLE["미계측"];

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
  // [MAP-R3] 선이 일급이다 — 오늘 여섯 건이 전부 선에서 났는데 선은 호버 툴팁뿐이었다.
  const [selectedEdge, setSelectedEdge] = useState<{
    from: AnatomyNodeId; to: AnatomyNodeId; label: string; evidence: string;
  } | null>(null);

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
  /** 선 상태 = 그 두 부위를 잇는 경계들의 판정. 하나라도 문제면 선은 점선이다(나쁜 쪽이 이긴다). */
  const lineStateFor = useCallback(
    (from: AnatomyNodeId, to: AnatomyNodeId): MapLineState => {
      const hit = (boundaries ?? []).filter(
        (b) => (b.from === from && b.to === to) || (b.from === to && b.to === from),
      );
      if (boundaryError) return "조회실패";
      if (hit.length === 0) return "미계측";   // 경계가 기장되지 않은 관계 — 정상이라 그리지 않는다
      const lines = hit.map((b) => b.state?.line ?? "미계측");
      for (const worst of ["조회실패", "점선", "미계측"] as const) {
        if (lines.includes(worst)) return worst;
      }
      return "실선";
    },
    [boundaries, boundaryError],
  );

  /** 크기=비중. 지표가 있는 노드만 커진다 — 모르는 것을 크게 그리지 않는다. */
  const metricFor = useCallback(
    (id: AnatomyNodeId): number | null => {
      const def = ANATOMY_NODES.find((n) => n.id === id);
      if (!def?.metricKey) return null;
      return data?.operations.metrics[def.metricKey]?.value ?? null;
    },
    [data],
  );

  /** 선 보고 — 이 선에 기장된 경계 카드에서 **읽기만** 한다. 새 계산은 없다.
   *  기장이 없으면 빈칸이 아니라 "왜 미계측인지"가 내용이다. */
  const edgeReport = useMemo(() => {
    if (!selectedEdge) return null;
    const hits = (boundaries ?? []).filter(
      (b) =>
        (b.from === selectedEdge.from && b.to === selectedEdge.to) ||
        (b.from === selectedEdge.to && b.to === selectedEdge.from),
    );
    const title = `${selectedEdge.from} → ${selectedEdge.to}`;
    if (hits.length === 0) {
      return {
        title,
        line: boundaryError ? "조회실패" : "미계측",
        kind: "기장 없음",
        why: "이 선을 지나는 값·기본값·순서·권위가 아직 감사되지 않았습니다. 감사해서 기장하기 전에는 정상이라고 그리지 않습니다.",
        order: "UNKNOWN",
        authority: "UNKNOWN",
        first: "UNKNOWN",
        latest: "UNKNOWN",
        failures: "UNKNOWN",
        caution: null as string | null,
        evidence: {
          relation: { from: selectedEdge.from, to: selectedEdge.to },
          evidence: selectedEdge.evidence,
          boundary: null,
          note: "경계 미기장 — 원장과 이을 자리가 아직 없다",
        },
      };
    }
    const b = hits[0];
    const ledger = b.ledger as Record<string, unknown>;
    return {
      title: `${title} · ${b.label}`,
      line: b.state?.line ?? "미계측",
      kind: `${b.kind}${b.user_decision_overwritten ? " · 사용자 결정 덮음" : ""}`,
      why: b.state?.why ?? "UNKNOWN",
      order: b.static.order,
      authority: b.static.authority,
      first: String(ledger?.first_occurrence ?? "UNKNOWN"),
      latest: String(ledger?.latest ?? "UNKNOWN"),
      failures: String(ledger?.failure_count ?? "UNKNOWN"),
      caution: b.state?.caution ?? null,
      evidence: hits.length === 1 ? b : hits,
    };
  }, [selectedEdge, boundaries, boundaryError]);

  const boundariesBetween = useCallback(
    (from: AnatomyNodeId, to: AnatomyNodeId) =>
      (boundaries ?? []).filter(
        (b) => (b.from === from && b.to === to) || (b.from === to && b.to === from),
      ),
    [boundaries],
  );

  /** 선을 고르면 그 선의 경계만 남기고 펼친다 — 카드는 이미 있다. 새로 만들지 않고 잇는다. */
  const nodeBoundaries = useMemo(() => {
    if (selectedEdge) return boundariesBetween(selectedEdge.from, selectedEdge.to);
    return (boundaries ?? []).filter((b) => b.from === selected.id || b.to === selected.id);
  }, [boundaries, selected, selectedEdge, boundariesBetween]);

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

      {/* [MAP-R2] 일렬 배치를 판으로 교체했다 — 위치·곡률·화살촉이 정보를 나른다.
          선의 상태는 경계 판정(LINE-STATE)에서 그대로 받아 쓴다. 여기서 재계산하지 않는다. */}
      {/* 지도와 보고를 좌우로 — 지도를 보면서 그 부위의 설명·증거를 같은 화면에서 읽는다.
          보고는 오른쪽에 위(일반 설명)·아래(기술 증거)로 쌓인다. */}
      <section
        className="grid gap-5 py-2 lg:grid-cols-[minmax(0,1fr)_minmax(300px,26rem)]"
        aria-label="CCUT 흐름 지도"
      >
        <div className="min-w-0 overflow-x-auto">
          <AnatomyMap
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              setSelectedEdge(null);   // 부위를 고르면 선 선택은 풀린다
            }}
            selectedEdge={selectedEdge}
            onSelectEdge={(rel) => {
              const hit = boundariesBetween(rel.from, rel.to);
              setSelectedEdge({
                from: rel.from, to: rel.to,
                label: `${rel.kind === "bidir" ? "⇄" : "→"} ${rel.evidence.split(" ")[0]}`,
                evidence: rel.evidence,
              });
              setOpenBoundaryId(hit[0]?.id ?? null);   // 한 건이면 바로 펼친다
            }}
            hasBoundary={(from, to) => boundariesBetween(from, to).length > 0}
            subtitleFor={(id) => {
              // 편집연구실이 "930 · 조각 단위"를 적는 자리 — 실값이 우선이다.
              const def = ANATOMY_NODES.find((n) => n.id === id);
              const v = def?.metricKey ? data?.operations.metrics[def.metricKey]?.value : null;
              if (v != null) return `${v.toLocaleString()} · ${def?.metricLabel ?? ""}`.trim();
              // 지표가 없는 부위는 이 부위에 닿는 **기장된 경계 수**가 실값이다.
              const n = (boundaries ?? []).filter((b) => b.from === id || b.to === id).length;
              return n > 0 ? `경계 ${n} · 감사됨` : "경계 0 · 미감사";
            }}
            lockedFor={(id) => {
              // 잠김 = 지표를 가져야 하는데 못 읽은 부위. 그 외엔 자물쇠를 달지 않는다.
              const def = ANATOMY_NODES.find((n) => n.id === id);
              if (!def?.metricKey) return false;
              return (data?.operations.metrics[def.metricKey]?.value ?? null) == null;
            }}
            lineStateFor={lineStateFor}
            metricFor={metricFor}
            statusLabelFor={(id) => ANATOMY_STATUS[nodeStatus(id, data)]?.label ?? "미계측"}
          />
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[9px] text-muted-foreground/55">
            <span>왼쪽 = 사용자의 말 · 가운데 = 재료의 본선 · 오른쪽 = 곁가지</span>
            <span className="text-fuchsia-300/80">보라 = 되돌아감(재승인)</span>
            <span className="text-sky-300/80">하늘 = 왕복</span>
            <span>선을 누르면 경계 카드</span>
          </div>
        </div>
        {/* 지도 오른쪽 보고 — 위: 일반 설명, 아래: 기술 증거 */}
        <aside className="flex min-w-0 flex-col gap-5 border-l border-border/15 pl-5">
        {selectedEdge ? (
          // 선을 골랐으면 **선의** 설명과 증거다. 문제는 늘 선에서 나므로 여기가 본체다.
          <>
            <div>
              <p className="text-[10px] font-bold uppercase text-muted-foreground/45">
                일반 설명 — 선
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <h2 className="text-base font-bold text-foreground/90">
                  {edgeReport.title}
                </h2>
                <span className={`border px-1.5 py-0.5 text-[9px] ${lineStyle(edgeReport.line).border} ${lineStyle(edgeReport.line).text}`}>
                  {edgeReport.line}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-foreground/70">
                {edgeReport.why}
              </p>
              <dl className="mt-5 grid grid-cols-[92px_1fr] gap-x-3 gap-y-2 text-[11px]">
                <dt className="text-muted-foreground/45">관계</dt>
                <dd className="text-foreground/70">{edgeReport.kind}</dd>
                <dt className="text-muted-foreground/45">근거</dt>
                <dd className="break-words font-mono text-[10px] text-foreground/65">
                  {selectedEdge.evidence}
                </dd>
                <dt className="text-muted-foreground/45">★순서</dt>
                <dd className="text-foreground/70">{edgeReport.order}</dd>
                <dt className="text-muted-foreground/45">★권위</dt>
                <dd className="text-foreground/70">{edgeReport.authority}</dd>
                <dt className="text-muted-foreground/45">최초 발생</dt>
                <dd className="font-mono text-foreground/65">{edgeReport.first}</dd>
                <dt className="text-muted-foreground/45">최근</dt>
                <dd className="font-mono text-foreground/65">{edgeReport.latest}</dd>
                <dt className="text-muted-foreground/45">실패</dt>
                <dd className="font-mono text-foreground/65">{edgeReport.failures}</dd>
              </dl>
              {edgeReport.caution && (
                <p className="mt-3 border border-amber-500/40 bg-amber-500/5 px-2 py-1.5 text-[10px] text-amber-200/85">
                  주의: {edgeReport.caution}
                </p>
              )}
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase text-muted-foreground/45">
                기술 증거 — 선
              </p>
              <pre className="mt-3 max-h-96 overflow-auto border border-border/20 bg-black/20 p-3 text-[10px] leading-5 text-cyan-100/70">
                {JSON.stringify(edgeReport.evidence, null, 2)}
              </pre>
            </div>
          </>
        ) : (
        <>
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
        </>
        )}
        </aside>
      </section>

      {/* [BOUNDARY-MAP] 노드 클릭 -> 그 노드에 닿는 **경계(화살표)** 확대.
          노드보다 화살표가 주인공이므로 여기가 화면의 중심이다. */}
      <section className="border-t border-border/20 pt-5" aria-label="경계 확대 보기">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-[10px] font-bold uppercase text-muted-foreground/45">
            {selectedEdge
              ? `선 — ${selectedEdge.from} → ${selectedEdge.to}`
              : `경계 — ${selected.label}에 닿는 화살표`}
          </p>
          <p className="text-[9px] text-muted-foreground/40">
            사고는 노드 안이 아니라 노드 사이에서 난다
          </p>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
          {(["실선", "점선", "미계측", "조회실패"] as const).map((k) => (
            <span key={k} className="flex items-center gap-1.5 text-[9px]">
              <span className={`w-6 border-t-2 ${LINE_STYLE[k].border}`} aria-hidden />
              <span className={`font-semibold ${LINE_STYLE[k].text}`}>{k}</span>
              <span className="text-muted-foreground/45">{LINE_STYLE[k].label}</span>
            </span>
          ))}
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
            {nodeBoundaries.length === 0 && selectedEdge && (
              // 빈 카드를 내놓지 않는다 — 왜 미계측인지가 카드의 내용이다.
              <div className="border border-zinc-500/50 border-dotted p-3">
                <p className="text-xs font-bold text-zinc-300">🔒 미계측 — 아직 경계가 기장되지 않은 선</p>
                <dl className="mt-2 grid grid-cols-[64px_1fr] gap-x-3 gap-y-1.5 text-[10px]">
                  <dt className="text-muted-foreground/45">관계</dt>
                  <dd className="font-mono text-foreground/70">
                    {selectedEdge.from} → {selectedEdge.to}
                  </dd>
                  <dt className="text-muted-foreground/45">근거</dt>
                  <dd className="text-foreground/70">{selectedEdge.evidence}</dd>
                  <dt className="text-muted-foreground/45">왜 미계측</dt>
                  <dd className="text-foreground/70">
                    이 선을 지나는 값·기본값·순서·권위가 아직 감사되지 않았습니다.
                    감사해서 기장하기 전에는 정상이라고 그리지 않습니다.
                  </dd>
                </dl>
              </div>
            )}
            {nodeBoundaries.length === 0 && !selectedEdge && (
              <p className="text-xs text-muted-foreground/55">
                이 부위에 기장된 경계가 없습니다 — 없는 것은 UNKNOWN, 채워 넣지 않습니다.
              </p>
            )}
            {nodeBoundaries.map((b) => {
              const open = openBoundaryId === b.id;
              const danger = b.user_decision_overwritten;
              const ls = lineStyle(b.state?.line);
              return (
                <div key={b.id} className="border border-border/20">
                  <button
                    type="button"
                    onClick={() => setOpenBoundaryId(open ? null : b.id)}
                    title={b.state?.why}
                    className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left transition-colors hover:bg-secondary/25"
                  >
                    {/* 선 자체가 상태다 — 실선이면 정상, 점선이면 문제. 중간은 없다. */}
                    <span className={`w-10 shrink-0 border-t-2 ${ls.border}`} aria-hidden />
                    <span className={`text-[9px] font-bold ${ls.text}`}>{b.state?.line ?? "미계측"}</span>
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
                        <p className={`mt-2 border px-2 py-1.5 text-[10px] ${ls.border} ${ls.text}`}>
                          선 판정: <b>{b.state?.line ?? "미계측"}</b> — {b.state?.why ?? "UNKNOWN"}
                        </p>
                        {b.state?.caution && (
                          <p className="mt-1 border border-amber-500/40 bg-amber-500/5 px-2 py-1.5 text-[10px] text-amber-200/85">
                            주의: {b.state.caution}
                          </p>
                        )}
                        {b.ledger_granularity && b.ledger_granularity.shared_with.length > 0 && (
                          <p className="mt-1 text-[9px] text-muted-foreground/50">
                            판정 해상도: {b.ledger_granularity.unit} — 같은 도메인 경계
                            {" "}{b.ledger_granularity.shared_with.join(", ")} 와 함께 움직입니다
                          </p>
                        )}
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

    </div>
  );
};
