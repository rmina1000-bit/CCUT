import React, { useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { LockKeyhole } from "lucide-react";
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
 * [MAP-R3] 흐름 지도 — 편집연구실 능력지도의 치수·서체·간선 규칙을 **그대로** 쓴다.
 *
 * 흉내가 아니라 이식이다. 아래 값은 전부 AdminEditLabPanel.tsx 에서 읽어온 것이고,
 * 그쪽 코드는 건드리지 않는다(useBoxMetrics 가 export 되지 않아 같은 구현을 옮겨 적었다).
 *   NODE_H_EM 4.4 / PAD_EM 1.8 / rx em(0.36)
 *   제목 em(1) 700 @ y+em(1.82) / 부제 em(0.82) #94a3b8 @ y+em(3.36)
 *   자물쇠 foreignObject em(1.64), LockKeyhole em(1.27), text-slate-500, 노드 안 왼쪽
 *   간선 굵기 1.7(정상)/1.2, 투명도 0.9/0.65, 색·대시 STATUS_STYLE 그대로
 *
 * 다른 것은 **배치 하나뿐**이다: 저쪽은 능력 축이라 5열 격자로 서고, 여긴 흐름 축이라
 * 되돌아가고 왕복하고 갈라진다. 그래서 좌표를 순환 구조로 잡았다.
 *
 * 크기는 폰트에 결속한다 — 07-29 사고: 컨테이너 폭에 결속했더니 글자를 줄이면 도표가 커졌다.
 */

export type MapLineState = "실선" | "점선" | "미계측" | "조회실패";

/** 편집연구실 STATUS_STYLE 그대로 — LIVE / BROKEN / UNDECLARED / REGISTERED 의 색과 대시. */
const LINE_STYLE: Record<MapLineState, { stroke: string; dash?: string; strong: boolean }> = {
  실선: { stroke: "#34d399", strong: true },
  점선: { stroke: "#f97316", dash: "7 6", strong: true },
  미계측: { stroke: "#64748b", dash: "2 7", strong: false },
  조회실패: { stroke: "#f59e0b", dash: "4 3", strong: false },
};

/** 되돌아가는 길·왕복은 색으로도 가른다 — 상태가 정상일 때만 방향색이 보인다. */
const KIND_TINT: Partial<Record<AnatomyRelationKind, string>> = {
  back: "#d946ef",
  bidir: "#38bdf8",
};

const BAND_FILL: Record<string, string> = {
  chat: "#101c28",
  main: "#102820",
  aside: "#171a20",
};

// 편집연구실 치수 (AdminEditLabPanel.tsx:243-249)
const NODE_H_EM = 4.4;
const PAD_EM = 1.8;
const FONT_MIN_PX = 9;
const FONT_MAX_PX = 24;

/** 편집연구실 useBoxMetrics 와 같은 구현 — 폰트가 바뀌면 1em 자(ruler)의 크기가 바뀌어
 *  ResizeObserver 가 울린다. 컨테이너 폭이 아니라 **폰트**에 도표를 묶는 장치다. */
const useBoxMetrics = () => {
  const ref = React.useRef<HTMLDivElement>(null);
  const rulerRef = React.useRef<HTMLSpanElement>(null);
  const [metrics, setMetrics] = useState({ width: 0, fontPx: 11 });

  const read = useCallback(() => {
    const element = ref.current;
    if (!element) return;
    const parsed = parseFloat(getComputedStyle(element).fontSize);
    const next = {
      width: element.clientWidth,
      fontPx: Math.min(
        FONT_MAX_PX,
        Math.max(FONT_MIN_PX, Number.isFinite(parsed) ? parsed : 11),
      ),
    };
    setMetrics((prev) =>
      prev.width === next.width && prev.fontPx === next.fontPx ? prev : next,
    );
  }, []);

  useLayoutEffect(read);

  useEffect(() => {
    const element = ref.current;
    const ruler = rulerRef.current;
    if (!element || !ruler) return;
    const observer = new ResizeObserver(read);
    observer.observe(element);
    observer.observe(ruler);
    return () => observer.disconnect();
  }, [read]);

  return [ref, rulerRef, metrics] as const;
};

interface Props {
  /** 경계 판정에서 온 선 상태. 여기서 계산하지 않는다(절벽 ②). */
  lineStateFor: (from: AnatomyNodeId, to: AnatomyNodeId) => MapLineState;
  metricFor: (id: AnatomyNodeId) => number | null;
  statusLabelFor: (id: AnatomyNodeId) => string;
  selectedId: AnatomyNodeId;
  onSelect: (id: AnatomyNodeId) => void;
  /** 선이 주인공이다 — 노드처럼 클릭되고, 클릭하면 경계 카드가 열린다. */
  selectedEdge: { from: AnatomyNodeId; to: AnatomyNodeId } | null;
  onSelectEdge: (rel: AnatomyRelation) => void;
  hasBoundary: (from: AnatomyNodeId, to: AnatomyNodeId) => boolean;
}

const NODE_LABEL: Record<string, string> = Object.fromEntries(
  [...ANATOMY_NODES, ...ANATOMY_CHAT_NODES].map((n) => [n.id, n.label]),
);

/** 폭은 글자를 따라간다 — 고정 폭이면 짧은 이름은 헐렁하고 긴 이름은 넘친다.
 *  지표가 있으면 그만큼 넓어진다(크기=비중). 편집연구실 노드 폭 15.6em 을 넘지 않는다. */
function widthEmOf(id: AnatomyNodeId, metric: number | null): number {
  const label = NODE_LABEL[id] ?? String(id);
  const chars = Math.max(label.length, metric != null ? String(metric).length * 0.62 : 0);
  return Math.min(15.6, Math.max(7.2, chars * 1.06 + PAD_EM * 2));
}

/** 사각 변과 선분의 교점 — 선이 박스를 뚫지 않게 변에서 끊는다(검증 ⑤). */
function edgePoint(
  from: { x: number; y: number }, to: { x: number; y: number },
  w: number, h: number, pad: number,
) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (dx === 0 && dy === 0) return { ...from };
  const hw = w / 2 + pad;
  const hh = h / 2 + pad;
  const t = Math.min(
    Math.abs(dx) > 1e-6 ? hw / Math.abs(dx) : Infinity,
    Math.abs(dy) > 1e-6 ? hh / Math.abs(dy) : Infinity,
  );
  return { x: from.x + dx * t, y: from.y + dy * t };
}

