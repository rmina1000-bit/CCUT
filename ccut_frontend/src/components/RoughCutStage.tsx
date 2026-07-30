import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Play } from "lucide-react";

import type { MiniPlayTarget } from "@/components/FragmentMiniPlayer";
import RoughCutOutline from "@/components/RoughCutOutline";
import type {
  RoughCutData,
  RoughCutSpan,
} from "@/components/RoughCutOutline";
import type { SourceEntry } from "@/types";

interface RoughCutStageProps {
  projectId: string;
  sourceEntries: SourceEntry[];
  onPlay: (target: MiniPlayTarget) => void;
}

const readError = async (response: Response) => {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return String(detail.message);
  return `HTTP ${response.status}`;
};

const RoughCutStage: React.FC<RoughCutStageProps> = ({
  projectId,
  sourceEntries,
  onPlay,
}) => {
  const [data, setData] = useState<RoughCutData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      setData(null);
      try {
        let response = await fetch(
          `/api/rough-cut/project/${encodeURIComponent(projectId)}`,
        );
        if (response.status === 404) {
          response = await fetch(
            `/api/rough-cut/project/${encodeURIComponent(projectId)}`,
            { method: "POST" },
          );
        }
        if (!response.ok) throw new Error(await readError(response));
        const result = await response.json();
        if (active) setData(result);
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : "rough_cut_failed");
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [projectId]);

  const sourceUrls = useMemo(
    () => new Map(
      sourceEntries
        .filter((source) => source.video_url)
        .map((source) => [source.source_id, source.video_url]),
    ),
    [sourceEntries],
  );

  const canPlay = useCallback(
    (span: RoughCutSpan) => sourceUrls.has(span.source_id),
    [sourceUrls],
  );

  const playSpan = useCallback((span: RoughCutSpan) => {
    const videoUrl = sourceUrls.get(span.source_id);
    if (!videoUrl) return;
    onPlay({
      videoUrl,
      spans: [[span.start_ms / 1000, span.end_ms / 1000]],
      fragmentId: span.span_id,
      label: span.text,
    });
  }, [onPlay, sourceUrls]);

  const selectedSpans = useMemo(() => {
    if (!data) return [];
    const byId = new Map(data.transcript.map((span) => [span.span_id, span]));
    return data.ordered_span_ids
      .map((spanId) => byId.get(spanId))
      .filter((span): span is RoughCutSpan => !!span);
  }, [data]);

  const premiseText = useMemo(
    () => (data?.premise || "")
      .replace(/\*\*/g, "")
      .replace(/^\s*[-*]\s+/gm, "")
      .trim(),
    [data?.premise],
  );

  const playableCut = useMemo(() => {
    if (selectedSpans.length === 0) return null;
    const sourceId = selectedSpans[0].source_id;
    if (!selectedSpans.every((span) => span.source_id === sourceId)) return null;
    const videoUrl = sourceUrls.get(sourceId);
    if (!videoUrl) return null;
    return {
      videoUrl,
      spans: selectedSpans.map(
        (span) => [span.start_ms / 1000, span.end_ms / 1000] as [number, number],
      ),
      fragmentId: `rough-cut:${projectId}`,
      label: "가편집",
    };
  }, [projectId, selectedSpans, sourceUrls]);

  if (loading) {
    return (
      <div className="flex min-h-[280px] w-full max-w-[800px] items-center justify-center">
        <Loader2 size={18} className="animate-spin text-primary" />
      </div>
    );
  }

  if (!data || error) {
    return (
      <div
        className="flex min-h-[220px] w-full max-w-[800px] items-center justify-center text-[13px] text-muted-foreground/60"
        data-rough-cut-error={error || "empty"}
      >
        가편집안을 만들지 못했습니다.
      </div>
    );
  }

  return (
    <section
      className="w-full max-w-[800px] px-1 py-2"
      data-rough-cut-stage="ready"
      data-selected-count={data.selected_count}
      data-eligible-count={data.eligible_count}
    >
      <header className="mb-3 flex items-center gap-3">
        <button
          type="button"
          disabled={!playableCut}
          onClick={() => playableCut && onPlay(playableCut)}
          className="inline-flex h-9 items-center gap-2 rounded-md bg-foreground px-3 text-[13px] font-semibold text-background transition-opacity hover:opacity-90 disabled:cursor-default disabled:opacity-35"
          title={playableCut ? "가편집 재생" : "한 영상의 가편집만 연속 재생할 수 있습니다"}
        >
          <Play size={14} fill="currentColor" />
          <span>재생</span>
        </button>
        <span className="ml-auto text-[13px] tabular-nums text-muted-foreground/65">
          사용 <strong className="font-semibold text-foreground/85">{data.selected_count}</strong>
          {" / "}
          전사 <strong className="font-semibold text-foreground/85">{data.eligible_count}</strong>
        </span>
      </header>

      <p
        className="mb-4 line-clamp-5 whitespace-pre-wrap px-1 text-[14px] leading-relaxed text-foreground/75"
        title={premiseText}
      >
        {premiseText}
      </p>

      <RoughCutOutline
        data={data}
        canPlay={canPlay}
        onPlaySpan={playSpan}
      />
    </section>
  );
};

export default RoughCutStage;
