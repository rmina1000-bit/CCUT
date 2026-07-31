import React, { useState, useCallback, useMemo, useRef } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { Fragment } from "@/data/fragmentData";
import FragmentTile from "./FragmentTile";
import { getUid } from "@/lib/fragmentIdentity";
import { FRAGMENT_EXCLUDED_STYLE } from "@/lib/fragmentText";
import { TextCaret, editingFromWords, excludedRangesFromEditing, moveTextCaret, WordTok, TextEditing } from "@/lib/ledgerTextEditor";
import {
  SyntheticCollapsedSeam,
  detectSyntheticSeams,
} from "@/types/boundaryTypes";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface FragmentMapProps {
  fragments: Fragment[];
  storyFragmentIds?: string[];
  storyOnly?: boolean;
  onFragmentsChange: (frags: Fragment[]) => void;
  selectedFragmentId: string | null;
  activeFragmentId?: string | null;
  /** [PLAYSTABILITY-FIX-01 1번] 조각 변경의 출처. "sequence"(시퀀스 진행)면 스크롤로 따라가지 않는다. */
  focusOrigin?: "sequence" | "user";
  expandedFragmentId: string | null;
  onFragmentClick: (f: Fragment) => void;
  onFragmentPlay?: (f: Fragment) => void;
  onEditFragment?: (f: Fragment) => void;   // [2-2b] 議곌컖?몄쭛 吏꾩엯
  onFragmentDoubleClick: (f: Fragment) => void;
  onExcludeFragment: (f: Fragment) => void;
  onRestoreFragment: (f: Fragment, insertAt?: number) => void;
  onMoveToHold: (f: Fragment) => void;
  onTrashRestore?: (f: Fragment, insertAt?: number) => void;
  onSourceRestore?: (f: Fragment, insertAt: number) => void;
  onBoundaryClick?: (
    leftFragId: string | null,
    rightFragId: string | null,
    clickSide: "left" | "right" | "center"
  ) => void;
  sourceVideoUrls?: Record<string, string>;
  modeGateEnabled?: boolean;
  fragmentFace?: "image" | "text";
  onFragmentFaceChange?: (face: "image" | "text") => void;
  onApproveComposition?: () => void;
  onReopenComposition?: () => void;
  /** [GATE-LOOP-01 1번] 승인 여부(잠금 아님). 구성 버튼 택일에만 쓴다 — 조작은 절대 막지 않는다. */
  storyApproved?: boolean;
  compositionNotice?: string | null;
  modeRound?: number;
  title?: string;
  textButtonLabel?: string;
  textScope?: "all" | "selected";
  showFaceControls?: boolean;
  showCompositionActions?: boolean;
  sourceFragments?: Fragment[];
  storyTextItems?: Array<{
    fragmentId?: string | null;
    label?: string;
    dialogue?: string;
    stageDirection?: string;
    timelineItemId?: string;
    sourceId?: string;
    revision?: number | null;
    anchorStartMs?: number;
    anchorEndMs?: number;
    trimStartMs?: number;
    trimEndMs?: number;
    words?: WordTok[];
    excludedRanges?: number[][];
  }>;
  programId?: string | null;
  onTextEditStateChanged?: () => void;
}

