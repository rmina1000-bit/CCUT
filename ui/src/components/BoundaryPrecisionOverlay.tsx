import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { FragmentTile } from './FragmentTile';
import { beginGlobalDragLifecycle } from './FragmentMap';
import { applySharedBoundary, buildFragmentOverrideMap, cloneFragments, MIN_FRAGMENT_DURATION } from '../utils/fragmentUtils';
import type { Fragment, PrecisionOverlayState } from '../types/boundaryTypes';

interface BoundaryPrecisionOverlayProps {
  overlay: PrecisionOverlayState;
  editFragments: Fragment[];
  playingFragmentId: string | null;
  playProgress: number;
  onClose: () => void;
  onCommit: (nextChain: Fragment[]) => void;
  onPreviewChange: (fragments: Fragment[]) => void;
  onPreviewClear: () => void;
  onSourceRecall: (fragmentIds: string[]) => void;
  onPlayToggle: (fragment: Fragment) => void;
}

interface EditableBoundary {
  id: string;
  leftIndex: number;
  leftFragmentId: string;
  rightFragmentId: string;
}

function buildChain(overlay: PrecisionOverlayState, editFragments: Fragment[]) {
  return cloneFragments(
    overlay.chainRealIndices
      .map((realIndex) => editFragments[realIndex] || null)
      .filter((fragment): fragment is Fragment => !!fragment)
  );
}

function getBoundaryId(leftFragmentId: string, rightFragmentId: string) {
  return `${leftFragmentId}-${rightFragmentId}`;
}

function buildEditableBoundaries(fragments: Fragment[]): EditableBoundary[] {
  return fragments.slice(0, -1).flatMap((fragment, index) => {
    const nextFragment = fragments[index + 1];
    if (!nextFragment || fragment.source_video !== nextFragment.source_video) {
      return [];
    }

    return [
      {
        id: getBoundaryId(fragment.fragment_id, nextFragment.fragment_id),
        leftIndex: index,
        leftFragmentId: fragment.fragment_id,
        rightFragmentId: nextFragment.fragment_id
      }
    ];
  });
}

function areChainsEqual(left: Fragment[], right: Fragment[]) {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((fragment, index) => {
    const nextFragment = right[index];
    return (
      nextFragment &&
      fragment.fragment_id === nextFragment.fragment_id &&
      fragment.start_frame === nextFragment.start_frame &&
      fragment.end_frame === nextFragment.end_frame &&
      fragment.duration === nextFragment.duration &&
      Boolean(fragment.excluded) === Boolean(nextFragment.excluded)
    );
  });
}

