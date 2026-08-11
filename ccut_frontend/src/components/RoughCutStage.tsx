import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
  /** [FIRST-RUN 2026-08-04] 조각화가 끝났는가 = /story 의 item_count > 0.
   *  새 폴링이 아니라 이미 도는 useStoryGate(10초)의 값을 받아 쓴다.
   *  false 인 동안의 insufficient_text 는 '아직'이지 '없음'이 아니다. */
  analysisReady?: boolean;
}

/** [FIRST-RUN 2026-08-04] 재시도 간격·상한. 서버 폭격 금지 — 5회로 끝난다.
 *  분석완료 신호(analysisReady)가 오면 이 백오프를 기다리지 않고 즉시 재시도하므로,
 *  이 표는 신호가 끝내 안 올 때의 안전망이다. 합계 최대 2분 15초. */
const RETRY_DELAYS_MS = [5000, 10000, 20000, 40000, 60000];

const ANALYZING_MESSAGE = "지금은 분석 중입니다. 영상에서 조각을 만들고 있어요.";
const NO_TRANSCRIPT_MESSAGE = "이 영상은 전사가 부족해 가편집을 만들 수 없습니다.";
/** [SPEED-P0 2026-08-09] 아직 만든 적 없는 프로젝트. 자동으로 만들지 않는다 — 아래 사유. */
const NEEDS_BUILD_MESSAGE = "아직 거친 편집본이 없습니다.";

/** 응답을 '아직(전사 미완)'과 '진짜 없음'으로 가른다.
 *  서버의 422 insufficient_text 판정은 건드리지 않는다 — 읽는 시점만 옮긴다. */
