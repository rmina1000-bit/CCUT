import React, { useState, useCallback, useMemo } from "react";
import { Fragment } from "@/data/fragmentData";
import FragmentTile from "./FragmentTile";
import { getUid } from "@/lib/fragmentIdentity";
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
  expandedFragmentId: string | null;
  onFragmentClick: (f: Fragment) => void;
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
  compositionLocked?: boolean;
  fragmentFace?: "image" | "text";
  onFragmentFaceChange?: (face: "image" | "text") => void;
  onApproveComposition?: () => void;
  onReopenComposition?: () => void;
  compositionNotice?: string | null;
  modeRound?: number;
  storyTextItems?: Array<{
    fragmentId?: string | null;
    label?: string;
    dialogue?: string;
    stageDirection?: string;
  }>;
}

const FragmentMap: React.FC<FragmentMapProps> = ({
  fragments,
  onFragmentsChange,
  selectedFragmentId,
  expandedFragmentId,
  onFragmentClick,
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
  compositionLocked,
  fragmentFace = "image",
  onFragmentFaceChange,
  onApproveComposition,
  onReopenComposition,
  compositionNotice,
  modeRound = 1,
  storyTextItems = [],
}) => {
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [hoveredSeamKey, setHoveredSeamKey] = useState<string | null>(null);

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
    if (compositionLocked) {
      e.preventDefault();
      return;
    }
    const uid = getUid(frag);
    e.dataTransfer.setData("text/plain", uid);
    e.dataTransfer.setData("application/ccut-edit-fragment", JSON.stringify(frag));
    e.dataTransfer.effectAllowed = "move";
    setDraggedId(uid);
  }, [compositionLocked]);

  const handleDragOver = useCallback((e: React.DragEvent, realIndex: number, totalCount: number) => {
    if (compositionLocked) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";

    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const midX = rect.left + rect.width / 2;

    if (e.clientX < midX) {
      setDragOverIndex(realIndex);
    } else {
      setDragOverIndex(realIndex === totalCount - 1 ? totalCount : realIndex + 1);
    }
  }, [compositionLocked]);

  const handleDrop = useCallback(
    (e: React.DragEvent, targetRealIndex: number) => {
      console.log("[DEBUG] FragmentMap handleDrop types:", e.dataTransfer.types);
      if (compositionLocked) {
        e.preventDefault();
        return;
      }
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
    [compositionLocked, fragments, onFragmentsChange, onRestoreFragment, onTrashRestore, onSourceRestore]
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
  const textForCard = (f: Fragment, index: number) => {
    const story = storyTextByFragmentId.get(getUid(f)) ?? storyTextItems[index];
    const stage = cleanText(story?.stageDirection || f.stage_direction);
    const dialogue = cleanText(story?.dialogue || f.dialogue || f.transcript || f.original_text || f.intelligence?.description || f.description);
    return {
      label: cleanText(story?.label),
      stage: stage || (!dialogue ? "(무음)" : ""),
      dialogue,
      duration: formatSeconds(f),
    };
  };

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className="flex flex-col bg-card/50 rounded-lg border border-border/20" data-dropzone="fragment-map"
        onDragOver={(e) => {
          if (compositionLocked) return;
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
          if (compositionLocked) {
            e.preventDefault();
            return;
          }
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
              onSourceRestore?.(frag, fragments.length);
            } catch {
              // ignore malformed payload
            }
            return;
          }


        }}
      >
        <div className="flex items-center justify-between px-3 py-2">
          <div className="flex items-center gap-1.5">
            <h3 className="text-[11px] font-semibold text-foreground/80 uppercase tracking-widest">
              조각맵
            </h3>
            <span className="text-[9px] text-muted-foreground/40">
              {activeCount}
              {excludedCount > 0 ? ` · ${excludedCount}` : ""}
            </span>
            {modeGateEnabled && modeRound > 1 && (
              <span className="text-[9px] text-primary/70">{modeRound}차</span>
            )}
          </div>
          {modeGateEnabled && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                className={`px-2 py-1 rounded border text-[10px] ${fragmentFace === "text" ? "bg-primary/15 border-primary/40" : "border-border/30"}`}
                onClick={() => onFragmentFaceChange?.("text")}
              >
                텍스트 조각
              </button>
              <button
                type="button"
                className={`px-2 py-1 rounded border text-[10px] ${fragmentFace === "image" ? "bg-primary/15 border-primary/40" : "border-border/30"}`}
                onClick={() => onFragmentFaceChange?.("image")}
              >
                이미지 조각
              </button>
              {compositionLocked ? (
                <button type="button" className="px-2 py-1 rounded border border-primary/40 text-[10px]" onClick={onReopenComposition}>
                  조각을 다시 고르기
                </button>
              ) : (
                <button type="button" className="px-2 py-1 rounded bg-primary text-primary-foreground text-[10px]" onClick={onApproveComposition}>
                  편집으로 가기
                </button>
              )}
            </div>
          )}
        </div>
        {modeGateEnabled && compositionNotice && (
          <div className="px-3 pb-1 text-[10px] text-primary/80">
            {compositionNotice}
          </div>
        )}

        <div
          className="flex flex-wrap items-start content-start gap-0.5 px-2 py-1.5 min-h-[160px] pb-8"
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
            if (compositionLocked) {
              e.preventDefault();
              return;
            }
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
                onSourceRestore?.(frag, fragments.length);
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
          {visibleFragments.map(({ fragment: f, realIndex }, visIdx) => {
            const uid = getUid(f);
            const seam = seamAfterVisible.get(uid);
            const seamKey = seam
              ? `${seam.leftVisibleFragmentId}-${seam.rightVisibleFragmentId}`
              : null;
            const nextVisible = visIdx < visibleFragments.length - 1 ? visibleFragments[visIdx + 1] : null;

            return (
              <React.Fragment key={(f as any).stable_key || uid}>


                <div
                  draggable={!compositionLocked}
                  onDragStart={(e) => handleDragStart(e, f)}
                  onDragOver={(e) => handleDragOver(e, realIndex, fragments.length)}
                  onDrop={(e) => handleDrop(e, realIndex)}
                  onDragEnd={handleDragEnd}
                  className="flex items-stretch relative"
                  data-dropzone="fragment-map-item"
                  data-frag-index={realIndex}
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
                  <div className="relative group/frag flex items-stretch">
                    {modeGateEnabled && fragmentFace === "text" ? (
                      (() => {
                        const txt = textForCard(f, realIndex);
                        return (
                      <button
                        type="button"
                        onClick={() => onFragmentClick(f)}
                        onDoubleClick={() => onFragmentDoubleClick(f)}
                        className={`w-[132px] min-h-[82px] text-left rounded border px-2 py-1.5 text-[11px] leading-snug bg-background/60 transition-all ${selectedFragmentId === uid ? "border-primary bg-primary/15 shadow-[0_0_0_2px_rgba(96,165,250,0.35)]" : "border-border/30"}`}
                      >
                        {txt.label && <div className="text-[10px] font-black text-primary/80 mb-0.5">{txt.label}</div>}
                        {txt.stage && <div className="italic text-muted-foreground/80 line-clamp-2">{txt.stage}</div>}
                        {txt.dialogue && <div className="text-foreground/90 line-clamp-3 mt-0.5">{txt.dialogue}</div>}
                        {txt.duration && <div className="text-[9px] text-muted-foreground/55 mt-1">{txt.duration}</div>}
                      </button>
                        );
                      })()
                    ) : (
                      <FragmentTile
                        fragment={f}
                        isSelected={selectedFragmentId === uid}
                        isHighlighted={false}
                        isExpanded={expandedFragmentId === uid}
                        hasActiveSelection={!!selectedFragmentId}
                        onClick={() => onFragmentClick(f)}
                        onDoubleClick={() => onFragmentDoubleClick(f)}
                        onEditFragment={onEditFragment && !compositionLocked ? () => onEditFragment(f) : undefined}
                        videoPath={sourceVideoUrls?.[(f as any).source_id] ?? null}
                        compactLabelOnly={modeGateEnabled}
                        widthScale={0.7}
                        variant="edit"
                      />
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

      </div>
    </TooltipProvider>
  );
};

export default FragmentMap;