const FragmentMap: React.FC<FragmentMapProps> = ({
  fragments: inputFragments,
  storyFragmentIds,
  storyOnly = false,
  onFragmentsChange,
  selectedFragmentId,
  activeFragmentId,
  focusOrigin = "user",
  expandedFragmentId,
  onFragmentClick,
  onFragmentPlay,
  onEditFragment,
  onFragmentDoubleClick,
  onExcludeFragment,
  onRestoreFragment,
  onMoveToHold,
  onTrashRestore,
  onSourceRestore,
  onBoundaryClick,
  sourceVideoUrls,
  modeGateEnabled,
  fragmentFace = "image",
  onFragmentFaceChange,
  onApproveComposition,
  onReopenComposition,
  storyApproved = false,
  compositionNotice,
  modeRound = 1,
  title,
  textButtonLabel = "전사",
  textScope = "all",
  showFaceControls = true,
  showCompositionActions = true,
  sourceFragments = [],
  storyTextItems = [],
  programId,
  onTextEditStateChanged,
}) => {
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [hoveredSeamKey, setHoveredSeamKey] = useState<string | null>(null);
  const [activeTextRowId, setActiveTextRowId] = useState<string | null>(null);
  const [hoveredImagePlayId, setHoveredImagePlayId] = useState<string | null>(null);
  const [textEditing, setTextEditing] = useState<TextEditing | null>(null);
  const [textEditItem, setTextEditItem] = useState<(typeof storyTextItems)[number] | null>(null);
  const [textEditNotice, setTextEditNotice] = useState<string | null>(null);
  const hiddenTextInputRef = useRef<HTMLInputElement | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // 가편집 배치는 전체 조각 풀 위에 순서 필터만 얹는다. 아래 visibleFragments는
  // 기존 선택·제외 계약을 그대로 유지하며, 안 보이는 조각의 상태는 바꾸지 않는다.
  const fragments = useMemo(() => {
    if (!storyOnly || !storyFragmentIds) return inputFragments;
    const byId = new Map(inputFragments.map((fragment) => [getUid(fragment), fragment]));
    return storyFragmentIds
      .map((fragmentId) => byId.get(fragmentId))
      .filter((fragment): fragment is Fragment => !!fragment);
  }, [inputFragments, storyFragmentIds, storyOnly]);

  React.useEffect(() => {
    const activeId = activeFragmentId || selectedFragmentId;
    if (!activeId) return;
    setActiveTextRowId(activeId);          // 하이라이트는 출처와 무관하게 항상.
    // [PLAYSTABILITY-FIX-01 1번] 스크롤 따라가기는 **사용자 클릭일 때만**.
    //   시퀀스 재생 진행으로 이걸 호출하면 중앙 채팅이 통째로 밀린다 — 실측 S1.scrollTop 0 -> 2152.
    if (focusOrigin !== "user") return;
    //   조회는 자기 인스턴스 안으로 한정한다. 구판 document.querySelector는 전역이라
    //   우측 조각맵 인스턴스가 자기 요소를 0/11로 못 집고 중앙(DOM 순서상 앞)을 집었다.
    //   OriginalPanorama:59·66과 같은 방식(컨테이너 ref 스코프).
    const el = rootRef.current?.querySelector(`[data-source-fid="${activeId}"], [data-map-fid="${activeId}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  }, [activeFragmentId, selectedFragmentId, focusOrigin]);

  const syntheticSeams = useMemo(() => detectSyntheticSeams(fragments), [fragments]);

  const seamAfterVisible = useMemo(() => {
    const map = new Map<string, SyntheticCollapsedSeam>();
    for (const seam of syntheticSeams) {
      map.set(seam.leftVisibleFragmentId, seam);
    }
    return map;
  }, [syntheticSeams]);

  const visibleFragments = useMemo(
    () =>
      fragments
        .map((f, i) => ({ fragment: f, realIndex: i }))
        // [BETA1] 議곌컖留?湲곕낯 ?붾㈃?먮뒗 active(S)留??쒖떆. 鍮꾪솢??N)? ?대? 蹂댁〈?섎릺 ?④릿??
        .filter(({ fragment }) => !fragment.excluded && fragment.selection_state !== "N"),
    [fragments]
  );

  // [PREVIEW-CUT STEP2] 먼저 보기 — visibleFragments(선택 필터)는 건드리지 않고 그 아래에
  //   보기 필터를 하나 더 얹는다. 안 보임 ≠ 제외이므로 조각 자체는 그대로 살아 있고,
  //   전환은 백엔드가 미리 계산해 실어 보낸 recommend_tier 로 즉시(재요청 없이) 한다.
  //   기본값은 '전체' — 시스템이 사용자보다 먼저 화면을 줄이지 않는다.
  const [previewTier, setPreviewTier] = useState<"simple" | "rich" | "all">("all");
  // [PREVIEW-CUT STEP3] 사용자가 직접 넣고 뺀 것(visible)은 selected 와 별개이며
  //   필터를 다시 계산해도 사용자 행위가 이긴다.
  const [manualShow, setManualShow] = useState<Set<string>>(new Set());
  const [manualHide, setManualHide] = useState<Set<string>>(new Set());

  const tierRank = { simple: 0, rich: 1, all: 2 } as const;
  const inTier = useCallback((f: Fragment) => {
    const tier = (f as any).recommend_tier as keyof typeof tierRank | null | undefined;
    if (previewTier === "all") return true;
    if (!tier) return true;   // 추천값이 아직 없는 조각을 숨기지 않는다(미도달 ≠ 제외)
    return tierRank[tier] <= tierRank[previewTier];
  }, [previewTier]);

  const shownFragments = useMemo(() => {
    if (storyOnly) return visibleFragments;
    if (previewTier === "all" && manualHide.size === 0) return visibleFragments;
    return visibleFragments.filter(({ fragment }) => {
      const uid = getUid(fragment);
      if (manualShow.has(uid)) return true;     // 사용자가 넣은 것은 항상 보인다
      if (manualHide.has(uid)) return false;
      return inTier(fragment);
    });
  }, [visibleFragments, previewTier, manualShow, manualHide, inTier, storyOnly]);

  const previewCount = shownFragments.length;

  // [PREVIEW-CUT 표시 정정] '먼저 보기 N'은 어느 모드에서든 **간단히에 들 조각 수**다.
  //   구판은 지금 보이는 수를 표시해, '전체' 모드에서 '먼저 보기 30 / 전체 30'이 되어
  //   추천이 있는지조차 안 보였다(국장 실사용 혼란 2026-07-31). 수동 넣기/빼기 반영.
  const recommendedCount = useMemo(
    () => visibleFragments.filter(({ fragment }) => {
      const uid = getUid(fragment);
      if (manualHide.has(uid)) return false;
      if (manualShow.has(uid)) return true;
      return (fragment as any).recommend_tier === "simple";
    }).length,
    [visibleFragments, manualShow, manualHide]
  );

  const handleDragStart = useCallback((e: React.DragEvent, frag: Fragment) => {
    const uid = getUid(frag);
    e.dataTransfer.setData("text/plain", uid);
    e.dataTransfer.setData("application/ccut-edit-fragment", JSON.stringify(frag));
    e.dataTransfer.effectAllowed = "move";
    setDraggedId(uid);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, realIndex: number, totalCount: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";

    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    // [DROPPOS-FIX] 세로 스택(전사·텍스트조각)은 Y, 가로 배치(이미지조각)는 X 기준으로 앞/뒤 판정.
    const isVertical = modeGateEnabled && fragmentFace === "text";
    const before = isVertical
      ? e.clientY < rect.top + rect.height / 2
      : e.clientX < rect.left + rect.width / 2;

    if (before) {
      setDragOverIndex(realIndex);
    } else {
      setDragOverIndex(realIndex === totalCount - 1 ? totalCount : realIndex + 1);
    }
  }, [modeGateEnabled, fragmentFace]);

  // [DROPPOS-FIX A] 원본맵 드롭이 타일이 아닌 컨테이너로 떨어질 때의 삽입 위치 —
  // 커서 좌표를 '선택 타일'(draggable=true, realIndex 정확) 미드포인트와 비교해 산출.
  // 어떤 타일보다도 뒤(끝)일 때만 append(fragments.length).
  const computeDropIndex = useCallback((e: React.DragEvent): number => {
    const host = e.currentTarget as HTMLElement;
    const tiles = Array.from(
      host.querySelectorAll('[data-dropzone="fragment-map-item"][draggable="true"]')
    ) as HTMLElement[];
    const isVertical = modeGateEnabled && fragmentFace === "text";
    const pos = isVertical ? e.clientY : e.clientX;
    for (const tile of tiles) {
      const r = tile.getBoundingClientRect();
      const mid = isVertical ? r.top + r.height / 2 : r.left + r.width / 2;
      if (pos < mid) {
        const idx = Number(tile.getAttribute("data-frag-index"));
        if (Number.isFinite(idx)) return idx;
      }
    }
    return fragments.length;
  }, [modeGateEnabled, fragmentFace, fragments.length]);

  const handleDrop = useCallback(
    (e: React.DragEvent, targetRealIndex: number) => {
      console.log("[DEBUG] FragmentMap handleDrop types:", e.dataTransfer.types);
      e.preventDefault();
      e.stopPropagation();
      setDragOverIndex(null);
      setDraggedId(null);

      const reserveData = e.dataTransfer.getData("application/ccut-reserve-restore");
      if (reserveData) {
        try {
          const frag = JSON.parse(reserveData) as Fragment;
          onRestoreFragment(frag, targetRealIndex);
        } catch {
          // ignore malformed payload
        }
        return;
      }

      const trashData = e.dataTransfer.getData("application/ccut-trash-restore");
      if (trashData) {
        try {
          const frag = JSON.parse(trashData) as Fragment;
          onTrashRestore?.(frag, targetRealIndex);
        } catch {
          // ignore malformed payload
        }
        return;
      }

      const holdData = e.dataTransfer.getData("application/ccut-fragment-hold");
      console.log("[DEBUG] holdData:", holdData);
      if (holdData) {
        try {
          const frag = JSON.parse(holdData) as Fragment;
          console.log("[DEBUG] parsed frag:", frag.fragment_id);
          console.log("[DEBUG] onSourceRestore exists:", !!onSourceRestore);
          onSourceRestore?.(frag, targetRealIndex);
        } catch (err) {
          console.error("[DEBUG] json parse error:", err);
        }
        return;
      }

      const sourceId = e.dataTransfer.getData("text/plain");
      if (!sourceId) return;

      const fromIdx = fragments.findIndex((fr) => getUid(fr) === sourceId);
      if (fromIdx === -1 || fromIdx === targetRealIndex) return;

      const newFrags = [...fragments];
      const [moved] = newFrags.splice(fromIdx, 1);
      newFrags.splice(targetRealIndex, 0, moved);
      onFragmentsChange(newFrags);
    },
    [fragments, onFragmentsChange, onRestoreFragment, onTrashRestore, onSourceRestore]
  );

  const handleDragEnd = useCallback(() => {
    setDraggedId(null);
    setDragOverIndex(null);
  }, []);

  const boundaries: number[] = [];
  let runningFrame = 0;
  for (const f of fragments) {
    boundaries.push(runningFrame);
    runningFrame += f.duration;
  }
  boundaries.push(runningFrame);

  const activeCount = visibleFragments.length;
  const excludedCount = fragments.length - activeCount;
  const transcriptFragments = useMemo(
    () => (modeGateEnabled && fragmentFace === "text" && textScope === "all" && sourceFragments.length > 0 ? sourceFragments : visibleFragments.map(({ fragment }) => fragment)),
    [modeGateEnabled, fragmentFace, textScope, sourceFragments, visibleFragments]
  );
  const transcriptRows = useMemo(
    () =>
      transcriptFragments.map((fragment, sourceIndex) => {
        const uid = getUid(fragment);
        const selectedIndex = visibleFragments.findIndex(({ fragment: selected }) => getUid(selected) === uid);
        return {
          fragment,
          sourceIndex,
          realIndex: selectedIndex >= 0 ? visibleFragments[selectedIndex].realIndex : fragments.length,
          selectedIndex,
          selected: selectedIndex >= 0,
        };
      }),
    [transcriptFragments, visibleFragments, fragments.length]
  );
  const storyTextByFragmentId = useMemo(() => {
    const m = new Map<string, (typeof storyTextItems)[number]>();
    storyTextItems.forEach((it) => {
      if (it.fragmentId) m.set(it.fragmentId, it);
    });
    return m;
  }, [storyTextItems]);
  const fragmentSeconds = (f: Fragment) => {
    const rawDuration = Number((f as any).duration);
    if (Number.isFinite(rawDuration)) return Math.max(0, rawDuration / 30);
    const start = Number((f as any).start ?? (f as any).start_sec);
    const end = Number((f as any).end ?? (f as any).end_sec);
    if (Number.isFinite(start) && Number.isFinite(end) && end >= start) return end - start;
    const startFrame = Number((f as any).start_frame);
    const endFrame = Number((f as any).end_frame);
    if (Number.isFinite(startFrame) && Number.isFinite(endFrame) && endFrame >= startFrame) return (endFrame - startFrame) / 30;
    return null;
  };
  const formatSeconds = (f: Fragment) => {
    const seconds = fragmentSeconds(f);
    return seconds === null ? "" : `${seconds.toFixed(1)}s`;
  };
  const cleanText = (v: unknown) => String(v ?? "").trim();
  const cleanLabel = (v: unknown) => {
    const label = cleanText(v);
    return /^(SF_|SRC_|PROP_)/.test(label) ? "" : label;
  };
  const textForCard = (f: Fragment, index: number) => {
    const story = storyTextByFragmentId.get(getUid(f)) ?? storyTextItems[index];
    const stage = cleanText(story?.stageDirection || f.stage_direction);
    const dialogue = cleanText(story?.dialogue || f.dialogue || f.transcript || f.original_text || f.intelligence?.description || f.description);
    return {
      label: cleanLabel(story?.label || (f as any).display_id),
      stage: stage || (!dialogue ? "(무음)" : ""),
      dialogue,
      duration: formatSeconds(f),
    };
  };
  const toggleTranscriptFragment = (f: Fragment, selected: boolean) => {
    const uid = getUid(f);
    setActiveTextRowId(uid);
    onFragmentClick(f);
    if (selected) {
      onFragmentsChange(fragments.filter((fr) => getUid(fr) !== uid));
      onMoveToHold(f);
    } else {
      onFragmentsChange([...fragments, { ...f, excluded: false }]);
      onSourceRestore?.(f, fragments.length);
    }
  };
  const focusTranscriptFragment = (f: Fragment) => {
    const uid = getUid(f);
    setActiveTextRowId(uid);
    onFragmentClick(f);
  };

  const startTextEdit = (f: Fragment, index: number) => {
    const uid = getUid(f);
    const story = storyTextByFragmentId.get(uid) ?? storyTextItems[index];
    if (!story?.timelineItemId || !story.words || story.words.length === 0) {
      setTextEditing(null);
      setTextEditItem(null);
      setTextEditNotice("\uB300\uC0AC \uB370\uC774\uD130 \uC5C6\uC74C");
      setActiveTextRowId(uid);
      return;
    }
    setTextEditNotice(null);
    setActiveTextRowId(uid);
    setTextEditItem(story);
    setTextEditing(editingFromWords(story.timelineItemId, story.words, story.excludedRanges ?? [], 0));
    setTimeout(() => hiddenTextInputRef.current?.focus({ preventScroll: true }), 0);
  };

  const commitTextEdit = async () => {
    const cur = textEditing;
    const item = textEditItem;
    setTextEditing(null);
    setTextEditItem(null);
    if (!cur || !item || !programId) return;
    const { ranges } = excludedRangesFromEditing(cur);
    // [SAVE-INTEGRITY] 조용한 드롭 폐지 — 진짜 no-op일 때만 생략(빈 배열 POST=RESTORE 오작동 방지).
    if (ranges.length === 0 && cur.inactive.size === 0) return;
    const res = await fetch("/api/edit-state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        program_id: programId,
        timeline_item_id: item.timelineItemId,
        source_id: item.sourceId,
        anchor_start_ms: item.anchorStartMs,
        anchor_end_ms: item.anchorEndMs,
        trim_start_ms: item.trimStartMs ?? item.anchorStartMs,
        trim_end_ms: item.trimEndMs ?? item.anchorEndMs,
        revision: item.revision ?? undefined,
        parent_fragment_id: item.fragmentId,
        origin: "TEXT_EDITOR",
        excluded_ranges: ranges,
        removed: false,
        command_type: "EXCLUDE_RANGE",
      }),
    });
    const body = await res.json().catch(() => null);
    if (body?.ok) onTextEditStateChanged?.();
  };

  const onTextEditKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    const key = e.key;
    if (key === "Escape" || key === "Enter") { e.preventDefault(); void commitTextEdit(); return; }
    if (!["ArrowLeft", "ArrowRight", "Home", "End", "Backspace", "Delete"].includes(key)) return;
    e.preventDefault();
    setTextEditing((cur) => {
      if (!cur) return cur;
      const { chars, caret, inactive } = cur;
      if (key === "ArrowLeft") return { ...cur, caret: moveTextCaret(caret, -1, chars) };
      if (key === "ArrowRight") return { ...cur, caret: moveTextCaret(caret, 1, chars) };
      if (key === "Home") return { ...cur, caret: 0 };
      if (key === "End") return { ...cur, caret: chars.length };
      if (key === "Backspace") {
        let p = caret - 1;
        while (p >= 0 && chars[p].s_ms == null) p--;
        if (p < 0) return cur;
        const ni = new Set(inactive); ni.has(p) ? ni.delete(p) : ni.add(p);
        return { ...cur, inactive: ni, caret: p };
      }
      let p = caret;
      while (p < chars.length && chars[p].s_ms == null) p++;
      if (p >= chars.length) return cur;
      const ni = new Set(inactive); ni.has(p) ? ni.delete(p) : ni.add(p);
      return { ...cur, inactive: ni, caret: p + 1 };
    });
  };

  return (
    <TooltipProvider delayDuration={300}>
      <div
        ref={rootRef}
        className={`flex flex-col ${title === "" && !showFaceControls ? "" : "bg-card/50 rounded-lg border border-border/20"}`} data-dropzone="fragment-map"
        onDragOver={(e) => {
                const types = e.dataTransfer.types;
          if (
            types.includes("application/ccut-fragment-hold") ||
            types.includes("application/ccut-trash-restore") ||
            types.includes("application/ccut-reserve-restore")
          ) {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
          }
        }}
        onDrop={(e) => {
          const reserveData = e.dataTransfer.getData("application/ccut-reserve-restore");
          if (reserveData) {
            e.preventDefault();
            try {
              const frag = JSON.parse(reserveData) as Fragment;
              onRestoreFragment(frag, fragments.length);
            } catch {
              // ignore malformed payload
            }
            return;
          }

          const trashData = e.dataTransfer.getData("application/ccut-trash-restore");
          if (trashData) {
            e.preventDefault();
            try {
              const frag = JSON.parse(trashData) as Fragment;
              onTrashRestore?.(frag, fragments.length);
            } catch {
              // ignore malformed payload
            }
            return;
          }

          const holdData = e.dataTransfer.getData("application/ccut-fragment-hold");
          if (holdData) {
            e.preventDefault();
            try {
              const frag = JSON.parse(holdData) as Fragment;
              onSourceRestore?.(frag, computeDropIndex(e));
            } catch {
              // ignore malformed payload
            }
            return;
          }


        }}
      >
        {!(title === "" && !showFaceControls) && (
        <div className="flex items-center justify-between px-3 py-2">
          <div className="flex items-center gap-1.5">
            <h3 className="text-[12px] font-semibold text-foreground/80 uppercase tracking-widest">
              {title ?? "조각맵"}
            </h3>
            <span className="text-[9px] text-muted-foreground/40">
              {activeCount}
              {excludedCount > 0 ? ` · ${excludedCount}` : ""}
            </span>
            {/* [PREVIEW-CUT STEP2] 먼저 보기 N / 전체 M — 상시 표시. 숨긴 조각은 제외가 아니다.
                N은 어느 모드에서든 간단히에 들 조각 수(추천 규모)를 말한다. */}
            {!storyOnly && (
              <span className="text-[9px] text-primary/70">
                먼저 보기 {recommendedCount} / 전체 {activeCount}
              </span>
            )}
            {!storyOnly && manualHide.size > 0 && (
              <button
                type="button"
                onClick={() => setManualHide(new Set())}
                title="내가 뺀 조각을 먼저 보기로 되돌립니다"
                className="text-[9px] text-muted-foreground/50 underline hover:text-foreground/70"
              >
                내가 뺀 {manualHide.size}개 되돌리기
              </button>
            )}
            {modeGateEnabled && modeRound > 1 && (
              <span className="text-[9px] text-primary/70">{modeRound}차</span>
            )}
            {/* [PREVIEW-CUT STEP2] 3단 프리셋. 슬라이더 없음. 필터만 바꾸고 재요청하지 않는다.
                누른다고 재생·포커스·스크롤이 따라 움직이지 않는다(상태만 바뀐다). */}
            {!storyOnly && <div className="ml-1 flex items-center gap-0.5">
              {([["simple", "간단히"], ["rich", "넉넉히"], ["all", "전체"]] as const).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setPreviewTier(key)}
                  title={key === "all" ? "조각 전부 보기" : "먼저 볼 조각만 추려 보기 (나머지도 그대로 있습니다)"}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-semibold transition-colors ${
                    previewTier === key
                      ? "bg-primary/20 text-primary"
                      : "text-muted-foreground/50 hover:text-foreground/70"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>}
          </div>
          {modeGateEnabled && showFaceControls && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                className={`px-2 py-1 rounded border text-[12px] ${fragmentFace === "text" ? "bg-primary/15 border-primary/40" : "border-border/30"}`}
                onClick={() => onFragmentFaceChange?.("text")}
              >
                {textButtonLabel}
              </button>
              <button
                type="button"
                className={`px-2 py-1 rounded border text-[12px] ${fragmentFace === "image" ? "bg-primary/15 border-primary/40" : "border-border/30"}`}
                onClick={() => onFragmentFaceChange?.("image")}
              >
                이미지 조각
              </button>
              {/* [GATE-LOOP-01 1번] 버튼 택일 기준을 '잠금'에서 '승인 여부'로 바꿨다.
                  잠금은 폐지됐고(사용자는 언제든 고칠 수 있다), 이 자리는 단지
                  "아직 승인 안 했으니 승인하러 가기" / "이미 승인됐으니 다시 고르기"다. */}
              {showCompositionActions && (
                storyApproved ? (
                  <button type="button" className="px-2 py-1 rounded border border-primary/40 text-[12px]" onClick={onReopenComposition}>
                    조각을 다시 고르기
                  </button>
                ) : (
                  <button type="button" className="px-2 py-1 rounded bg-primary text-primary-foreground text-[12px]" onClick={onApproveComposition}>
                    편집으로 가기
                  </button>
                )
              )}
            </div>
          )}
        </div>
        )}
        {modeGateEnabled && compositionNotice && (
          <div className="px-3 pb-1 text-[12px] text-primary/80">
            {compositionNotice}
          </div>
        )}

        <div
          className={`flex ${modeGateEnabled && fragmentFace === "text" ? "flex-col items-stretch gap-0 min-h-[360px]" : "flex-wrap items-start content-start gap-0.5 min-h-[160px]"} px-2 py-1.5 pb-8 overflow-y-auto`}
          onDragOver={(e) => {
            // 議곌컖 tile ?꾩뿉?쒕뒗 tile??onDragOver媛 泥섎━ ???ш린?쒕뒗 鍮?怨듦컙留?泥섎━
            const target = e.target as HTMLElement;
            const isOnTile = target.closest('[draggable="true"]');
            if (isOnTile) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            setDragOverIndex(fragments.length);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setDragOverIndex(null);
            setDraggedId(null);

            const reserveData = e.dataTransfer.getData("application/ccut-reserve-restore");
            if (reserveData) {
              try {
                const frag = JSON.parse(reserveData) as Fragment;
                onRestoreFragment(frag, fragments.length);
              } catch { }
              return;
            }

            const trashData = e.dataTransfer.getData("application/ccut-trash-restore");
            if (trashData) {
              try {
                const frag = JSON.parse(trashData) as Fragment;
                onTrashRestore?.(frag, fragments.length);
              } catch { }
              return;
            }

            const holdData = e.dataTransfer.getData("application/ccut-fragment-hold");
            if (holdData) {
              const target = e.target as HTMLElement;
              const isOnTile = target.closest('[draggable="true"]');
              if (isOnTile) return;
              try {
                const frag = JSON.parse(holdData) as Fragment;
                onSourceRestore?.(frag, computeDropIndex(e));
              } catch { }
              return;
            }

            const sourceId = e.dataTransfer.getData("text/plain");
            if (!sourceId) return;
            const fromIdx = fragments.findIndex((fr) => getUid(fr) === sourceId);
            if (fromIdx === -1) return;
            const newFrags = [...fragments];
            const [moved] = newFrags.splice(fromIdx, 1);
            newFrags.push(moved);
            onFragmentsChange(newFrags);
          }}
        >
          {/* [PREVIEW-CUT STEP2] 이미지면 목록만 '먼저 보기' 필터를 탄다. realIndex 는
              원본 인덱스라 드래그·재정렬은 필터와 무관하게 그대로 동작한다. */}
          {(modeGateEnabled && fragmentFace === "text" ? transcriptRows : shownFragments.map(({ fragment, realIndex }, sourceIndex) => ({ fragment, sourceIndex, realIndex, selectedIndex: sourceIndex, selected: true }))).map(({ fragment: f, realIndex, sourceIndex, selectedIndex, selected }, visIdx) => {
            const uid = getUid(f);
            const seam = seamAfterVisible.get(uid);
            const seamKey = seam
              ? `${seam.leftVisibleFragmentId}-${seam.rightVisibleFragmentId}`
              : null;
            const nextVisible = visIdx < shownFragments.length - 1 ? shownFragments[visIdx + 1] : null;
            const fid = (f as any).fragment_id ?? uid;
            const activeId = activeFragmentId || selectedFragmentId;
            const fragmentActive = activeId === uid || activeId === fid || activeTextRowId === uid || activeTextRowId === fid;

            return (
              <React.Fragment key={(f as any).stable_key || uid}>


                <div
                  draggable={selected}
                  onDragStart={(e) => handleDragStart(e, f)}
                  onDragOver={(e) => handleDragOver(e, realIndex, fragments.length)}
                  onDrop={(e) => handleDrop(e, realIndex)}
                  onDragEnd={handleDragEnd}
                  onClick={modeGateEnabled && fragmentFace !== "text" ? () => onFragmentClick(f) : undefined}
                  onMouseDown={modeGateEnabled && fragmentFace !== "text" ? (e) => {
                    if ((e.target as HTMLElement).closest("[data-image-play]")) return;
                    onFragmentClick(f);
                  } : undefined}
                  className={`flex items-stretch relative ${modeGateEnabled && fragmentFace === "text" ? "w-full" : ""}`}
                  data-dropzone="fragment-map-item"
                  data-frag-index={realIndex}
                  data-map-fid={fid}
                  data-fragment-active={fragmentActive ? "true" : "false"}
                  style={{
                    opacity: draggedId === uid ? 0.4 : f.selection_state === "N" ? 0.35 : 1,
                    filter: f.selection_state === "N" ? "saturate(0.3)" : "none",
                  }}
                >
                  {storyOnly && (
                    <>
                      <button
                        type="button"
                        title="스토리에서 빼기"
                        onClick={(e) => {
                          e.stopPropagation();
                          onExcludeFragment(f);
                        }}
                        className="absolute right-1 top-1 z-50 inline-flex h-6 w-6 items-center justify-center rounded bg-background/85 text-muted-foreground/55 shadow-sm transition-colors hover:text-foreground"
                      >
                        <X size={13} />
                      </button>
                      <div className="absolute bottom-1 right-1 z-50 flex items-center rounded bg-background/85 shadow-sm">
                        <button
                          type="button"
                          title="앞으로 이동"
                          disabled={realIndex === 0}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (realIndex === 0) return;
                            const next = [...fragments];
                            [next[realIndex - 1], next[realIndex]] = [next[realIndex], next[realIndex - 1]];
                            onFragmentsChange(next);
                          }}
                          className="inline-flex h-6 w-6 items-center justify-center text-muted-foreground/60 transition-colors hover:text-foreground disabled:opacity-20"
                        >
                          <ChevronLeft size={14} />
                        </button>
                        <button
                          type="button"
                          title="뒤로 이동"
                          disabled={realIndex === fragments.length - 1}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (realIndex === fragments.length - 1) return;
                            const next = [...fragments];
                            [next[realIndex], next[realIndex + 1]] = [next[realIndex + 1], next[realIndex]];
                            onFragmentsChange(next);
                          }}
                          className="inline-flex h-6 w-6 items-center justify-center text-muted-foreground/60 transition-colors hover:text-foreground disabled:opacity-20"
                        >
                          <ChevronRight size={14} />
                        </button>
                      </div>
                    </>
                  )}
                  {dragOverIndex === realIndex && draggedId !== uid && (
                    <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-primary rounded-full z-50 pointer-events-none" style={{ transform: "translateX(-2px)" }} />
                  )}
                  {/* [PREVIEW-CUT STEP3] 먼저 보기에서 빼기 — visible 만 바꾼다.
                      선택(selected)·제외(excluded)는 건드리지 않는다. '전체' 뷰에선 안 띄운다
                      (거기선 뺄 대상이 아니라 전부 보는 자리다). */}
                  {previewTier !== "all" && !(modeGateEnabled && fragmentFace === "text") && (
                    <button
                      type="button"
                      title="먼저 보기에서 빼기 (조각은 그대로 남습니다)"
                      onClick={(e) => {
                        e.stopPropagation();
                        setManualShow((prev) => { const n = new Set(prev); n.delete(uid); return n; });
                        setManualHide((prev) => new Set(prev).add(uid));
                      }}
                      className="absolute right-0.5 top-0.5 z-40 hidden h-4 w-4 items-center justify-center rounded bg-background/80 text-[10px] text-muted-foreground/70 hover:text-foreground group-hover/frag:flex"
                    >
                      −
                    </button>
                  )}
                  {/* [PREVIEW-CUT STEP3] 먼저 보기에 넣기 — 전체 뷰에서 추천 밖 조각을 집어넣는다.
                      사용자가 넣은 것은 필터를 다시 계산해도 계속 보인다(사용자 행위 우선). */}
                  {previewTier === "all" && !(modeGateEnabled && fragmentFace === "text")
                    && (f as any).recommend_tier && (f as any).recommend_tier !== "simple"
                    && !manualShow.has(uid) && (
                    <button
                      type="button"
                      title="먼저 보기에 넣기 (간단히 뷰에서도 계속 보입니다)"
                      onClick={(e) => {
                        e.stopPropagation();
                        setManualHide((prev) => { const n = new Set(prev); n.delete(uid); return n; });
                        setManualShow((prev) => new Set(prev).add(uid));
                      }}
                      className="absolute right-0.5 top-0.5 z-40 hidden h-4 w-4 items-center justify-center rounded bg-background/80 text-[10px] text-muted-foreground/70 hover:text-primary group-hover/frag:flex"
                    >
                      +
                    </button>
                  )}
                  {visIdx === shownFragments.length - 1 && dragOverIndex === fragments.length && (
                    <div className="absolute right-0 top-0 bottom-0 w-0.5 bg-primary rounded-full z-50 pointer-events-none" style={{ transform: "translateX(2px)" }} />
                  )}
                  <div
                    className={`relative group group/frag flex items-stretch ${modeGateEnabled && fragmentFace === "text" ? "w-full" : ""}`}
                    onMouseEnter={() => setHoveredImagePlayId(fid)}
                    onMouseMove={() => setHoveredImagePlayId(fid)}
                    onMouseLeave={() => setHoveredImagePlayId((current) => current === fid ? null : current)}
                  >
                    {modeGateEnabled && fragmentFace === "text" ? (
                      (() => {
                        const txt = textForCard(f, sourceIndex);
                        return (
                      <button
                        type="button"
                        onClick={(e) => {
                          if (e.detail >= 2) { startTextEdit(f, sourceIndex); return; }
                          textScope === "selected" ? focusTranscriptFragment(f) : toggleTranscriptFragment(f, selected);
                        }}
                        onDoubleClick={() => startTextEdit(f, sourceIndex)}
                        data-transcript-row="true"
                        data-transcript-active={fragmentActive ? "true" : "false"}
                        data-transcript-selected={selected ? "true" : "false"}
                        data-source-fid={fid}
                        className={`flex w-full items-center gap-2.5 border-b-[0.5px] border-l-2 px-3 py-[6px] text-left transition-colors ${fragmentActive ? "border-l-primary bg-primary/10" : "border-l-transparent border-border/30"}`}
                      >
                        <span className="flex h-[18px] w-[18px] flex-none items-center justify-center">
                          <span
                            role="button"
                            aria-label="play fragment"
                            className={`flex h-4 w-4 items-center justify-center ${fragmentActive || selected ? "text-foreground/80" : "text-muted-foreground/60 hover:text-foreground/80"}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              onFragmentPlay?.({
                                ...f,
                                video_url: (f as any).video_url ?? sourceVideoUrls?.[(f as any).source_id] ?? sourceVideoUrls?.[(f as any).source_video],
                              } as Fragment);
                            }}
                          >
                            <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true">
                              <path d="M9 7.5 L16.5 12 L9 16.5 Z" fill="currentColor" stroke="currentColor" strokeWidth={2.6} strokeLinejoin="round" strokeLinecap="round" />
                            </svg>
                          </span>
                        </span>
                        <span className="flex h-[18px] w-[18px] flex-none items-center justify-center">
                          {selected && (
                            <span className="flex h-[18px] w-[18px] items-center justify-center rounded-[5px] bg-primary font-mono text-[11px] font-medium leading-none text-primary-foreground">
                              {selectedIndex + 1}
                            </span>
                          )}
                        </span>
                        <span className={`w-7 flex-none font-mono text-[12px] font-medium leading-none ${selected ? "text-primary" : "text-secondary-foreground/60"}`}>
                          {txt.label}
                        </span>
                        <span className={`min-w-0 flex-1 whitespace-normal break-words text-[12px] leading-snug ${selected ? "text-foreground" : "text-muted-foreground/60"}`}>
                          {txt.stage && <span className="italic text-muted-foreground">{txt.stage}</span>}
                          {txt.stage && txt.dialogue && <span> </span>}
                          {/* [LAB-47] textEditing null 가드 — 없으면 지도 전체가 죽는다.
                              구판: textEditing?.itemId === (...)?.timelineItemId
                              편집 중이 아니고(textEditing=null) 그 조각의 원고 항목도 없으면
                              양변이 모두 undefined 라 === 가 true 가 되어 분기에 진입했고,
                              곧바로 textEditing.chars 를 읽어 TypeError 로 화면이 무너졌다.
                              초벌(VF) 프로젝트는 /api/ledger 행이 없어 항상 이 조건에 걸린다 —
                              초벌은 비정상이 아니라 정상 상태이므로 크래시가 아니라 그냥
                              편집 UI 를 띄우지 않는 것이 맞다(가짜 chars 를 채우지 않는다). */}
                          {textEditing && textEditing.itemId === (storyTextByFragmentId.get(fid) ?? storyTextItems[sourceIndex])?.timelineItemId ? (
                            textEditing.chars.map((c, i) => (
                              <React.Fragment key={i}>
                                {textEditing.caret === i && <TextCaret />}
                                <span
                                  onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); setTextEditing((cur) => cur ? { ...cur, caret: i } : cur); }}
                                  style={textEditing.inactive.has(i) ? FRAGMENT_EXCLUDED_STYLE : undefined}
                                >{c.ch === " " ? " " : c.ch}</span>
                              </React.Fragment>
                            ))
                          ) : (storyTextByFragmentId.get(fid) ?? storyTextItems[sourceIndex])?.words?.length ? (
                            (storyTextByFragmentId.get(fid) ?? storyTextItems[sourceIndex])!.words!.map((w, wi) => (
                              <span key={wi} style={w.excluded ? FRAGMENT_EXCLUDED_STYLE : undefined}>{w.w}{" "}</span>
                            ))
                          ) : (
                            txt.dialogue && <span>{txt.dialogue}</span>
                          )}
                        </span>
                        {txt.duration && (
                          <span className="flex-none font-mono text-[11px] text-muted-foreground">
                            {txt.duration}
                          </span>
                        )}
                      </button>
                        );
                      })()
                    ) : (
                      <>
                        <FragmentTile
                          fragment={f}
                          isSelected={selectedFragmentId === uid}
                          isHighlighted={fragmentActive}
                          isExpanded={expandedFragmentId === uid}
                          hasActiveSelection={!!selectedFragmentId}
                          onClick={() => onFragmentClick(f)}
                          onDoubleClick={() => onFragmentDoubleClick(f)}
                          onEditFragment={onEditFragment ? () => onEditFragment(f) : undefined}
                          videoPath={sourceVideoUrls?.[(f as any).source_id] ?? null}
                          compactLabelOnly={modeGateEnabled}
                          widthScale={0.7}
                          variant="edit"
                          orderBadge={modeGateEnabled ? selectedIndex + 1 : null}
                        />
                        {modeGateEnabled && (
                          <button
                            type="button"
                            data-image-play="true"
                            className={`absolute left-1/2 bottom-1 z-30 pointer-events-auto -translate-x-1/2 rounded bg-black/60 px-1.5 py-0.5 text-[12px] text-white/90 transition-opacity hover:bg-black/80 ${hoveredImagePlayId === fid ? "opacity-100" : "opacity-0"}`}
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              onFragmentPlay?.({
                                ...f,
                                video_url: (f as any).video_url ?? sourceVideoUrls?.[(f as any).source_id] ?? sourceVideoUrls?.[(f as any).source_video],
                              } as Fragment);
                            }}
                            onClick={(e) => {
                              e.stopPropagation();
                              onFragmentPlay?.({
                                ...f,
                                video_url: (f as any).video_url ?? sourceVideoUrls?.[(f as any).source_id] ?? sourceVideoUrls?.[(f as any).source_video],
                              } as Fragment);
                            }}
                          >
                            ▶
                          </button>
                        )}
                      </>
                    )}
                  </div>

                  {nextVisible && seam && (
                    <div
                      className="self-stretch flex-shrink-0 flex items-center justify-center"
                      style={{ width: 10 }}
                    >
                      <div className="h-full flex flex-col items-center justify-center gap-[3px]">
                        <div className="w-[3px] h-[3px] rounded-full bg-muted-foreground/25" />
                        <div className="w-[3px] h-[3px] rounded-full bg-muted-foreground/25" />
                        <div className="w-[3px] h-[3px] rounded-full bg-muted-foreground/25" />
                      </div>
                    </div>
                  )}
                </div>
              </React.Fragment>
            );
          })}
        </div>

        {textEditNotice && (
          <div data-transcript-edit-notice="true" className="px-3 py-1 text-[11px] text-muted-foreground">{textEditNotice}</div>
        )}
        {textEditing && (
          <input
            ref={hiddenTextInputRef}
            data-transcript-hidden-editor="true"
            className="sr-only"
            onKeyDown={onTextEditKey}
            onBlur={() => { if (textEditing) void commitTextEdit(); }}
          />
        )}
      </div>
    </TooltipProvider>
  );
};

export default FragmentMap;