const classifyError = async (response: Response) => {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (detail?.error === "insufficient_text") {
    return { insufficientText: true, message: NO_TRANSCRIPT_MESSAGE };
  }
  if (typeof detail === "string") return { insufficientText: false, message: detail };
  if (detail?.message) {
    return { insufficientText: false, message: `가편집을 만들지 못했습니다: ${String(detail.message)}` };
  }
  return { insufficientText: false, message: `HTTP ${response.status}` };
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
  analysisReady = false,
}) => {
  const [data, setData] = useState<RoughCutData | null>(null);
  const [ledgerItems, setLedgerItems] = useState<LedgerTranscriptItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // [FIRST-RUN 2026-08-04] 재시도 상태. 프로젝트가 바뀌면 전부 처음으로 돌아간다.
  const [exhausted, setExhausted] = useState(false);
  const [manualRetryTick, setManualRetryTick] = useState(0);
  // [SPEED-P0 2026-08-09] 거친 편집본을 '만들' 권한은 국장 손에만 있다. 0 = 아직 안 눌렀다.
  const [buildTick, setBuildTick] = useState(0);
  const [needsBuild, setNeedsBuild] = useState(false);
  const loadedForRef = useRef<string | null>(null);
  const attemptRef = useRef(0);
  useEffect(() => {
    loadedForRef.current = null;
    attemptRef.current = 0;
    setExhausted(false);
    setBuildTick(0);        // [SPEED-P0] 프로젝트가 바뀌면 '만들기' 승인도 따라가지 않는다.
    setNeedsBuild(false);
  }, [projectId]);

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
    // [FIRST-RUN 2026-08-04] 이미 뜬 프로젝트는 다시 부르지 않는다.
    //   analysisReady 가 나중에 바뀌어도 성공한 화면을 재요청으로 흔들지 않는다(F-6).
    if (loadedForRef.current === projectId) return;
    let active = true;
    let timer: number | undefined;
    const load = async () => {
      setLoading(true);
      setError(null);
      setData(null);
      try {
        let response = await fetch(
          `/api/rough-cut/project/${encodeURIComponent(projectId)}`,
        );
        // [MAP-1 2026-08-12] 새 계약: "아직 안 만들었다" = 200 + status:"not_generated".
        //   404 는 더 이상 이 뜻으로 오지 않는다(main.py:7161) — 콘솔 빨간 줄이 사라진다.
        //   body 를 여기서 한 번만 읽고 아래로 넘긴다(Response 는 두 번 못 읽는다).
        let prefetched: any = null;
        if (response.ok) {
          prefetched = await response.json().catch(() => null);
          // 200 인데 본문이 JSON 이 아니다 = 계약 위반. 아래에서 다시 읽을 수 없으므로
          // (스트림은 한 번뿐) 여기서 사실 그대로 끊는다.
          if (prefetched === null) throw new Error("rough_cut_bad_response");
        }
        // OK 도 not_generated 도 아닌 상태(예: no_sources) — 만들 수 있는 것이 없다.
        //   화면에는 이유를 적고 조용히 멈춘다. 빨간 줄도, 만들기 버튼도 남기지 않는다.
        if (prefetched?.status && prefetched.status !== "OK"
            && prefetched.status !== "not_generated") {
          if (active) { setNeedsBuild(false); setError(String(prefetched.message || prefetched.status)); }
          return;
        }
        const notGenerated =
          response.status === 404             // 구판 백엔드 호환(계약 바뀌기 전 배포본)
          || (response.ok && prefetched?.status === "not_generated");
        if (notGenerated) {
          // ★[SPEED-P0 2026-08-09] 여기서 자동으로 POST 하던 자리다. 끊는다.
          //   POST 는 rough-cut 2pass = qwen2.5:7b@8192(4.8GiB)를 기동시킨다.
          //   RX 6600M 8.0GiB 에서는 대화 목소리 gemma3:4b@16384(5.8GiB)와 공존이
          //   불가능해 서로 축출한다(실측 2026-08-09: 축출 사슬 13:26:19→13:36:29,
          //   로드마다 6~9s). 그 대가가 국장 화면의 first_out_ms=69664 였다.
          //   격리 재현: 대화 단독 2.6s → qwen 동시 기동 20.5s (8배).
          //   국장이 사이드바에서 프로젝트를 여는 것은 "가편집을 만들어라"가 아니다.
          //   만드는 것은 버튼으로 옮긴다 — 이미 만든 프로젝트는 GET 200(161ms)이라 무영향.
          if (buildTick === 0) {
            if (active) { setNeedsBuild(true); setError(NEEDS_BUILD_MESSAGE); }
            return;
          }
          if (active) setNeedsBuild(false);
          response = await fetch(
            `/api/rough-cut/project/${encodeURIComponent(projectId)}`,
            { method: "POST" },
          );
          prefetched = null;   // POST 응답은 아직 안 읽었다
        }
        if (!response.ok) {
          const { insufficientText, message } = await classifyError(response);
          // ★핵심: '전사 부족'이 왔는데 조각화가 아직 안 끝났으면 그건 '없음'이 아니라 '아직'이다.
          //   (실측 2026-08-04: 업로드 06:06:10 → 이 컴포넌트 발사 06:07:2x → ASR 완료 06:10:41.
          //    3분 34초 먼저 물어보고 다시 안 물어서 새 프로젝트가 영영 빈 화면이었다.)
          if (insufficientText && !analysisReady) {
            const idx = attemptRef.current;
            if (idx < RETRY_DELAYS_MS.length) {
              attemptRef.current = idx + 1;
              const wait = RETRY_DELAYS_MS[idx];
              if (active) {
                setError(ANALYZING_MESSAGE);
                setExhausted(false);
                console.info(
                  `[FIRST-RUN] 조각화 미완 — ${wait}ms 뒤 재시도 `
                  + `(${idx + 1}/${RETRY_DELAYS_MS.length}) project=${projectId}`,
                );
                timer = window.setTimeout(() => { if (active) void load(); }, wait);
              }
              return;
            }
            // 상한 도달 — 폭격하지 않는다. 화면에 '다시 시도'를 남기고 멈춘다.
            if (active) { setError(ANALYZING_MESSAGE); setExhausted(true); }
            console.warn(`[FIRST-RUN] 재시도 상한(${RETRY_DELAYS_MS.length}회) 도달 — 중지 project=${projectId}`);
            return;
          }
          throw new Error(message);
        }
        const result = prefetched ?? await response.json();
        if (active) {
          loadedForRef.current = projectId;
          attemptRef.current = 0;
          setExhausted(false);
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
      if (timer !== undefined) window.clearTimeout(timer);   // [FIRST-RUN] 예약 재시도 회수
      // [FOLD-VISUAL-ONLY 2026-08-03] ★언마운트가 부모 상태를 죽이지 않는다.
      //   여기서 onData(null) 을 부르면 Index.tsx 의 roughCutData 가 null 이 되고,
      //   그러면 roughCutMapReady=false -> FragmentMap 입력이 [] -> ★조각맵이 통째로 빈다.
      //   실측(국장 화면 2026-08-03 06:02): 전송으로 채팅이 하단 이동 -> 전사 블록이
      //   2.5A 밖으로 -> IO 가 접음 -> 몸통 언마운트 -> 이 줄 -> 조각맵 8 -> 0.
      //   데이터(story.fids 8 · 조각 풀 135)는 하나도 안 지워졌는데 게이트만 닫혔다.
      //   ★"조각맵을 비워야 하는" 진짜 상황은 ★프로젝트 전환뿐이고,
      //     그 경로는 Index.tsx 에 이미 따로 있다(activeNavItem 전환 effect).
      //     이 컴포넌트가 사라지는 것은 '화면에서 안 보이게 됐다'는 뜻일 뿐이다.
      //   ★남겨두면 옛 프로젝트 데이터가 새 방에 남지 않는가? 남지 않는다 —
      //     위 전환 effect 가 먼저 비우고, 이 컴포넌트는 projectId 가 바뀌면
      //     새로 load() 해서 덮어쓴다(deps 에 projectId 가 있다).
    };
    // [FIRST-RUN 2026-08-04] analysisReady 가 deps 에 있다 = 조각화가 끝나는 순간 자동 재발사.
    //   이것이 주 경로이고 RETRY_DELAYS_MS 백오프는 신호가 안 올 때의 안전망이다.
    //   manualRetryTick 은 상한 도달 뒤 사용자가 '다시 시도'를 눌렀을 때만 움직인다.
  }, [onData, projectId, analysisReady, manualRetryTick, buildTick]);

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

  // [TRANSCRIPT-FOLD 2026-08-01 재개정] 높이를 픽셀로 추측하지 않는다.
  //   실패 이력: 12.4rem -> 3줄, 32rem -> 국장 화면에선 "그냥 계속 전사".
  //   원인은 행 높이가 환경마다 다르기 때문이다 — 같은 조각이 내 창에선 4줄로 접히고
  //   국장 창에선 1줄이다(중앙 패널 실폭이 다르다). 행 높이를 상수로 박는 순간 틀린다.
  //   그래서 **6번째 행이 실제로 시작하는 위치**를 재서 거기서 자른다. 폭·글꼴·줄바꿈이
  //   달라져도 언제나 6줄이 남는다. 못 재면(행 6개 미만 등) 자르지 않는다.
  const bodyRef = useRef<HTMLDivElement>(null);
  const [compactHeight, setCompactHeight] = useState<number | null>(null);
  const VISIBLE_ROWS = 6;
  useLayoutEffect(() => {
    if (!folded) { setCompactHeight(null); return; }
    const el = bodyRef.current;
    if (!el) return;
    const measure = () => {
      const rows = el.querySelectorAll<HTMLElement>("[data-rough-cut-span]");
      if (rows.length <= VISIBLE_ROWS) { setCompactHeight(null); return; }
      const top = el.getBoundingClientRect().top;
      const cut = rows[VISIBLE_ROWS].getBoundingClientRect().top;
      const h = Math.round(cut - top + el.scrollTop);
      if (h > 0) setCompactHeight(h);
    };
    measure();
    // 폭이 바뀌면 줄바꿈이 바뀌고 6줄의 높이도 달라진다 — 다시 잰다.
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [folded, displayData]);


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
        className="flex min-h-[220px] w-full max-w-[800px] flex-col items-center justify-center gap-3 text-[13px] text-muted-foreground/60"
        data-rough-cut-error={error || "empty"}
      >
        <span>{error || "전사를 불러오지 못했습니다."}</span>
        {/* [SPEED-P0 2026-08-09] 만들기는 국장이 누른다. 프로젝트를 여는 것만으로
            qwen2.5:7b 가 GPU 를 잡아 대화를 8배 느리게 만들던 자동 발사를 대체한다. */}
        {needsBuild ? (
          <button
            type="button"
            data-rough-cut-build="idle"
            className="rounded-md border border-border px-3 py-1 text-[12px] text-foreground/80 hover:bg-muted"
            onClick={() => {
              setError(null);
              setNeedsBuild(false);
              loadedForRef.current = null;
              setBuildTick((n) => n + 1);
            }}
          >
            거친 편집본 만들기
          </button>
        ) : null}
        {/* [FIRST-RUN 2026-08-04] 자동 재시도 상한에 닿았을 때만 나온다. 평소엔 사람 손이 필요 없다. */}
        {exhausted ? (
          <button
            type="button"
            className="rounded-md border border-border px-3 py-1 text-[12px] text-foreground/80 hover:bg-muted"
            onClick={() => {
              attemptRef.current = 0;
              setExhausted(false);
              setManualRetryTick((n) => n + 1);
            }}
          >
            다시 시도
          </button>
        ) : null}
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
        ref={bodyRef}
        data-transcript-body={folded ? "compact" : "full"}
        data-transcript-compact-h={compactHeight ?? undefined}
        className={folded ? "overflow-y-auto" : undefined}
        style={folded && compactHeight ? { maxHeight: compactHeight } : undefined}
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
