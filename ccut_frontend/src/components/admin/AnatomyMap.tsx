import React, { useMemo } from "react";
import {
  ANATOMY_CANVAS,
  ANATOMY_CHAT_NODES,
  ANATOMY_NODES,
  ANATOMY_PLACEMENT,
  ANATOMY_RELATIONS,
  AnatomyNodeId,
  AnatomyRelation,
  AnatomyRelationKind,
} from "./adminAnatomyConfig";

/**
 * [MAP-R2] 흐름 지도 — 시간표가 아니라 지도.
 *
 * 왜 다시 그리는가: 노드 8개를 왼쪽에서 오른쪽으로 한 줄 세우면 위치가 아무 정보도
 * 나르지 못한다. 되돌아가는 길도 왕복하는 길도 갈라지는 길도 그릴 자리가 없다.
 * 그래서 오늘 감사한 결함 중 넷(채팅 계열)은 지도에 존재조차 하지 않았다.
 *
 * 모든 시각 속성이 데이터를 나른다 (Vizceral 에서 가져온 원칙, 입자·물리는 가져오지 않음):
 *   위치   어느 세계의 것인가 (말 / 본선 / 곁가지)
 *   곡률   방향 — 되돌아가는 길은 본선 아래로 부푼다. 순방향과 절대 겹치지 않는다.
 *   화살촉 방향. 왕복은 양쪽에 달린다.
 *   선 모양 실선=정상 / 점선=문제 (LINE-STATE 판정 그대로 받아 쓴다 — 여기서 재계산하지 않는다)
 *   크기   비중 (지표가 있는 노드만 커진다)
 * 입자 애니메이션은 넣지 않는다 — 흐를 트래픽이 없다. 흉내 내면 장식이다.
 */

export type MapLineState = "실선" | "점선" | "미계측" | "조회실패";

const BAND_STYLE: Record<string, { fill: string; stroke: string; text: string }> = {
  chat: { fill: "rgba(56,189,248,0.10)", stroke: "rgba(56,189,248,0.55)", text: "#bae6fd" },
  main: { fill: "rgba(16,185,129,0.10)", stroke: "rgba(16,185,129,0.5)", text: "#d1fae5" },
  aside: { fill: "rgba(161,161,170,0.08)", stroke: "rgba(161,161,170,0.45)", text: "#e4e4e7" },
};

const LINE_COLOR: Record<MapLineState, string> = {
  실선: "rgba(16,185,129,0.75)",
  점선: "rgba(239,68,68,0.9)",
  미계측: "rgba(161,161,170,0.5)",
  조회실패: "rgba(245,158,11,0.85)",
};
const LINE_DASH: Record<MapLineState, string | undefined> = {
  실선: undefined,
  점선: "7 5",
  미계측: "2 4",
  조회실패: "7 5",
};

/** 되돌아가는 길은 색까지 다르다 — 모양 하나로는 놓친다. */
const KIND_TINT: Partial<Record<AnatomyRelationKind, string>> = {
  back: "rgba(217,70,239,0.85)",
  bidir: "rgba(125,211,252,0.8)",
};

interface Props {
  /** 경계 판정에서 온 선 상태. 여기서 계산하지 않는다(절벽 ①). */
  lineStateFor: (from: AnatomyNodeId, to: AnatomyNodeId) => MapLineState;
  metricFor: (id: AnatomyNodeId) => number | null;
  statusLabelFor: (id: AnatomyNodeId) => string;
  selectedId: AnatomyNodeId;
  onSelect: (id: AnatomyNodeId) => void;
}

const NODE_LABEL: Record<string, string> = Object.fromEntries(
  [...ANATOMY_NODES, ...ANATOMY_CHAT_NODES].map((n) => [n.id, n.label]),
);

/** 크기 = 비중. 지표가 없는 노드는 커지지 않는다 — 모르는 것을 크게 그리지 않는다. */
function radiusOf(metric: number | null): number {
  if (metric == null) return 21;
  return 21 + Math.min(13, Math.log10(Math.max(1, metric)) * 6);
}

function pathFor(rel: AnatomyRelation, a: { x: number; y: number }, b: { x: number; y: number }) {
  const bow = rel.bow ?? (rel.kind === "branch" || rel.kind === "merge" ? 0 : -14);
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2 + bow;
  return `M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`;
}

/** 노드 테두리에서 멈춘다 — 화살촉이 원 안으로 박히면 방향이 안 읽힌다. */
function trim(a: { x: number; y: number }, b: { x: number; y: number }, ra: number, rb: number) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  return {
    a: { x: a.x + ux * (ra + 3), y: a.y + uy * (ra + 3) },
    b: { x: b.x - ux * (rb + 9), y: b.y - uy * (rb + 9) },
  };
}

