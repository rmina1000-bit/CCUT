import React, { useState, useCallback, useMemo, useRef } from "react";
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
  onFragmentsChange: (frags: Fragment[]) => void;
  selectedFragmentId: string | null;
  activeFragmentId?: string | null;
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
  fragments,
  onFragmentsChange,
  selectedFragmentId,
  activeFragmentId,
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
  React.useEffect(() => {
    const activeId = activeFragmentId || selectedFragmentId;
    if (!activeId) return;
    setActiveTextRowId(activeId);
    const el = document.querySelector(`[data-source-fid="${activeId}"], [data-map-fid="${activeId}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  }, [activeFragmentId, selectedFragmentId]);

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
            {modeGateEnabled && modeRound > 1 && (
              <span className="text-[9px] text-primary/70">{modeRound}차</span>
            )}
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
          {(modeGateEnabled && fragmentFace === "text" ? transcriptRows : visibleFragments.map(({ fragment, realIndex }, sourceIndex) => ({ fragment, sourceIndex, realIndex, selectedIndex: sourceIndex, selected: true }))).map(({ fragment: f, realIndex, sourceIndex, selectedIndex, selected }, visIdx) => {
            const uid = getUid(f);
            const seam = seamAfterVisible.get(uid);
            const seamKey = seam
              ? `${seam.leftVisibleFragmentId}-${seam.rightVisibleFragmentId}`
              : null;
            const nextVisible = visIdx < visibleFragments.length - 1 ? visibleFragments[visIdx + 1] : null;
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
                  {dragOverIndex === realIndex && draggedId !== uid && (
                    <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-primary rounded-full z-50 pointer-events-none" style={{ transform: "translateX(-2px)" }} />
                  )}
                  {visIdx === visibleFragments.length - 1 && dragOverIndex === fragments.length && (
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
                          {textEditing?.itemId === (storyTextByFragmentId.get(fid) ?? storyTextItems[sourceIndex])?.timelineItemId ? (
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
