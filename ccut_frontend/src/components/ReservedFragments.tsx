import React, { useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { Fragment } from "@/data/fragmentData";
import FragmentTile from "./FragmentTile";
import TrashBin from "./TrashBin";
import { getUid } from "@/lib/fragmentIdentity";

interface Position {
  x: number;
  y: number;
}

interface ReservedFragmentsProps {
  fragments: Fragment[];
  selectedFragmentId: string | null;
  onFragmentClick: (f: Fragment) => void;
  onRestoreFragment: (f: Fragment, insertAt?: number) => void;
  onDeleteFragment?: (f: Fragment) => void;
  deletedFragments: Fragment[];
  onRestoreToHold: (f: Fragment) => void;
  onRestoreToEdit: (f: Fragment) => void;
  onEmptyTrash: () => void;
  holdPositions?: Record<string, { x: number; y: number }>;
  onHoldPositionsChange?: (positions: Record<string, { x: number; y: number }>) => void;
  onDropToHold?: (fid: string, position?: { x: number; y: number }) => void;
}

type DragMode = "idle" | "pending" | "internal" | "external";

const CARD_WIDTH = 120;
const CARD_HEIGHT = 100;
const DRAG_THRESHOLD = 4;

const ReservedFragments: React.FC<ReservedFragmentsProps> = ({
  fragments,
  selectedFragmentId,
  onFragmentClick,
  onRestoreFragment,
  onDeleteFragment,
  deletedFragments,
  onRestoreToHold,
  onRestoreToEdit,
  onEmptyTrash,
  holdPositions = {},
  onHoldPositionsChange,
  onDropToHold,
}) => {
  const boardRef = useRef<HTMLDivElement>(null);
  const trashZoneRef = useRef<HTMLDivElement>(null);

  const [dragMode, setDragMode] = useState<DragMode>("idle");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [externalReadyId, setExternalReadyId] = useState<string | null>(null);
  const [trashHover, setTrashHover] = useState(false);
  const [ghostPos, setGhostPos] = useState<Position | null>(null);

  const pointerIdRef = useRef<number | null>(null);
  const startClientRef = useRef<Position>({ x: 0, y: 0 });
  const startPosRef = useRef<Position>({ x: 0, y: 0 });
  const trashHoverRef = useRef(false);
  // 클릭 vs 드래그 구분용 (이동 거리 누적)
  const movedRef = useRef(false);

  const getPosition = useCallback(
    (fragId: string): Position => {
      return holdPositions[fragId] ?? { x: 12, y: 8 };
    },
    [holdPositions]
  );

  const cleanupAll = useCallback(() => {
    setDragMode("idle");
    setActiveId(null);
    setExternalReadyId(null);
    setGhostPos(null);
    pointerIdRef.current = null;
    trashHoverRef.current = false;
    setTrashHover(false);
    // movedRef 는 클릭 판정 후 리셋되므로 여기선 건드리지 않음
  }, []);

  const isOverTrashZone = useCallback((clientX: number, clientY: number) => {
    if (!trashZoneRef.current) return false;
    const rect = trashZoneRef.current.getBoundingClientRect();
    const pad = 60;
    return (
      clientX >= rect.left - pad &&
      clientX <= rect.right + pad &&
      clientY >= rect.top - pad &&
      clientY <= rect.bottom + pad
    );
  }, []);

  const isOutsideBoard = useCallback((clientX: number, clientY: number) => {
    if (!boardRef.current) return false;
    const rect = boardRef.current.getBoundingClientRect();
    return (
      clientX < rect.left ||
      clientX > rect.right ||
      clientY < rect.top ||
      clientY > rect.bottom
    );
  }, []);

  const clampToBoard = useCallback(
    (clientX: number, clientY: number): Position => {
      const boardRect = boardRef.current?.getBoundingClientRect();
      if (!boardRect) return startPosRef.current;

      const dx = clientX - startClientRef.current.x;
      const dy = clientY - startClientRef.current.y;

      const rawX = startPosRef.current.x + dx;
      const rawY = startPosRef.current.y + dy;

      const x = Math.max(0, Math.min(boardRect.width - CARD_WIDTH, rawX));
      const y = Math.max(0, Math.min(Math.max(boardRect.height - CARD_HEIGHT, 0), rawY));

      return { x, y };
    },
    []
  );

  const handleCardPointerDown = useCallback(
    (e: React.PointerEvent, fid: string) => {
      if (e.button !== 0) return;
      if (!boardRef.current) return;

      const pos = getPosition(fid);

      pointerIdRef.current = e.pointerId;
      startClientRef.current = { x: e.clientX, y: e.clientY };
      startPosRef.current = pos;
      movedRef.current = false;

      setActiveId(fid);
      setExternalReadyId(null);
      setDragMode("pending");
      trashHoverRef.current = false;
      setTrashHover(false);

      try {
        (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
      } catch { }
    },
    [getPosition]
  );

  const handleCardPointerMove = useCallback(
    (e: React.PointerEvent, fid: string) => {
      if (pointerIdRef.current !== e.pointerId) return;
      if (activeId !== fid) return;

      if (dragMode === "external") {
        setGhostPos({ x: e.clientX, y: e.clientY });
        return;
      }

      if (dragMode === "idle") return;

      const dx = e.clientX - startClientRef.current.x;
      const dy = e.clientY - startClientRef.current.y;
      const moved = Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD;

      if (moved) {
        movedRef.current = true;
      }

      if (dragMode === "pending" && moved) {
        setDragMode("internal");
      }

      if (dragMode === "pending" || dragMode === "internal") {
        const nextPos = clampToBoard(e.clientX, e.clientY);
        onHoldPositionsChange?.({ ...holdPositions, [fid]: nextPos });

        const over = isOverTrashZone(e.clientX, e.clientY);
        trashHoverRef.current = over;
        setTrashHover(over);

        if (isOutsideBoard(e.clientX, e.clientY)) {
          setDragMode("external");
          setExternalReadyId(fid);
          setGhostPos({ x: e.clientX, y: e.clientY });
          trashHoverRef.current = false;
          setTrashHover(false);
        }
      }
    },
    [activeId, clampToBoard, dragMode, holdPositions, isOutsideBoard, isOverTrashZone, onHoldPositionsChange]
  );

  const handleCardPointerUp = useCallback(
    (e: React.PointerEvent, fid: string) => {
      if (pointerIdRef.current !== e.pointerId) return;
      if (activeId !== fid) return;

      // [V5] 조각맵 drop 판정 + 위치 정밀 삽입
      if (dragMode === "external" || isOutsideBoard(e.clientX, e.clientY)) {
        const elem = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;

        // 조각 위에 떨어진 경우 (per-item) → 그 조각 뒤에 삽입
        const itemEl = elem?.closest('[data-dropzone="fragment-map-item"]') as HTMLElement | null;
        // 조각맵 영역에 떨어진 경우 (root) → 맨 끝
        const mapEl = elem?.closest('[data-dropzone="fragment-map"]') as HTMLElement | null;

        if (itemEl || mapEl) {
          const frag = fragments.find((f) => getUid(f) === fid);
          if (frag) {
            let insertAt: number | undefined = undefined;
            if (itemEl) {
              const fragIndex = Number(itemEl.dataset.fragIndex);
              if (Number.isFinite(fragIndex)) {
                insertAt = fragIndex + 1;
              }
            }
            // 보류맵에서 제거 + 조각맵으로 복원 (insertAt 동봉)
            const next = { ...holdPositions };
            delete next[fid];
            onHoldPositionsChange?.(next);
            onRestoreFragment(frag, insertAt);
          }
          movedRef.current = false;
          cleanupAll();
          return;
        }
      }

      // 휴지통 위에서 떼면 삭제 (internal 모드)
      if (dragMode === "internal" && trashHoverRef.current) {
        const frag = fragments.find((f) => getUid(f) === fid);
        if (frag) {
          const next = { ...holdPositions };
          delete next[fid];
          onHoldPositionsChange?.(next);
          onDeleteFragment?.(frag);
        }
      }

      // 클릭 판정 (이동 없으면 onFragmentClick)
      if (!movedRef.current && dragMode !== "external") {
        const frag = fragments.find((f) => getUid(f) === fid);
        if (frag) onFragmentClick(frag);
      }

      movedRef.current = false;
      cleanupAll();
    },
    [activeId, cleanupAll, dragMode, fragments, holdPositions, isOutsideBoard, onDeleteFragment, onFragmentClick, onHoldPositionsChange, onRestoreFragment]
  );

  const handleCardPointerCancel = useCallback(
    (e: React.PointerEvent, fid: string) => {
      if (pointerIdRef.current !== e.pointerId) return;
      if (activeId !== fid) return;
      movedRef.current = false;
      cleanupAll();
    },
    [activeId, cleanupAll]
  );

  const handleCardDragStart = useCallback(
    (e: React.DragEvent, f: Fragment) => {
      const fid = getUid(f);

      // external 준비된 카드만 native drag 허용
      if (dragMode !== "external" || externalReadyId !== fid) {
        e.preventDefault();
        return;
      }

      e.dataTransfer.setData("application/ccut-reserve-restore", JSON.stringify(f));
      e.dataTransfer.effectAllowed = "move";
    },
    [dragMode, externalReadyId]
  );

  const handleCardDragEnd = useCallback(() => {
    cleanupAll();
  }, [cleanupAll]);

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 외부 → 보류맵 드롭 (LOCK 드래그 타입 4 종 보존)
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  const handleDragOverHold = useCallback((e: React.DragEvent) => {
    // 보류맵 자체에서 나간 카드는 보류맵이 다시 받지 않음
    if (e.dataTransfer.types.includes("application/ccut-reserve-restore")) {
      return;
    }
    // 휴지통/원본맵/조각맵 → 보류맵 모두 허용
    if (
      e.dataTransfer.types.includes("application/ccut-trash-restore") ||
      e.dataTransfer.types.includes("application/ccut-fragment-hold") ||
      e.dataTransfer.types.includes("application/ccut-edit-fragment")
    ) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
    }
  }, []);

  const handleTrashDrop = useCallback(
    (e: React.DragEvent) => {
      const data = e.dataTransfer.getData("application/ccut-trash-restore");
      if (!data) return;
      e.preventDefault();
      const frag = JSON.parse(data) as Fragment;
      const uid = getUid(frag);
      const boardRect = boardRef.current?.getBoundingClientRect();
      if (boardRect) {
        const x = Math.max(0, e.clientX - boardRect.left - CARD_WIDTH / 2);
        const y = Math.max(0, e.clientY - boardRect.top - CARD_HEIGHT / 2);
        onHoldPositionsChange?.({ ...holdPositions, [uid]: { x, y } });
      }
      onRestoreToHold(frag);
    },
    [onRestoreToHold, holdPositions, onHoldPositionsChange]
  );

  return (
    <>
      <div
        /* [#3+#13 3차 2026-07-19] min-h-full — 카드가 부모(보류맵 패널) 높이를 최소로 채운다.
           높이 지정이 없어 내용(min-h-[220px] board)만큼만 커지던 게 큰 화면에서 카드가
           위쪽에 뜨고 아래가 비는 '공중부양'의 실제 원인이었다(패딩 아님). min-h-full이면
           내용이 적어도 바닥까지 내려가고(dock), 많으면 커져 부모가 스크롤한다. */
        className="relative bg-card/50 rounded-lg overflow-hidden border border-border/20 min-h-full"
        onDragOver={handleDragOverHold}
        onDrop={(e) => {
          // 보류맵 자체 드래그 (reserve-restore)는 보류맵이 받지 않음
          if (e.dataTransfer.types.includes("application/ccut-reserve-restore")) {
            return;
          }

          // 휴지통 → 보류맵
          if (e.dataTransfer.types.includes("application/ccut-trash-restore")) {
            handleTrashDrop(e);
            return;
          }

          // 원본맵 → 보류맵 (fragment-hold 타입)
          if (e.dataTransfer.types.includes("application/ccut-fragment-hold")) {
            e.preventDefault();
            try {
              const frag = JSON.parse(e.dataTransfer.getData("application/ccut-fragment-hold")) as Fragment;
              const boardRect = boardRef.current?.getBoundingClientRect();
              if (boardRect) {
                const x = Math.max(0, e.clientX - boardRect.left - CARD_WIDTH / 2);
                const y = Math.max(0, e.clientY - boardRect.top - CARD_HEIGHT / 2);
                onHoldPositionsChange?.({ ...holdPositions, [getUid(frag)]: { x, y } });
              }
              onDropToHold?.(getUid(frag));
            } catch (err) { }
            return;
          }

          // 조각맵 → 보류맵 (edit-fragment 타입)
          const editData = e.dataTransfer.getData("application/ccut-edit-fragment");
          if (editData && onDropToHold) {
            e.preventDefault();
            try {
              const frag = JSON.parse(editData) as Fragment;
              const uid = getUid(frag);
              const boardRect = boardRef.current?.getBoundingClientRect();
              const x = boardRect ? Math.max(0, e.clientX - boardRect.left - CARD_WIDTH / 2) : 12;
              const y = boardRect ? Math.max(0, e.clientY - boardRect.top - CARD_HEIGHT / 2) : 8;

              onHoldPositionsChange?.({ ...holdPositions, [uid]: { x, y } });
              onDropToHold(uid, { x, y });
            } catch { }
          }
        }}
      >
        <div className="absolute top-0 left-0 right-0 z-50 flex items-center justify-between px-3 py-1 pointer-events-none">
          <div className="flex items-center gap-1.5">
            <h3 className="text-[11px] font-semibold text-foreground/80 uppercase tracking-widest">
              보류맵
            </h3>
            {fragments.length > 0 && (
              <span className="text-[9px] text-muted-foreground/40">{fragments.length}</span>
            )}
          </div>
        </div>

        <div
          ref={boardRef}
          className="relative min-h-[220px] h-full select-none overflow-visible"
          style={{
            cursor:
              dragMode === "internal" ? "grabbing" :
                dragMode === "pending" ? "grab" :
                  dragMode === "external" ? "grabbing" : "default",
          }}
        >
          {fragments.map((f) => {
            const fid = getUid(f);
            const pos = getPosition(fid);
            const isActive = activeId === fid;
            const isInternalActive = isActive && dragMode === "internal";

            return (
              <div
                key={fid}
                className="absolute group"
                draggable={dragMode === "external" && externalReadyId === fid}
                onDragStart={(e) => handleCardDragStart(e, f)}
                onDragEnd={handleCardDragEnd}
                style={{
                  left: pos.x,
                  top: pos.y,
                  zIndex: isActive ? 100 : selectedFragmentId === fid ? 20 : 1,
                  cursor: isActive ? "grabbing" : "grab",
                  transform: isInternalActive && trashHover ? "scale(0.4) rotate(10deg)" : "scale(1)",
                  opacity: isInternalActive && trashHover ? 0.4 : 1,
                  filter: isInternalActive && trashHover ? "blur(2px) saturate(0)" : "none",
                  transition: isActive ? "none" : "box-shadow 120ms ease",
                  touchAction: "none",
                }}
                onPointerDown={(e) => handleCardPointerDown(e, fid)}
                onPointerMove={(e) => handleCardPointerMove(e, fid)}
                onPointerUp={(e) => handleCardPointerUp(e, fid)}
                onPointerCancel={(e) => handleCardPointerCancel(e, fid)}
              >
                <FragmentTile
                  fragment={f}
                  isSelected={selectedFragmentId === fid}
                  isHighlighted={false}
                  hasActiveSelection={!!selectedFragmentId}
                  onClick={() => {
                    // 클릭 발동은 handleCardPointerUp 에서 처리.
                    // FragmentTile 내부 onClick 은 호출되지 않게 비워둠.
                  }}
                  widthScale={0.5}
                  variant="reserved"
                />
              </div>
            );
          })}

          <div ref={trashZoneRef} className="absolute bottom-2 right-2 z-40">
            <div className={`transition-transform duration-150 ${trashHover ? "scale-110" : ""}`}>
              <TrashBin
                deletedFragments={deletedFragments}
                onRestoreToHold={onRestoreToHold}
                onRestoreToEdit={onRestoreToEdit}
                onEmptyTrash={onEmptyTrash}
                onTrashDrop={(f) => onDeleteFragment?.(f)}
                isMagnetic={trashHover}
              />
            </div>
          </div>
        </div>
      </div>

      {dragMode === "external" && externalReadyId && ghostPos && createPortal(
        (() => {
          const frag = fragments.find((f) => getUid(f) === externalReadyId);
          if (!frag) return null;
          return (
            <div
              style={{
                position: "fixed",
                left: ghostPos.x - CARD_WIDTH / 2,
                top: ghostPos.y - CARD_HEIGHT / 2,
                width: CARD_WIDTH,
                height: CARD_HEIGHT,
                pointerEvents: "none",
                zIndex: 9999,
                opacity: 0.85,
                transform: "scale(1.05)",
                filter: "drop-shadow(0 8px 16px rgba(0,0,0,0.4))",
                transition: "none",
              }}
            >
              <FragmentTile
                fragment={frag}
                isSelected={false}
                isHighlighted={false}
                hasActiveSelection={false}
                widthScale={0.5}
                variant="reserved"
              />
            </div>
          );
        })(),
        document.body
      )}
    </>
  );
};

export default ReservedFragments;
