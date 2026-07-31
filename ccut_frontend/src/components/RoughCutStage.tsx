import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

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
  selectedSpanIds?: string[];
  onAddSpan?: (span: RoughCutSpan) => void;
  onData?: (data: RoughCutData | null) => void;
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
  selectedSpanIds,
  onAddSpan,
  onData,
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
        if (active) {
          setData(result);
          onData?.(result);
        }
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
      onData?.(null);
    };
  }, [onData, projectId]);

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
        전사를 불러오지 못했습니다.
      </div>
    );
  }

  return (
    <section
      className="w-full max-w-[800px] shrink-0 px-1 py-2"
      data-rough-cut-stage="ready"
      data-selected-count={data.selected_count}
      data-eligible-count={data.eligible_count}
    >
      <RoughCutOutline
        data={data}
        selectedSpanIds={selectedSpanIds ?? data.ordered_span_ids}
        canPlay={canPlay}
        onAddSpan={onAddSpan ?? (() => {})}
        onPlaySpan={playSpan}
      />
    </section>
  );
};

export default RoughCutStage;
