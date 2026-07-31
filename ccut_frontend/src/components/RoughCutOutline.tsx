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
      {data.transcript.map((span) => {
        const selected = selectedIds.has(span.span_id);
        const active = !!activeFragmentId && span.fragment_id === activeFragmentId;
        const storyOrder = span.fragment_id
          ? selectedOrderByFragment.get(span.fragment_id)
          : undefined;
        return (
          <div
            key={span.span_id}
            className={`group flex min-h-9 w-full items-start border-b border-white/[0.035] transition-colors last:border-b-0 hover:bg-white/[0.035] ${
              active ? "bg-primary/10" : selected ? "bg-white/[0.025]" : ""
            }`}
            data-rough-cut-span={span.span_id}
            data-fragment-id={span.fragment_id}
            data-fragment-display-id={span.display_id}
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
                {span.display_id}
              </span>
              <span className="min-w-0 break-words">
                {span.display_words?.length
                  ? span.display_words.map((word, index) => (
                    <span
                      key={`${word.s_ms}-${word.e_ms}-${index}`}
                      style={word.excluded ? FRAGMENT_EXCLUDED_STYLE : undefined}
                    >
                      {word.w}{" "}
                    </span>
                  ))
                  : span.text}
              </span>
              <span className="ml-auto shrink-0 pt-0.5 text-[11px] tabular-nums text-muted-foreground/35">
                {formatTime(span.start_ms)}
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
