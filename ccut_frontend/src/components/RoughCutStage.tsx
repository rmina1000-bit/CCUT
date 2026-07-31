import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import type { MiniPlayTarget } from "@/components/FragmentMiniPlayer";
import RoughCutOutline from "@/components/RoughCutOutline";
import type { Fragment } from "@/data/fragmentData";
import type {
  RoughCutData,
  RoughCutDisplayWord,
  RoughCutSpan,
} from "@/components/RoughCutOutline";
import type { SourceEntry } from "@/types";

interface RoughCutStageProps {
  projectId: string;
  sourceEntries: SourceEntry[];
  onPlay: (target: MiniPlayTarget) => void;
  selectedSpanIds?: string[];
  activeFragmentId?: string | null;
  focusOrigin?: "sequence" | "user";
  fragmentForSpan?: (span: RoughCutSpan) => Fragment | null;
  onAddSpan?: (span: RoughCutSpan) => void;
  onData?: (data: RoughCutData | null) => void;
}

const readError = async (response: Response) => {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (detail?.error === "insufficient_text") {
    return "이 영상은 전사가 부족해 가편집을 만들 수 없습니다.";
  }
  if (typeof detail === "string") return detail;
  if (detail?.message) return `가편집을 만들지 못했습니다: ${String(detail.message)}`;
  return `HTTP ${response.status}`;
};

interface LedgerTranscriptItem {
  source_id?: string;
  anchor_start_ms?: number;
  anchor_end_ms?: number;
  words?: RoughCutDisplayWord[];
}

const RoughCutStage: React.FC<RoughCutStageProps> = ({
  projectId,
  sourceEntries,
  onPlay,
  selectedSpanIds,
  activeFragmentId,
  focusOrigin,
  fragmentForSpan,
  onAddSpan,
  onData,
}) => {
  const [data, setData] = useState<RoughCutData | null>(null);
  const [ledgerItems, setLedgerItems] = useState<LedgerTranscriptItem[]>([]);
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

  useEffect(() => {
    let active = true;
    const loadLedger = async () => {
      const response = await fetch(
        `/api/ledger/${encodeURIComponent(projectId)}`,
      );
      if (!response.ok) return;
      const body = await response.json().catch(() => null);
      if (active) {
        setLedgerItems(
          Array.isArray(body?.items)
            ? body.items.filter((item: LedgerTranscriptItem) => Array.isArray(item.words))
            : [],
        );
      }
    };
    const handleTextEdit = (event: Event) => {
      const detail = (event as CustomEvent<{ programId?: string }>).detail;
      if (!detail?.programId || detail.programId === projectId) {
        void loadLedger();
      }
    };
    void loadLedger();
    window.addEventListener("ccut:text-edit-state-changed", handleTextEdit);
    return () => {
      active = false;
      window.removeEventListener("ccut:text-edit-state-changed", handleTextEdit);
    };
  }, [projectId]);

  const displayData = useMemo(() => {
    if (!data) return data;
    return {
      ...data,
      transcript: data.transcript.map((span) => {
        const fragment = fragmentForSpan?.(span);
        const best = ledgerItems
          .filter((item) => item.source_id === span.source_id)
          .map((item) => {
            const start = Number(item.anchor_start_ms);
            const end = Number(item.anchor_end_ms);
            const overlap = Math.max(
              0,
              Math.min(span.end_ms, end) - Math.max(span.start_ms, start),
            );
            return { item, overlap };
          })
          .filter(({ overlap }) => overlap > 0)
          .sort((left, right) => right.overlap - left.overlap)[0]?.item;
        const displayWords = (best?.words ?? []).filter((word) => (
          Number(word.e_ms) > span.start_ms && Number(word.s_ms) < span.end_ms
        ));
        return displayWords.length > 0
          ? {
            ...span,
            fragment_id: fragment?.fragment_id,
            display_id: fragment?.display_id,
            display_words: displayWords,
          }
          : {
            ...span,
            fragment_id: fragment?.fragment_id,
            display_id: fragment?.display_id,
          };
      }),
    };
  }, [data, fragmentForSpan, ledgerItems]);

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

  if (!displayData || error) {
    return (
      <div
        className="flex min-h-[220px] w-full max-w-[800px] items-center justify-center text-[13px] text-muted-foreground/60"
        data-rough-cut-error={error || "empty"}
      >
        {error || "전사를 불러오지 못했습니다."}
      </div>
    );
  }

  return (
    <section
      className="w-full max-w-[800px] shrink-0 px-1 py-2"
      data-rough-cut-stage="ready"
      data-selected-count={displayData.selected_count}
      data-eligible-count={displayData.eligible_count}
    >
      <RoughCutOutline
        data={displayData}
        selectedSpanIds={selectedSpanIds ?? displayData.ordered_span_ids}
        activeFragmentId={activeFragmentId}
        focusOrigin={focusOrigin}
        canPlay={canPlay}
        onAddSpan={onAddSpan ?? (() => {})}
        onPlaySpan={playSpan}
      />
    </section>
  );
};

export default RoughCutStage;
