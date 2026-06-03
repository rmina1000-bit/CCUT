import React, { useState, useCallback, useMemo } from "react";
import { Fragment } from "@/data/fragmentData";
import FragmentTile from "./FragmentTile";
import { getUid } from "@/lib/pbeEngine";
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
  onEditFragment?: (f: Fragment) => void;   // [2-2b] 조각편집 진입
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
        // [BETA1] 조각맵 기본 화면에는 active(S)만 표시. 비활성(N)은 내부 보존하되 숨긴다.
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
    const midX = rect.left + rect.width / 2;

    if (e.clientX < midX) {
      setDragOverIndex(realIndex);
    } else {
      setDragOverIndex(realIndex === totalCount - 1 ? totalCount : realIndex + 1);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent, targetRealIndex: number) => {
      console.log("[DEBUG] FragmentMap handleDrop 호출됨, types:", e.dataTransfer.types);
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

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className="flex flex-col bg-card/50 rounded-lg border border-border/20" data-dropzone="fragment-map"
        onDragOver={(e) => {
          const types = e.dataTransfer.types;
          if (
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
          </div>
        </div>

        <div
          className="flex flex-wrap items-start content-start gap-0.5 px-2 py-1.5 min-h-[160px] pb-8"
          onDragOver={(e) => {
            // 조각 tile 위에서는 tile의 onDragOver가 처리 — 여기서는 빈 공간만 처리
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
              if (isOnTile) return; // tile handleDrop이 이미 처리함
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
                  draggable
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
                    <FragmentTile
                      fragment={f}
                      isSelected={selectedFragmentId === uid}
                      isHighlighted={false}
                      isExpanded={expandedFragmentId === uid}
                      hasActiveSelection={!!selectedFragmentId}
                      onClick={() => onFragmentClick(f)}
                      onDoubleClick={() => onFragmentDoubleClick(f)}
                      onEditFragment={onEditFragment ? () => onEditFragment(f) : undefined}

                      widthScale={0.7}
                      variant="edit"
                    />
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
