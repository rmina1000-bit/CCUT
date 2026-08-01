import React, { useEffect, useMemo, useRef } from "react";
import { Play } from "lucide-react";
import { FRAGMENT_EXCLUDED_STYLE } from "@/lib/fragmentText";

export interface RoughCutDisplayWord {
  w: string;
  s_ms: number;
  e_ms: number;
  excluded?: boolean;
}

export interface RoughCutSpan {
  span_id: string;
  fragment_id?: string;
  display_id?: string;
  source_id: string;
  start_ms: number;
  end_ms: number;
  text: string;
  selected?: boolean;
  display_words?: RoughCutDisplayWord[];
}

export interface RoughCutAct {
  phase: "gi" | "seung" | "jeon" | "gyeol";
  summary: string;
  span_ids: string[];
  spans: RoughCutSpan[];
}

export interface RoughCutData {
  project_id: string;
  owner: {
    program_id: string;
    source_ids: string[];
  };
  input_hash?: string | null;
  premise: string;
  acts: RoughCutAct[];
  ordered_span_ids: string[];
  selected_count: number;
  eligible_count: number;
  transcript: RoughCutSpan[];
  mapping: {
    auto: number;
    candidate: number;
    unknown: number;
  };
  generation?: {
    kind?: string;
    reason?: string;
  };
}

interface RoughCutOutlineProps {
  data: RoughCutData;
  selectedSpanIds: string[];
  activeFragmentId?: string | null;
  focusOrigin?: "sequence" | "user";
  canPlay: (span: RoughCutSpan) => boolean;
  onAddSpan: (span: RoughCutSpan) => void;
  onPlaySpan: (span: RoughCutSpan) => void;
}

const formatTime = (ms: number) => {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
};