export const AnatomyMap: React.FC<Props> = ({
  lineStateFor,
  metricFor,
  statusLabelFor,
  selectedId,
  onSelect,
}) => {
  const pos = useMemo(
    () => Object.fromEntries(ANATOMY_PLACEMENT.map((p) => [p.id, p])) as Record<
      AnatomyNodeId,
      (typeof ANATOMY_PLACEMENT)[number]
    >,
    [],
  );
  const radii = useMemo(
    () =>
      Object.fromEntries(
        ANATOMY_PLACEMENT.map((p) => [p.id, radiusOf(metricFor(p.id))]),
      ) as Record<AnatomyNodeId, number>,
    [metricFor],
  );

  return (
    <svg
      viewBox={`0 0 ${ANATOMY_CANVAS.width} ${ANATOMY_CANVAS.height}`}
      className="w-full"
      role="img"
      aria-label="CCUT 흐름 지도"
    >
      <defs>
        {(["실선", "점선", "미계측", "조회실패"] as MapLineState[]).map((s) => (
          <marker key={s} id={`ah-${s}`} viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={LINE_COLOR[s]} />
          </marker>
        ))}
        {(["back", "bidir"] as const).map((k) => (
          <marker key={k} id={`ah-${k}`} viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={KIND_TINT[k]} />
          </marker>
        ))}
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* 세계의 경계 — 말과 본선은 다른 세계다 */}
      <text x="14" y="30" fontSize="10" fill="rgba(56,189,248,0.55)" fontWeight="700">
        사용자의 말
      </text>
      <line x1="0" y1="300" x2={ANATOMY_CANVAS.width} y2="300"
        stroke="rgba(255,255,255,0.07)" strokeDasharray="3 7" />
      <text x="14" y="322" fontSize="10" fill="rgba(16,185,129,0.5)" fontWeight="700">
        재료의 본선
      </text>

      {ANATOMY_RELATIONS.map((rel) => {
        const a = pos[rel.from];
        const b = pos[rel.to];
        if (!a || !b) return null;
        const state = lineStateFor(rel.from, rel.to);
        const tinted = KIND_TINT[rel.kind];
        // 상태가 문제면 상태색이 이긴다 — 방향보다 건강이 먼저다.
        const color = state === "실선" && tinted ? tinted : LINE_COLOR[state];
        const marker =
          state === "실선" && tinted ? `url(#ah-${rel.kind})` : `url(#ah-${state})`;
        const t = trim(a, b, radii[rel.from], radii[rel.to]);
        const touching = rel.from === selectedId || rel.to === selectedId;
        return (
          <g key={`${rel.from}->${rel.to}`} opacity={touching ? 1 : 0.5}>
            <title>
              {`${NODE_LABEL[rel.from]} ${rel.kind === "bidir" ? "⇄" : "→"} ${NODE_LABEL[rel.to]}  [${state}]\n근거: ${rel.evidence}`}
            </title>
            <path
              d={pathFor(rel, t.a, t.b)}
              fill="none"
              stroke={color}
              strokeWidth={touching ? 2.4 : 1.6}
              strokeDasharray={LINE_DASH[state]}
              markerEnd={marker}
              markerStart={rel.kind === "bidir" ? marker : undefined}
              filter={touching ? "url(#glow)" : undefined}
            />
          </g>
        );
      })}

      {ANATOMY_PLACEMENT.map((p) => {
        const style = BAND_STYLE[p.band];
        const r = radii[p.id];
        const on = selectedId === p.id;
        const metric = metricFor(p.id);
        return (
          <g
            key={p.id}
            onClick={() => onSelect(p.id)}
            className="cursor-pointer"
            role="button"
            aria-label={`${NODE_LABEL[p.id]} 부위 선택`}
          >
            <title>{`${NODE_LABEL[p.id]} — ${statusLabelFor(p.id)}`}</title>
            <circle
              cx={p.x} cy={p.y} r={r}
              fill={style.fill}
              stroke={on ? "rgba(103,232,249,0.95)" : style.stroke}
              strokeWidth={on ? 2.4 : 1.4}
              filter={on ? "url(#glow)" : undefined}
            />
            <text x={p.x} y={p.y + 4} textAnchor="middle" fontSize="11"
              fontWeight="700" fill={style.text}>
              {NODE_LABEL[p.id]}
            </text>
            {metric != null && (
              <text x={p.x} y={p.y + r + 13} textAnchor="middle" fontSize="9"
                fill="rgba(255,255,255,0.45)">
                {metric.toLocaleString()}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
};