export function BoundaryPrecisionOverlay({
  overlay,
  editFragments,
  playingFragmentId,
  playProgress,
  onClose,
  onCommit,
  onPreviewChange,
  onPreviewClear,
  onSourceRecall,
  onPlayToggle
}: BoundaryPrecisionOverlayProps) {
  const baseChain = useMemo(() => buildChain(overlay, editFragments), [overlay, editFragments]);
  const [overlayFragments, setOverlayFragments] = useState<Fragment[]>(() => cloneFragments(baseChain));
  const [activeBoundaryId, setActiveBoundaryId] = useState<string | null>(overlay.activeBoundaryId);
  const dragCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    setOverlayFragments(cloneFragments(baseChain));
    setActiveBoundaryId(overlay.activeBoundaryId);
  }, [baseChain, overlay.activeBoundaryId]);

  useEffect(() => {
    onPreviewChange(overlayFragments);
  }, [overlayFragments, onPreviewChange]);

  useEffect(() => onPreviewClear, [onPreviewClear]);

  useEffect(() => {
    return () => {
      dragCleanupRef.current?.();
      dragCleanupRef.current = null;
    };
  }, []);

  const overlayStyle = useMemo(
    () => ({
      top: overlay.anchorRect.bottom + 10,
      left: Math.max(16, overlay.anchorRect.left - 32)
    }),
    [overlay.anchorRect]
  );

  const editableBoundaries = useMemo(
    () => buildEditableBoundaries(overlayFragments),
    [overlayFragments]
  );

  const editableBoundaryByLeftIndex = useMemo(
    () => new Map(editableBoundaries.map((boundary) => [boundary.leftIndex, boundary])),
    [editableBoundaries]
  );

  const activeBoundary = useMemo(
    () => editableBoundaries.find((boundary) => boundary.id === activeBoundaryId) || null,
    [editableBoundaries, activeBoundaryId]
  );

  const hasPendingChanges = useMemo(
    () => !areChainsEqual(baseChain, overlayFragments),
    [baseChain, overlayFragments]
  );

  useEffect(() => {
    if (!activeBoundary) {
      return;
    }
    onSourceRecall([activeBoundary.leftFragmentId, activeBoundary.rightFragmentId]);
  }, [activeBoundary, onSourceRecall]);

  const handleInternalBoundaryDrag = (boundary: EditableBoundary, startX: number) => {
    dragCleanupRef.current?.();
    dragCleanupRef.current = null;

    const originalChain = cloneFragments(overlayFragments);
    let delta = 0;
    let raf = 0;

    const update = (event: MouseEvent) => {
      delta = Math.round((event.clientX - startX) / 1.2);
      if (raf) {
        return;
      }

      raf = window.requestAnimationFrame(() => {
        raf = 0;
        const nextChain = applySharedBoundary(originalChain, boundary.leftIndex, delta);
        setOverlayFragments(nextChain);
        onSourceRecall([boundary.leftFragmentId, boundary.rightFragmentId]);
        delta = 0;
      });
    };

    const cleanup = () => {
      if (raf) {
        window.cancelAnimationFrame(raf);
        raf = 0;
      }
      dragCleanupRef.current?.();
      dragCleanupRef.current = null;
    };

    const stop = () => {
      cleanup();
    };

    const cancel = () => {
      cleanup();
      setOverlayFragments(cloneFragments(originalChain));
      onSourceRecall([boundary.leftFragmentId, boundary.rightFragmentId]);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        cancel();
      }
    };

    const onWindowBlur = () => {
      cancel();
    };

    dragCleanupRef.current = beginGlobalDragLifecycle({
      cursor: 'col-resize',
      listeners: [
        { target: 'document', type: 'mousemove', listener: update as EventListener },
        { target: 'document', type: 'mouseup', listener: stop as EventListener },
        { target: 'document', type: 'keydown', listener: onKeyDown as EventListener },
        { target: 'window', type: 'blur', listener: onWindowBlur as EventListener }
      ]
    });
  };

  const durationOverrides = useMemo(() => buildFragmentOverrideMap(overlayFragments), [overlayFragments]);

  const handleBoundarySelect = (boundaryId: string) => {
    setActiveBoundaryId(boundaryId);
  };

  const handleBoundaryPointerDown = (
    event: React.MouseEvent<HTMLButtonElement>,
    boundary: EditableBoundary
  ) => {
    if (activeBoundaryId !== boundary.id) {
      event.preventDefault();
      setActiveBoundaryId(boundary.id);
      return;
    }

    event.preventDefault();
    handleInternalBoundaryDrag(boundary, event.clientX);
  };

  const handleResetBoundary = () => {
    if (!activeBoundary) {
      return;
    }

    const baselineBoundary = buildEditableBoundaries(baseChain).find(
      (boundary) => boundary.id === activeBoundary.id
    );

    if (!baselineBoundary) {
      return;
    }

    const currentBoundaryFrame = overlayFragments[activeBoundary.leftIndex]?.end_frame;
    const baselineBoundaryFrame = baseChain[baselineBoundary.leftIndex]?.end_frame;

    if (typeof currentBoundaryFrame !== 'number' || typeof baselineBoundaryFrame !== 'number') {
      return;
    }

    const nextChain = applySharedBoundary(
      overlayFragments,
      activeBoundary.leftIndex,
      baselineBoundaryFrame - currentBoundaryFrame
    );
    setOverlayFragments(nextChain);
  };

  const handleResetAll = () => {
    dragCleanupRef.current?.();
    dragCleanupRef.current = null;
    setOverlayFragments(cloneFragments(baseChain));
  };

  const handleApply = () => {
    dragCleanupRef.current?.();
    dragCleanupRef.current = null;
    if (!hasPendingChanges) {
      onClose();
      return;
    }
    onCommit(overlayFragments);
  };

  const handleCancel = () => {
    dragCleanupRef.current?.();
    dragCleanupRef.current = null;
    setOverlayFragments(cloneFragments(baseChain));
    setActiveBoundaryId(null);
    onClose();
  };

  const handleBoundaryStep = (direction: -1 | 1) => {
    if (!editableBoundaries.length) {
      return;
    }

    if (!activeBoundaryId) {
      const nextBoundary = direction > 0 ? editableBoundaries[0] : editableBoundaries[editableBoundaries.length - 1];
      setActiveBoundaryId(nextBoundary.id);
      return;
    }

    const currentIndex = editableBoundaries.findIndex((boundary) => boundary.id === activeBoundaryId);
    if (currentIndex === -1) {
      const nextBoundary = direction > 0 ? editableBoundaries[0] : editableBoundaries[editableBoundaries.length - 1];
      setActiveBoundaryId(nextBoundary.id);
      return;
    }

    const nextIndex = (currentIndex + direction + editableBoundaries.length) % editableBoundaries.length;
    setActiveBoundaryId(editableBoundaries[nextIndex].id);
  };

  const editorTitle = overlay.mode === 'cross-source' ? 'Precision Boundary Editor / Cross-source' : 'Precision Boundary Editor';

  const content = (
    <div
      className="precision-overlay"
      style={overlayStyle}
      role="dialog"
      aria-modal="false"
      aria-label={editorTitle}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="precision-overlay__header">
        <div className="precision-overlay__meta">
          <span className="eyebrow">Precision Boundary Editor</span>
          <span className="precision-overlay__scope">
            {overlay.mode === 'cross-source' ? 'Cross-source local transition' : 'Same-source local correction'} · {overlay.fragmentIds.length} fragments
          </span>
        </div>
        <button type="button" className="ghost-button" onClick={handleCancel}>
          Close
        </button>
      </div>
      <div className="precision-overlay__chain">
        {overlayFragments.map((fragment, index) => {
          const boundary = editableBoundaryByLeftIndex.get(index) || null;
          const nextFragment = overlayFragments[index + 1] || null;

          return (
            <div key={fragment.fragment_id} className="precision-overlay__segment">
              <FragmentTile
                fragment={fragment}
                variant="edit"
                isSelected={false}
                isFocusExpanded={false}
                isTimeLens={false}
                isDimmed={false}
                isPlaying={playingFragmentId === fragment.fragment_id}
                playProgress={playingFragmentId === fragment.fragment_id ? playProgress : 0}
                durationOverride={durationOverrides.get(fragment.fragment_id)}
                onPlayToggle={() => onPlayToggle(fragment)}
              />
              {boundary ? (
                <button
                  type="button"
                  className={[
                    'precision-overlay__boundary',
                    activeBoundaryId === boundary.id ? 'is-active' : 'is-inactive'
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => handleBoundarySelect(boundary.id)}
                  onMouseDown={(event) => handleBoundaryPointerDown(event, boundary)}
                  aria-pressed={activeBoundaryId === boundary.id}
                  aria-label={`Select internal boundary between ${boundary.leftFragmentId} and ${boundary.rightFragmentId}`}
                />
              ) : nextFragment ? (
                <div
                  className="precision-overlay__junction"
                  aria-label={`Cross-source transition between ${fragment.fragment_id} and ${nextFragment.fragment_id}`}
                >
                  Transition
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <div className="precision-overlay__footer">
        <span className="precision-overlay__hint">
          {activeBoundary
            ? `Active boundary: ${activeBoundary.leftFragmentId} / ${activeBoundary.rightFragmentId}`
            : 'Select one internal boundary to edit. Cross-source junctions are reveal-only.'}
        </span>
        <div className="precision-overlay__actions">
          <button type="button" className="ghost-button" onClick={() => handleBoundaryStep(-1)} disabled={!editableBoundaries.length}>
            Prev Boundary
          </button>
          <button type="button" className="ghost-button" onClick={() => handleBoundaryStep(1)} disabled={!editableBoundaries.length}>
            Next Boundary
          </button>
          <button type="button" className="ghost-button" onClick={handleResetBoundary} disabled={!activeBoundary}>
            Reset Boundary
          </button>
          <button type="button" className="ghost-button" onClick={handleResetAll} disabled={!hasPendingChanges}>
            Reset All
          </button>
          <button type="button" className="ghost-button" onClick={handleCancel}>
            Cancel
          </button>
          <button type="button" className="ghost-button ghost-button--primary" onClick={handleApply}>
            Apply
          </button>
        </div>
      </div>
      <div className="precision-overlay__footer">
        <span>Hidden chain preserved. Minimum fragment duration {MIN_FRAGMENT_DURATION}f.</span>
      </div>
    </div>
  );

  return createPortal(content, document.body);
}