const RoughCutOutline: React.FC<RoughCutOutlineProps> = ({
  data,
  selectedSpanIds,
  activeFragmentId,
  focusOrigin = "user",
  canPlay,
  onAddSpan,
  onPlaySpan,
}) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const selectedIds = useMemo(
    () => new Set(selectedSpanIds),
    [selectedSpanIds],
  );
  const selectedOrderByFragment = useMemo(() => {
    const spanById = new Map(data.transcript.map((span) => [span.span_id, span]));
    const orderByFragment = new Map<string, number>();
    for (const spanId of selectedSpanIds) {
      const fragmentId = spanById.get(spanId)?.fragment_id;
      if (fragmentId && !orderByFragment.has(fragmentId)) {
        orderByFragment.set(fragmentId, orderByFragment.size + 1);
      }
    }
    return orderByFragment;
  }, [data.transcript, selectedSpanIds]);
  // [TRANSCRIPT-ONE-ROW 2026-08-01] 한 조각 = 한 줄.
  //   구판은 span(자막 세그먼트) 하나가 한 줄이라, 조각 하나가 대여섯 줄로 흩어지고
  //   그중 첫 줄만 라벨을 달았다(나머지는 continuation 세로선). 텍스트 조각 방식과 어긋난다.
  //   묶음은 **연속된 같은 fragment_id** 로만 한다 — 조각의 span 들은 시간순으로 붙어 있고,
  //   떨어진 것을 억지로 합치면 없는 인접성을 만든다.
  //   fragment_id 가 없는 span(조각 미매핑)은 예전처럼 자기 줄을 그대로 갖는다.
  const rows = useMemo(() => {
    const out: Array<{
      key: string;
      spans: RoughCutSpan[];
      fragment_id?: string;
      display_id?: string;
      start_ms: number;
    }> = [];
    for (const span of data.transcript) {
      const last = out[out.length - 1];
      if (span.fragment_id && last?.fragment_id === span.fragment_id) {
        last.spans.push(span);
        continue;
      }
      out.push({
        key: span.span_id,
        spans: [span],
        fragment_id: span.fragment_id,
        display_id: span.display_id,
        start_ms: span.start_ms,
      });
    }
    return out;
  }, [data.transcript]);

  useEffect(() => {
    if (!activeFragmentId || focusOrigin !== "user") return;
    const row = rootRef.current?.querySelector(
      `[data-fragment-id="${activeFragmentId}"]`,
    );
    row?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeFragmentId, focusOrigin]);

  return (
    <div
      ref={rootRef}
      className="w-full border-y border-white/8 py-1"
      data-rough-cut-transcript-count={data.transcript.length}
    >
      {rows.map((row) => {
        // 스토리 추가는 이미 조각 단위다(Index.handleRoughCutSpanAdd 가 span -> fragment 로
        // 풀어 fid 를 넣는다) — 대표 span 하나만 넘기면 예전과 같은 결과가 된다.
        const span = row.spans[0];
        const storyOrder = row.fragment_id
          ? selectedOrderByFragment.get(row.fragment_id)
          : undefined;
        const selected = row.spans.some((s) => selectedIds.has(s.span_id)) || storyOrder !== undefined;
        const active = !!activeFragmentId && row.fragment_id === activeFragmentId;
        const words = row.spans.flatMap((s) => s.display_words ?? []);
        const text = row.spans.map((s) => s.text).join(" ");
        return (
          <div
            key={row.key}
            className={`group flex min-h-9 w-full items-start border-b border-white/[0.035] transition-colors last:border-b-0 hover:bg-white/[0.035] ${
              active ? "bg-primary/10" : selected ? "bg-white/[0.025]" : ""
            }`}
            data-rough-cut-span={span.span_id}
            data-rough-cut-span-count={row.spans.length}
            data-fragment-id={row.fragment_id}
            data-fragment-display-id={row.display_id}
            data-fragment-label-visible="true"
            data-fragment-continuation="false"
            data-story-order={storyOrder}
            data-transcript-active={active ? "true" : "false"}
            data-story-selected={selected ? "true" : "false"}
          >
            <button
              type="button"
              onClick={() => onAddSpan(span)}
              className={`flex min-w-0 flex-1 items-start gap-3 px-2 py-2 text-left text-[13px] leading-relaxed transition-colors ${
                selected
                  ? "font-medium text-white"
                  : "text-muted-foreground/55 hover:text-foreground/75"
              }`}
              title={selected ? "스토리에 들어간 문장" : "스토리에 추가"}
            >
              <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center">
                {storyOrder && (
                  <span className="flex h-[18px] w-[18px] items-center justify-center rounded-[5px] bg-primary font-mono text-[11px] font-medium leading-none text-primary-foreground">
                    {storyOrder}
                  </span>
                )}
              </span>
              <span className={`w-7 shrink-0 pt-0.5 font-mono text-[12px] font-medium leading-none ${
                storyOrder ? "text-primary" : "text-secondary-foreground/45"
              }`}>
                {row.display_id}
              </span>
              <span className="min-w-0 break-words">
                {words.length
                  ? words.map((word, index) => (
                    <span
                      key={`${word.s_ms}-${word.e_ms}-${index}`}
                      style={word.excluded ? FRAGMENT_EXCLUDED_STYLE : undefined}
                    >
                      {word.w}{" "}
                    </span>
                  ))
                  : text}
              </span>
              <span className="ml-auto shrink-0 pt-0.5 text-[11px] tabular-nums text-muted-foreground/35">
                {formatTime(row.start_ms)}
              </span>
            </button>
            <button
              type="button"
              disabled={!canPlay(span)}
              onClick={() => onPlaySpan(span)}
              className="mr-1 mt-1.5 inline-flex h-7 w-7 shrink-0 items-center justify-center text-muted-foreground/35 transition-colors hover:text-primary disabled:cursor-default disabled:opacity-20"
              title={canPlay(span) ? "이 구간 재생" : "재생할 영상을 찾지 못했습니다"}
            >
              <Play size={13} fill="currentColor" />
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default RoughCutOutline;
