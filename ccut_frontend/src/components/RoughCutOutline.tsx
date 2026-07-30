import React, { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Play } from "lucide-react";

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
  canPlay: (span: RoughCutSpan) => boolean;
  onPlaySpan: (span: RoughCutSpan) => void;
}

const ACT_LABELS: Record<RoughCutAct["phase"], string> = {
  gi: "기",
  seung: "승",
  jeon: "전",
  gyeol: "결",
};

const formatTime = (ms: number) => {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
};

const RoughCutOutline: React.FC<RoughCutOutlineProps> = ({
  data,
  canPlay,
  onPlaySpan,
}) => {
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const selectedIds = useMemo(
    () => new Set(data.ordered_span_ids),
    [data.ordered_span_ids],
  );

  return (
    <div className="w-full">
      <div className="border-y border-white/10">
        {data.acts.map((act) => (
          <section
            key={act.phase}
            className="grid grid-cols-[34px_minmax(0,1fr)] border-b border-white/8 last:border-b-0"
          >
            <div className="flex items-start justify-center pt-3 text-[13px] font-bold text-primary">
              {ACT_LABELS[act.phase]}
            </div>
            <div className="min-w-0 border-l border-white/8 py-2">
              {act.spans.map((span) => (
                <button
                  key={span.span_id}
                  type="button"
                  disabled={!canPlay(span)}
                  onClick={() => onPlaySpan(span)}
                  className="group flex w-full min-w-0 items-start gap-2 px-3 py-2 text-left text-[14px] leading-relaxed text-foreground/85 transition-colors hover:bg-white/[0.04] disabled:cursor-default disabled:opacity-55"
                  title={canPlay(span) ? "이 구간 재생" : "재생할 영상을 찾지 못했습니다"}
                >
                  <Play
                    size={13}
                    className="mt-1 shrink-0 text-muted-foreground/45 group-hover:text-primary"
                    fill="currentColor"
                  />
                  <span className="min-w-0 break-words">{span.text}</span>
                  <span className="ml-auto shrink-0 pt-0.5 text-[11px] tabular-nums text-muted-foreground/40">
                    {formatTime(span.start_ms)}
                  </span>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>

      <button
        type="button"
        aria-expanded={transcriptOpen}
        onClick={() => setTranscriptOpen((open) => !open)}
        className="mt-2 flex h-9 w-full items-center gap-2 px-2 text-left text-[13px] font-semibold text-muted-foreground transition-colors hover:text-foreground"
      >
        {transcriptOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        <span>전체 전사</span>
        <span className="ml-auto tabular-nums text-muted-foreground/50">
          {data.eligible_count}
        </span>
      </button>

      {transcriptOpen && (
        <div className="max-h-[34vh] overflow-y-auto border-t border-white/8 py-1">
          {data.transcript.map((span) => {
            const selected = selectedIds.has(span.span_id);
            return (
              <button
                key={span.span_id}
                type="button"
                disabled={!canPlay(span)}
                onClick={() => onPlaySpan(span)}
                className={`flex w-full items-start gap-2 px-2 py-1.5 text-left text-[12px] leading-relaxed transition-colors hover:bg-white/[0.04] disabled:cursor-default ${
                  selected ? "text-foreground/80" : "text-muted-foreground/55"
                }`}
                title={canPlay(span) ? "이 구간 재생" : "재생할 영상을 찾지 못했습니다"}
              >
                <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${
                  selected ? "bg-primary" : "bg-white/15"
                }`} />
                <span className="min-w-0 break-words">{span.text}</span>
                <span className="ml-auto shrink-0 tabular-nums text-muted-foreground/35">
                  {formatTime(span.start_ms)}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default RoughCutOutline;
