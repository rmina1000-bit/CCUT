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

/** 노드 채움·테두리는 편집연구실 Node(:395)와 **같은 식**이다 — 계열이 아니라 상태에서 나온다.
 *  계열로 칠했더니 파랑/초록/회색이 섞여 색감이 달라 보였다. 위치가 계열을 말하므로 색까지 쓸 필요가 없다. */
const NODE_FILL = { LIVE: "#102820", LOCKED: "#171a20" } as const;
const NODE_STROKE = { LIVE: "#34d399", LOCKED: "#64748b" } as const;

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
  /** 부제는 실값이다 — 편집연구실이 "930 · 조각 단위"를 적는 자리. 없으면 세어서 적는다. */
  subtitleFor: (id: AnatomyNodeId) => string;
  /** 잠김: 지표를 가져야 할 노드인데 값을 못 읽은 경우에만. */
  lockedFor: (id: AnatomyNodeId) => boolean;
}

const NODE_LABEL: Record<string, string> = Object.fromEntries(
  [...ANATOMY_NODES, ...ANATOMY_CHAT_NODES].map((n) => [n.id, n.label]),
);

/** 폭은 **모든 노드가 같다**. 편집연구실 NODE_W_EM 15.6 그대로.
 *  이전 차수에 "크기=텍스트 연동"으로 폭을 제각각 잡았더니 어수선했다 — 편집연구실이
 *  정돈돼 보이는 정체가 바로 이 통일이다. 크기로 비중을 말하지 않는다(부제의 실값이 말한다). */
const NODE_W_EM = 15.6;

/** 열의 왼쪽 x — 좌표(config)와 같은 값에서 온다. 라벨은 편집연구실처럼 열 위에 붙는다. */
const COLUMNS = [
  { x: 13.8, label: "사용자의 말" },
  { x: 39.6, label: "재료의 본선" },
  { x: 65.4, label: "곁가지" },
];

/** 모서리를 조금 둥글린 꺾임 — 곧은 직선도, 크게 휘는 곡선도 아니다.
 *  본선에 붙지 않게 왼쪽 차선으로 빠져나갔다 돌아온다. */
