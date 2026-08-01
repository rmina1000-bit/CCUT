import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, Loader2 } from "lucide-react";

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

  // [TRANSCRIPT-FOLD 2026-08-01] 전사 제목 + 접기.
  //   접힘은 **프로젝트별로** 기억한다. 이유: 같은 프로젝트를 매일 여는데 열 때마다
  //   다시 접어야 하면 그건 기억이 아니라 잡일이다. 그렇다고 전역으로 두면 A 에서 접은 것이
  //   B 를 접어버린다 — 오늘 하루 배운 것이 "프로젝트 상태는 프로젝트 것"이다.
  //   전사를 접어도 데이터는 그대로 불러온다(조각맵·재생이 같은 data 를 쓴다).
  //   접기는 표시만 바꾼다 — 안 보이는 것과 없는 것을 섞지 않는다.
  const FOLD_KEY = "ccut_transcript_folded";
  const readFolded = (): Record<string, boolean> => {
    try { return JSON.parse(localStorage.getItem(FOLD_KEY) || "{}"); } catch { return {}; }
  };
  const [folded, setFolded] = useState<boolean>(() => !!readFolded()[projectId]);
  useEffect(() => { setFolded(!!readFolded()[projectId]); }, [projectId]);
  const toggleFold = useCallback(() => {
    setFolded((prev) => {
      const next = !prev;
      try {
        const all = readFolded();
        if (next) all[projectId] = true; else delete all[projectId];
        localStorage.setItem(FOLD_KEY, JSON.stringify(all));
      } catch {
        // 저장이 막혀도(사생활 모드 등) 화면 동작은 그대로 — 기억만 못 한다.
      }
      return next;
    });
  }, [projectId]);

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
    const linkedSpans = span.fragment_id
      ? displayData?.transcript.filter((candidate) => (
        candidate.fragment_id === span.fragment_id
        && candidate.source_id === span.source_id
      )) ?? [span]
      : [span];
    const startMs = Math.min(...linkedSpans.map((candidate) => candidate.start_ms));
    const endMs = Math.max(...linkedSpans.map((candidate) => candidate.end_ms));
    onPlay({
      videoUrl,
      spans: [[startMs / 1000, endMs / 1000]],
      fragmentId: span.fragment_id ?? span.span_id,
      label: linkedSpans.map((candidate) => candidate.text).join(" "),
    });
  }, [displayData, onPlay, sourceUrls]);

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
      <button
        type="button"
        onClick={toggleFold}
        aria-expanded={!folded}
        data-transcript-fold={folded ? "folded" : "open"}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-[13px] font-medium tracking-[0.02em] text-foreground/70 transition-colors hover:text-foreground"
        title={folded ? "전사 펼치기" : "전사 줄이기"}
      >
        전사
        <ChevronDown
          size={15}
          className={`transition-transform duration-150 ${folded ? "-rotate-90" : ""}`}
        />
      </button>
      {/* [TRANSCRIPT-FOLD 2026-08-01 개정] 접어도 **완전히 감추지 않는다.**
          구판은 접으면 0행이라 그 자리가 통째로 비어 화면이 허전했다. 접힘의 뜻은
          '없애기'가 아니라 '자리를 덜 쓰기'다 — 대여섯 줄만 남기고, 그 안에서
          스크롤로 나머지를 계속 볼 수 있게 둔다(데이터는 어차피 다 실려 있다).
          높이는 행 최소높이(min-h-9=2.25rem)의 약 5.5배. 조각 한 줄이 길어 두 줄로
          접히는 경우가 있어 '정확히 6행'으로 고정하지 않는다 — 픽셀로 세는 것이
          행으로 세는 것보다 정직하다(행 높이는 내용에 따라 변한다).
          높이 산정(실측 2026-08-01, Freesia 124행): 행 높이 38~207px, 중앙값 101px.
          한 조각을 한 줄로 합친 뒤로 행이 두꺼워져서, 처음 잡은 12.4rem 은 3행밖에
          못 보여줬다. 중앙값 x5 = 505px 에 맞춰 32rem(512px)로 올린다. */}
      <div
        data-transcript-body={folded ? "compact" : "full"}
        className={folded ? "max-h-[32rem] overflow-y-auto" : undefined}
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
      </div>
    </section>
  );
};

export default RoughCutStage;
