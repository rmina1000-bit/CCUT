import { useLayoutEffect, useMemo, useRef } from 'react';
import { FragmentTile } from './FragmentTile';
import { buildStructuralItems, getVisibleFragments } from '../utils/fragmentUtils';
import type { Fragment, PrecisionEntryHandle } from '../types/boundaryTypes';

type DragListenerBinding =
  | { target: 'document'; type: keyof DocumentEventMap; listener: EventListener }
  | { target: 'window'; type: keyof WindowEventMap; listener: EventListener };

interface GlobalDragLifecycleOptions {
  cursor: string;
  listeners: DragListenerBinding[];
}

export function beginGlobalDragLifecycle({
  cursor,
  listeners
}: GlobalDragLifecycleOptions) {
  let cleaned = false;

  document.body.style.cursor = cursor;
  document.body.style.userSelect = 'none';

  listeners.forEach(({ target, type, listener }) => {
    const host = target === 'document' ? document : window;
    host.addEventListener(type, listener);
  });

  return () => {
    if (cleaned) {
      return;
    }

    cleaned = true;

    listeners.forEach(({ target, type, listener }) => {
      const host = target === 'document' ? document : window;
      host.removeEventListener(type, listener);
    });

    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };
}

interface FragmentMapProps {
  editFragments: Fragment[];
  selectedFragmentId: string | null;
  pairSelectedFragmentIds: string[];
  focusExpandedId: string | null;
  timeLensId: string | null;
  playingFragmentId: string | null;
  playProgress: number;
  boundaryHighlightIds: string[];
  isBoundaryDragging: boolean;
  fragmentOverrides: Map<string, number>;
  dragOrigin: 'edit' | 'reserved' | null;
  dragTargetVisibleIndex: number | null;
  replaceTargetId: string | null;
  onFragmentSingleClick: (fragment: Fragment) => void;
  onFragmentDoubleClick: (fragment: Fragment) => void;
  onPairSelectionToggle: (fragment: Fragment) => void;
  onPlayToggle: (fragment: Fragment) => void;
  onExcludeToggle: (fragment: Fragment) => void;
  onMoveToHold: (fragment: Fragment) => void;
  onPrecisionEntryOpen: (handle: PrecisionEntryHandle, anchorRect: DOMRect) => void;
  onThumbnailError?: (fragmentId: string) => void;
  onDragStart: (fragmentId: string, origin: 'edit' | 'reserved') => void;
  onDragTargetIndexChange: (index: number | null) => void;
  onReplaceTargetChange: (fragmentId: string | null) => void;
  onReplaceDrop: (fragmentId: string) => void;
  onDragDrop: () => boolean;
  onDragEnd: () => void;
}