function softElbow(pts: Array<{ x: number; y: number }>, r: number): string {
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const prev = pts[i - 1];
    const cur = pts[i];
    const next = pts[i + 1];
    const inLen = Math.hypot(cur.x - prev.x, cur.y - prev.y) || 1;
    const outLen = Math.hypot(next.x - cur.x, next.y - cur.y) || 1;
    const ri = Math.min(r, inLen / 2, outLen / 2);
    const a = { x: cur.x - ((cur.x - prev.x) / inLen) * ri, y: cur.y - ((cur.y - prev.y) / inLen) * ri };
    const b = { x: cur.x + ((next.x - cur.x) / outLen) * ri, y: cur.y + ((next.y - cur.y) / outLen) * ri };
    d += ` L ${a.x} ${a.y} Q ${cur.x} ${cur.y} ${b.x} ${b.y}`;
  }
  const last = pts[pts.length - 1];
  return `${d} L ${last.x} ${last.y}`;
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
  subtitleFor,
  lockedFor,
}) => {
  const [boxRef, rulerRef, { fontPx }] = useBoxMetrics();
  const em = (value: number) => value * fontPx;

  const pos = useMemo(
    () => Object.fromEntries(ANATOMY_PLACEMENT.map((p) => [p.id, p])),
    [],
  ) as Record<AnatomyNodeId, (typeof ANATOMY_PLACEMENT)[number]>;

  const nodeH = em(NODE_H_EM);

  /** 가는 길과 되돌아오는 길이 둘 다 있는 짝 — 두 선을 나란히 놓아야 왕복이 보인다. */
  const reciprocal = useMemo(() => {
    const keys = new Set(ANATOMY_RELATIONS.map((r) => `${r.from}>${r.to}`));
    const out = new Set<string>();
    ANATOMY_RELATIONS.forEach((r) => {
      if (keys.has(`${r.to}>${r.from}`)) out.add(`${r.from}>${r.to}`);
    });
    return out;
  }, []);

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

        {/* 열 라벨 — 편집연구실 :432-436 그대로 (같은 색 #94a3b8, em(1) 700, 밑줄 #29313d) */}
        {COLUMNS.map((col) => (
          <g key={col.label}>
            <text x={em(col.x)} y={em(2.55)} fill="#94a3b8" fontSize={em(1)} fontWeight="700">
              {col.label}
            </text>
            <line
              x1={em(col.x)} y1={em(3.64)} x2={em(col.x + NODE_W_EM)} y2={em(3.64)}
              stroke="#29313d"
            />
          </g>
        ))}

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
          const bowEm = rel.bow ?? 0;
          const sameCol = Math.abs(a.x - b.x) < 0.01;
          const skips = Math.abs(a.y - b.y) > 11;   // 한 행보다 멀다 = 사이 노드를 건너뛴다
          let s0: { x: number; y: number };
          let s1: { x: number; y: number };
          let d: string;
          if (sameCol && skips && bowEm !== 0) {
            // 여기도 곡선이 아니다 — **직선 세 토막**으로 옆으로 나갔다 돌아온다.
            // 같은 열에서 이웃을 건너뛰는 선(분기·되돌아감)은 곧게 그으면 사이 노드를 관통한다.
            const side = Math.sign(bowEm);
            const off = em(Math.abs(bowEm));
            s0 = { x: A.x + side * (em(NODE_W_EM) / 2), y: A.y };
            s1 = { x: B.x + side * (em(NODE_W_EM) / 2 + em(0.55)), y: B.y };
            d = softElbow(
              [
                s0,
                { x: s0.x + side * off, y: s0.y },
                { x: s1.x + side * off, y: s1.y },
                s1,
              ],
              em(1.6),
            );
          } else {
            // 나머지는 전부 **직선**이다. 곡선을 쓸 이유가 없는 곳에 쓰지 않는다.
            s0 = edgePoint(A, B, em(NODE_W_EM), nodeH, em(0.2));
            s1 = edgePoint(B, A, em(NODE_W_EM), nodeH, em(0.75));
            // 오가는 짝(스토리 <-> 편집처럼 가는 길과 되돌아오는 길이 둘 다 있는 곳)은
            // 나란히 긋는다. 같은 자리에 겹쳐 그으면 왕복이 한 줄로 보여 되돌아감이 사라진다.
            if (reciprocal.has(`${rel.from}>${rel.to}`)) {
              const vx = s1.x - s0.x;
              const vy = s1.y - s0.y;
              const L = Math.hypot(vx, vy) || 1;
              const lane = em(1.7) * (rel.kind === "back" ? -1 : 1);
              const ox = (-vy / L) * lane;
              const oy = (vx / L) * lane;
              s0 = { x: s0.x + ox, y: s0.y + oy };
              s1 = { x: s1.x + ox, y: s1.y + oy };
            }
            d = `M ${s0.x} ${s0.y} L ${s1.x} ${s1.y}`;
          }

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
          const w = em(NODE_W_EM);
          const x = em(p.x) - w / 2;
          const y = em(p.y) - nodeH / 2;
          const on = selectedId === p.id;
          const metric = metricFor(p.id);
          // 자물쇠는 **잠긴 것에만**. 편집연구실도 재료가 0인 노드 3개에만 붙는다.
          // 앞 차수엔 지표 없는 노드 전부에 붙어 12개가 어수선했다 — 미계측은 이미
          // 선이 점선으로 말하고 있으므로 노드까지 표식을 달 이유가 없다.
          const locked = lockedFor(p.id);
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
                fill={locked ? NODE_FILL.LOCKED : NODE_FILL.LIVE}
                stroke={on ? "#67e8f9" : locked ? NODE_STROKE.LOCKED : NODE_STROKE.LIVE}
                strokeWidth={on ? 1.5 : locked ? 1 : 1.5}
              />
              {locked && (
                <foreignObject x={x + em(0.55)} y={y + em(1.27)} width={em(1.64)} height={em(1.64)}>
                  <LockKeyhole size={em(1.27)} className="text-slate-500" />
                </foreignObject>
              )}
              <text
                x={x + em(locked ? 2.9 : 1.1)} y={y + em(1.82)}
                fill="#e5e7eb" fontSize={em(1)} fontWeight="700"
              >
                {NODE_LABEL[p.id]}
              </text>
              <text x={x + em(1.1)} y={y + em(3.36)} fill="#94a3b8" fontSize={em(0.82)}>
                {subtitleFor(p.id)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
