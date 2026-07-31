import React, { useMemo } from "react";
import { Play } from "lucide-react";

export interface RoughCutSpan {
  span_id: string;
  source_id: string;
  start_ms: number;
  end_ms: number;
  text: string;
  selected?: boolean;
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
}

interface RoughCutOutlineProps {
  data: RoughCutData;
  selectedSpanIds: string[];
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
  canPlay,
  onAddSpan,
  onPlaySpan,
}) => {
  const selectedIds = useMemo(
    () => new Set(selectedSpanIds),
    [selectedSpanIds],
  );

  return (
    <div
      className="w-full border-y border-white/8 py-1"
      data-rough-cut-transcript-count={data.transcript.length}
    >
      {data.transcript.map((span) => {
        const selected = selectedIds.has(span.span_id);
        return (
          <div
            key={span.span_id}
            className={`group flex min-h-9 w-full items-start border-b border-white/[0.035] transition-colors last:border-b-0 hover:bg-white/[0.035] ${
              selected ? "bg-white/[0.025]" : ""
            }`}
            data-rough-cut-span={span.span_id}
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
              <span className="min-w-0 break-words">{span.text}</span>
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