export const AnatomyMap: React.FC<Props> = ({
  lineStateFor,
  metricFor,
  statusLabelFor,
  selectedId,
  onSelect,
  selectedEdge,
  onSelectEdge,
  hasBoundary,
}) => {
  const [boxRef, rulerRef, { fontPx }] = useBoxMetrics();
  const em = (value: number) => value * fontPx;

  const pos = useMemo(
    () => Object.fromEntries(ANATOMY_PLACEMENT.map((p) => [p.id, p])),
    [],
  ) as Record<AnatomyNodeId, (typeof ANATOMY_PLACEMENT)[number]>;

  const widthsEm = useMemo(
    () =>
      Object.fromEntries(
        ANATOMY_PLACEMENT.map((p) => [p.id, widthEmOf(p.id, metricFor(p.id))]),
      ) as Record<AnatomyNodeId, number>,
    [metricFor],
  );

  const nodeH = em(NODE_H_EM);

  return (
    <div
      ref={boxRef}
      className="relative border border-border/20 bg-[#0c0f13] overflow-x-auto text-[11px]"
    >
      {/* 보이지 않는 1em 자 — 폰트가 바뀌면 이 크기가 바뀌어 관찰자가 울린다 */}
      <span
        ref={rulerRef}
        aria-hidden
        className="pointer-events-none absolute left-0 top-0 block h-[1em] w-[1em] opacity-0"
      />
      <svg
        width={em(ANATOMY_CANVAS.width)}
        height={em(ANATOMY_CANVAS.height)}
        className="block"
        role="img"
        aria-label="CCUT 흐름 지도"
      >
        <defs>
          {(Object.keys(LINE_STYLE) as MapLineState[]).map((s) => (
            <marker key={s} id={`anh-${s}`} viewBox="0 0 8 8" refX="7" refY="4"
              markerWidth="4.5" markerHeight="4.5" orient="auto-start-reverse">
              <path d="M 0 0.6 L 8 4 L 0 7.4 z" fill={LINE_STYLE[s].stroke} />
            </marker>
          ))}
          {(["back", "bidir"] as const).map((k) => (
            <marker key={k} id={`anh-${k}`} viewBox="0 0 8 8" refX="7" refY="4"
              markerWidth="4.5" markerHeight="4.5" orient="auto-start-reverse">
              <path d="M 0 0.6 L 8 4 L 0 7.4 z" fill={KIND_TINT[k]} />
            </marker>
          ))}
        </defs>

        {/* 세계의 경계 — 말과 본선은 다른 세계다 */}
        <text x={em(PAD_EM)} y={em(1.9)} fontSize={em(0.82)} fill="#38bdf8" fontWeight="700">
          사용자의 말
        </text>
        <line
          x1="0" y1={em(22)} x2={em(ANATOMY_CANVAS.width)} y2={em(22)}
          stroke="#1f2937" strokeDasharray="3 7"
        />
        <text x={em(PAD_EM)} y={em(23.6)} fontSize={em(0.82)} fill="#34d399" fontWeight="700">
          재료의 본선
        </text>

        {ANATOMY_RELATIONS.map((rel) => {
          const a = pos[rel.from];
          const b = pos[rel.to];
          if (!a || !b) return null;
          const state = lineStateFor(rel.from, rel.to);
          const st = LINE_STYLE[state];
          const tinted = KIND_TINT[rel.kind];
          // 상태가 문제면 상태색이 이긴다 — 방향보다 건강이 먼저다.
          const color = state === "실선" && tinted ? tinted : st.stroke;
          const marker =
            state === "실선" && tinted ? `url(#anh-${rel.kind})` : `url(#anh-${state})`;

          const A = { x: em(a.x), y: em(a.y) };
          const B = { x: em(b.x), y: em(b.y) };
          const s0 = edgePoint(A, B, em(widthsEm[rel.from]), nodeH, em(0.2));
          const s1 = edgePoint(B, A, em(widthsEm[rel.to]), nodeH, em(0.75));
          const bow = em(rel.bow ?? (rel.kind === "branch" || rel.kind === "merge" ? 0 : -1.3));
          const d = `M ${s0.x} ${s0.y} Q ${(s0.x + s1.x) / 2} ${(s0.y + s1.y) / 2 + bow} ${s1.x} ${s1.y}`;

          const picked =
            !!selectedEdge && selectedEdge.from === rel.from && selectedEdge.to === rel.to;
          const touching = rel.from === selectedId || rel.to === selectedId;
          const measured = hasBoundary(rel.from, rel.to);
          return (
            <g
              key={`${rel.from}->${rel.to}`}
              className="cursor-pointer"
              onClick={() => onSelectEdge(rel)}
              role="button"
              aria-label={`${NODE_LABEL[rel.from]}에서 ${NODE_LABEL[rel.to]}로 가는 경계 열기`}
            >
              <title>
                {`${NODE_LABEL[rel.from]} ${rel.kind === "bidir" ? "⇄" : "→"} ${NODE_LABEL[rel.to]}  [${state}]${measured ? "" : " · 미계측"}\n근거: ${rel.evidence}\n(클릭하면 경계 카드)`}
              </title>
              {/* 가는 선은 누르기 어렵다 — 투명한 굵은 선을 겹쳐 히트박스로 쓴다 */}
              <path d={d} fill="none" stroke="transparent" strokeWidth={em(1.2)} />
              <path
                d={d}
                fill="none"
                stroke={color}
                strokeWidth={picked ? 2.6 : st.strong ? 1.7 : 1.2}
                strokeDasharray={st.dash}
                opacity={picked ? 1 : touching ? 0.9 : st.strong ? 0.9 : 0.65}
                markerEnd={marker}
                markerStart={rel.kind === "bidir" ? marker : undefined}
              />
            </g>
          );
        })}

        {ANATOMY_PLACEMENT.map((p) => {
          const w = em(widthsEm[p.id]);
          const x = em(p.x) - w / 2;
          const y = em(p.y) - nodeH / 2;
          const on = selectedId === p.id;
          const metric = metricFor(p.id);
          // 자물쇠는 노드 **안** 왼쪽 — 편집연구실과 같은 자리·크기·색. 아무것도 가리지 않는다.
          const locked = metric == null;
          return (
            <g
              key={p.id}
              onClick={() => onSelect(p.id)}
              className="cursor-pointer"
              role="button"
              tabIndex={0}
              aria-label={`${NODE_LABEL[p.id]} 부위 선택`}
            >
              <title>{`${NODE_LABEL[p.id]} — ${statusLabelFor(p.id)}`}</title>
              <rect
                x={x} y={y} width={w} height={nodeH} rx={em(0.36)}
                fill={BAND_FILL[p.band]}
                stroke={on ? "#67e8f9" : "#334155"}
                strokeWidth={on ? 1.5 : 1}
              />
              {locked && (
                <foreignObject x={x + em(0.55)} y={y + em(1.27)} width={em(1.64)} height={em(1.64)}>
                  <LockKeyhole size={em(1.27)} className="text-slate-500" />
                </foreignObject>
              )}
              <text
                x={x + em(locked ? 2.3 : 0.8)} y={y + em(1.82)}
                fill="#e5e7eb" fontSize={em(1)} fontWeight="700"
              >
                {NODE_LABEL[p.id]}
              </text>
              <text x={x + em(0.8)} y={y + em(3.36)} fill="#94a3b8" fontSize={em(0.82)}>
                {metric != null ? metric.toLocaleString() : statusLabelFor(p.id)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