export function FragmentMap({
  editFragments,
  selectedFragmentId,
  pairSelectedFragmentIds,
  focusExpandedId,
  timeLensId,
  playingFragmentId,
  playProgress,
  boundaryHighlightIds,
  isBoundaryDragging,
  fragmentOverrides,
  dragOrigin,
  dragTargetVisibleIndex,
  replaceTargetId,
  onFragmentSingleClick,
  onFragmentDoubleClick,
  onPairSelectionToggle,
  onPlayToggle,
  onExcludeToggle,
  onMoveToHold,
  onPrecisionEntryOpen,
  onThumbnailError,
  onDragStart,
  onDragTargetIndexChange,
  onReplaceTargetChange,
  onReplaceDrop,
  onDragDrop,
  onDragEnd
}: FragmentMapProps) {
  const visibleFragments = useMemo(() => getVisibleFragments(editFragments), [editFragments]);
  const structuralItems = useMemo(() => buildStructuralItems(editFragments), [editFragments]);
  const flowNodeMapRef = useRef(new Map<string, HTMLElement>());
  const fragmentSlotMapRef = useRef(new Map<string, HTMLDivElement>());
  const previousPositionsRef = useRef<Map<string, DOMRect>>(new Map());
  const pointerReorderRef = useRef<{
    fragmentId: string;
    pointerId: number;
    startX: number;
    startY: number;
    originTile: HTMLDivElement;
    active: boolean;
  } | null>(null);
  const pointerReorderCleanupRef = useRef<(() => void) | null>(null);

  const flowSignature = useMemo(
    () =>
      structuralItems
        .map((item) => {
          if (item.type === 'fragment') {
            return [
              'fragment',
              item.fragment.fragment_id,
              fragmentOverrides.get(item.fragment.fragment_id) ?? item.fragment.duration,
              selectedFragmentId === item.fragment.fragment_id ? 'selected' : 'idle',
              replaceTargetId === item.fragment.fragment_id ? 'replace' : 'plain',
              dragTargetVisibleIndex === item.visibleIndex ? 'before' : '',
              dragTargetVisibleIndex === item.visibleIndex + 1 ? 'after' : ''
            ].join(':');
          }

          if (item.type === 'boundary') {
            return ['boundary', item.leftFragment.fragment_id, item.rightFragment.fragment_id].join(':');
          }

          return ['seam', item.seam.leftVisibleFragmentId, item.seam.rightVisibleFragmentId].join(':');
        })
        .join('|'),
    [structuralItems, fragmentOverrides, selectedFragmentId, replaceTargetId, dragTargetVisibleIndex]
  );

  const registerFlowNode = (key: string) => (node: HTMLElement | null) => {
    if (!node) {
      flowNodeMapRef.current.delete(key);
      return;
    }

    flowNodeMapRef.current.set(key, node);
  };

  const registerFragmentSlot = (fragmentId: string) => (node: HTMLDivElement | null) => {
    registerFlowNode(`fragment-${fragmentId}`)(node);

    if (!node) {
      fragmentSlotMapRef.current.delete(fragmentId);
      return;
    }

    fragmentSlotMapRef.current.set(fragmentId, node);
  };

  const resolveNearestDropIndex = (clientX: number, clientY: number) => {
    if (!visibleFragments.length) {
      return 0;
    }

    const slotRects = visibleFragments
      .map((fragment) => ({
        fragmentId: fragment.fragment_id,
        rect: fragmentSlotMapRef.current.get(fragment.fragment_id)?.getBoundingClientRect() || null
      }))
      .filter((entry): entry is { fragmentId: string; rect: DOMRect } => !!entry.rect);

    if (!slotRects.length) {
      return null;
    }

    const slotAnchors = slotRects.map((entry, index) => {
      if (index === 0) {
        return {
          index: 0,
          x: entry.rect.left,
          y: entry.rect.top + entry.rect.height / 2
        };
      }

      const previous = slotRects[index - 1].rect;
      const sameRow = Math.abs(previous.top - entry.rect.top) < Math.max(previous.height, entry.rect.height) / 2;

      return {
        index,
        x: sameRow ? (previous.right + entry.rect.left) / 2 : entry.rect.left - 8,
        y: sameRow ? (previous.top + previous.height / 2 + entry.rect.top + entry.rect.height / 2) / 2 : entry.rect.top + entry.rect.height / 2
      };
    });

    const lastRect = slotRects[slotRects.length - 1].rect;
    slotAnchors.push({
      index: slotRects.length,
      x: lastRect.right,
      y: lastRect.top + lastRect.height / 2
    });

    let nearestIndex = slotAnchors[0].index;
    let nearestDistance = Number.POSITIVE_INFINITY;

    slotAnchors.forEach((anchor) => {
      const dx = anchor.x - clientX;
      const dy = anchor.y - clientY;
      const distance = dx * dx + dy * dy;

      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = anchor.index;
      }
    });

    return nearestIndex;
  };

  const clearPointerReorderSession = () => {
    const session = pointerReorderRef.current;
    pointerReorderRef.current = null;

    if (!session) {
      return;
    }

    window.setTimeout(() => {
      delete session.originTile.dataset.suppressClick;
    }, 0);
  };

  const handleEditPointerDown = (fragment: Fragment, event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || dragOrigin === 'reserved' || isBoundaryDragging) {
      return;
    }

    const target = event.target as HTMLElement | null;
    if (target?.closest('[data-action-button="true"]')) {
      return;
    }

    if (event.metaKey || event.ctrlKey) {
      event.preventDefault();
      event.currentTarget.dataset.suppressClick = 'true';
      onPairSelectionToggle(fragment);
      return;
    }

    pointerReorderCleanupRef.current?.();
    pointerReorderCleanupRef.current = null;

    const originTile = event.currentTarget;
    pointerReorderRef.current = {
      fragmentId: fragment.fragment_id,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originTile,
      active: false
    };

    const onPointerMove = (moveEvent: PointerEvent) => {
      const session = pointerReorderRef.current;
      if (!session || moveEvent.pointerId !== session.pointerId) {
        return;
      }

      const dx = moveEvent.clientX - session.startX;
      const dy = moveEvent.clientY - session.startY;

      if (!session.active) {
        if (Math.hypot(dx, dy) < 6) {
          return;
        }

        session.active = true;
        session.originTile.dataset.suppressClick = 'true';
        onDragStart(session.fragmentId, 'edit');
      }

      moveEvent.preventDefault();
      onReplaceTargetChange(null);
      onDragTargetIndexChange(resolveNearestDropIndex(moveEvent.clientX, moveEvent.clientY));
    };

    const finishPointerDrag = (commit: boolean) => {
      const session = pointerReorderRef.current;
      const shouldCommit = !!session?.active && commit;

      if (shouldCommit) {
        const committed = onDragDrop();
        if (!committed) {
          onDragEnd();
        }
      } else if (session?.active) {
        onDragEnd();
      }

      pointerReorderCleanupRef.current?.();
      pointerReorderCleanupRef.current = null;
      clearPointerReorderSession();
    };

    const onPointerUp = (upEvent: PointerEvent) => {
      if (upEvent.pointerId !== pointerReorderRef.current?.pointerId) {
        return;
      }

      finishPointerDrag(true);
    };

    const onPointerCancel = (cancelEvent: PointerEvent) => {
      if (cancelEvent.pointerId !== pointerReorderRef.current?.pointerId) {
        return;
      }

      finishPointerDrag(false);
    };

    const onKeyDown = (keyEvent: KeyboardEvent) => {
      if (keyEvent.key !== 'Escape') {
        return;
      }

      keyEvent.preventDefault();
      finishPointerDrag(false);
    };

    const onWindowBlur = () => {
      finishPointerDrag(false);
    };

    pointerReorderCleanupRef.current = beginGlobalDragLifecycle({
      cursor: 'grabbing',
      listeners: [
        { target: 'document', type: 'pointermove', listener: onPointerMove as EventListener },
        { target: 'document', type: 'pointerup', listener: onPointerUp as EventListener },
        { target: 'document', type: 'pointercancel', listener: onPointerCancel as EventListener },
        { target: 'document', type: 'keydown', listener: onKeyDown as EventListener },
        { target: 'window', type: 'blur', listener: onWindowBlur as EventListener }
      ]
    });
  };

  useLayoutEffect(() => {
    return () => {
      pointerReorderCleanupRef.current?.();
      pointerReorderCleanupRef.current = null;
      clearPointerReorderSession();
    };
  }, []);

  useLayoutEffect(() => {
    const reducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const nextPositions = new Map<string, DOMRect>();

    flowNodeMapRef.current.forEach((node, key) => {
      nextPositions.set(key, node.getBoundingClientRect());
    });

    flowNodeMapRef.current.forEach((node, key) => {
      const previous = previousPositionsRef.current.get(key);
      const next = nextPositions.get(key);

      if (!previous || !next) {
        return;
      }

      const deltaX = previous.left - next.left;
      const deltaY = previous.top - next.top;

      if (Math.abs(deltaX) < 0.5 && Math.abs(deltaY) < 0.5) {
        return;
      }

      node.style.transition = 'none';
      node.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
      node.style.willChange = 'transform';

      window.requestAnimationFrame(() => {
        node.style.transition = reducedMotion ? 'none' : 'transform 170ms ease-out';
        node.style.transform = 'translate(0px, 0px)';
      });
    });

    previousPositionsRef.current = nextPositions;
  }, [flowSignature]);

  return (
    <section className="workspace-section workspace-section--map">
      <div className="section-header">
        <div>
          <span className="eyebrow">Fragment Map</span>
          <h3>Edit Structure</h3>
        </div>
        <span className="panel-chip">{visibleFragments.length} visible</span>
      </div>

      <div
        className="fragment-map-board"
        aria-label="Fragment structure board"
        onDragOver={(event) => {
          if (dragOrigin !== 'edit') {
            return;
          }

          event.preventDefault();
          onReplaceTargetChange(null);
          onDragTargetIndexChange(resolveNearestDropIndex(event.clientX, event.clientY));
        }}
        onDrop={(event) => {
          if (dragOrigin !== 'edit') {
            return;
          }

          event.preventDefault();
          onDragDrop();
          onDragEnd();
        }}
      >
        {structuralItems.map((item) => {
          if (item.type === 'fragment') {
            const isSelected =
              selectedFragmentId === item.fragment.fragment_id ||
              pairSelectedFragmentIds.includes(item.fragment.fragment_id);
            const isDimmed = !!(focusExpandedId || timeLensId) && !isSelected;
            const dropBefore = dragTargetVisibleIndex === item.visibleIndex;
            const dropAfter = dragTargetVisibleIndex === item.visibleIndex + 1;

            return (
              <div
                key={`fragment-${item.fragment.fragment_id}`}
                className={[
                  'fragment-map-flow-node',
                  'fragment-map-slot',
                  replaceTargetId === item.fragment.fragment_id ? 'is-replace-target' : '',
                  dropBefore ? 'is-drop-before' : '',
                  dropAfter ? 'is-drop-after' : ''
                ]
                  .filter(Boolean)
                  .join(' ')}
                ref={registerFragmentSlot(item.fragment.fragment_id)}
              >
                <FragmentTile
                  fragment={item.fragment}
                  variant="edit"
                  isSelected={isSelected}
                  isFocusExpanded={focusExpandedId === item.fragment.fragment_id}
                  isTimeLens={timeLensId === item.fragment.fragment_id}
                  isDimmed={isDimmed}
                  isPlaying={playingFragmentId === item.fragment.fragment_id}
                  playProgress={playingFragmentId === item.fragment.fragment_id ? playProgress : 0}
                  durationOverride={fragmentOverrides.get(item.fragment.fragment_id)}
                  highlighted={boundaryHighlightIds.includes(item.fragment.fragment_id)}
                  onSingleClick={() => onFragmentSingleClick(item.fragment)}
                  onDoubleClick={() => onFragmentDoubleClick(item.fragment)}
                  onPlayToggle={() => onPlayToggle(item.fragment)}
                  onExcludeToggle={() => onExcludeToggle(item.fragment)}
                  onMoveToHold={() => onMoveToHold(item.fragment)}
                  onThumbnailError={onThumbnailError}
                  draggable={false}
                  onPointerDown={(event) => handleEditPointerDown(item.fragment, event)}
                  onDragOver={(event) => {
                    if (dragOrigin === 'reserved') {
                      event.preventDefault();
                      onReplaceTargetChange(item.fragment.fragment_id);
                      return;
                    }

                    if (dragOrigin === 'edit') {
                      event.preventDefault();
                      onReplaceTargetChange(null);
                      onDragTargetIndexChange(resolveNearestDropIndex(event.clientX, event.clientY));
                    }
                  }}
                  onDrop={(event) => {
                    if (dragOrigin === 'reserved') {
                      event.preventDefault();
                      onReplaceDrop(item.fragment.fragment_id);
                      return;
                    }

                    if (dragOrigin === 'edit') {
                      event.preventDefault();
                      onDragDrop();
                      onDragEnd();
                    }
                  }}
                />
              </div>
            );
          }

          if (item.type === 'boundary') {
            const handleMeta: PrecisionEntryHandle =
              item.leftFragment.source_video === item.rightFragment.source_video
                ? {
                    type: 'same-source-boundary',
                    leftFragmentId: item.leftFragment.fragment_id,
                    rightFragmentId: item.rightFragment.fragment_id
                  }
                : {
                    type: 'cross-source-junction',
                    leftFragmentId: item.leftFragment.fragment_id,
                    rightFragmentId: item.rightFragment.fragment_id
                  };

            return (
              <button
                key={`boundary-${item.leftFragment.fragment_id}-${item.rightFragment.fragment_id}`}
                type="button"
                className="fragment-map-flow-node boundary-handle"
                ref={registerFlowNode(`boundary-${item.leftFragment.fragment_id}-${item.rightFragment.fragment_id}`)}
                onClick={(event) => onPrecisionEntryOpen(handleMeta, event.currentTarget.getBoundingClientRect())}
                aria-haspopup="dialog"
                aria-label={`Open precision editor between ${item.leftFragment.fragment_id} and ${item.rightFragment.fragment_id}`}
              />
            );
          }

          return (
            <button
              key={`seam-${item.seam.leftVisibleFragmentId}-${item.seam.rightVisibleFragmentId}`}
              type="button"
              className="fragment-map-flow-node synthetic-seam"
              ref={registerFlowNode(`seam-${item.seam.leftVisibleFragmentId}-${item.seam.rightVisibleFragmentId}`)}
              onClick={(event) =>
                onPrecisionEntryOpen(
                  {
                    type: 'synthetic-seam',
                    leftVisibleFragmentId: item.seam.leftVisibleFragmentId,
                    rightVisibleFragmentId: item.seam.rightVisibleFragmentId,
                    hiddenFragmentIds: item.seam.hiddenExcludedFragmentIds
                  },
                  event.currentTarget.getBoundingClientRect()
                )
              }
              title={`${item.seam.hiddenExcludedFragmentIds.length} hidden`}
              aria-haspopup="dialog"
              aria-label={`Open precision editor for ${item.seam.hiddenExcludedFragmentIds.length} hidden fragments`}
            >
              <span />
              <span />
              <span />
            </button>
          );
        })}
      </div>
    </section>
  );
}
