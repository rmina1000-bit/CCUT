import { FragmentTile } from './FragmentTile';
import type { Fragment, HoldPosition } from '../types/boundaryTypes';

interface ReservedFragmentsProps {
  fragments: Fragment[];
  positions: Record<string, HoldPosition>;
  selectedFragmentId: string | null;
  focusExpandedId: string | null;
  timeLensId: string | null;
  playingFragmentId: string | null;
  playProgress: number;
  onPlayToggle: (fragment: Fragment) => void;
  onRestore: (fragment: Fragment) => void;
  onSelect: (fragment: Fragment) => void;
  onRepositionStart: (fragment: Fragment, event: React.MouseEvent<HTMLDivElement>) => void;
  onReplaceDragStart: (fragmentId: string) => void;
  onReplaceDragEnd: () => void;
  onThumbnailError?: (fragmentId: string) => void;
}

export function ReservedFragments({
  fragments,
  positions,
  selectedFragmentId,
  focusExpandedId,
  timeLensId,
  playingFragmentId,
  playProgress,
  onPlayToggle,
  onRestore,
  onSelect,
  onRepositionStart,
  onReplaceDragStart,
  onReplaceDragEnd,
  onThumbnailError
}: ReservedFragmentsProps) {
  return (
    <section className="workspace-section workspace-section--hold">
      <div className="section-header">
        <div>
          <span className="eyebrow">보류 구역</span>
          <h3>보류맵</h3>
        </div>
        <span className="panel-chip"></span>
      </div>
      <div className="hold-board">
        {fragments.length ? null : <p className="hold-empty">Move fragments here to remove them from the edit structure without deleting identity.</p>}
        {fragments.map((fragment) => {
          const position = positions[fragment.fragment_id] || { x: 18, y: 18 };
          return (
            <div
              key={fragment.fragment_id}
              className="hold-board__item"
              style={{ left: position.x, top: position.y }}
              onMouseDown={(event) => onRepositionStart(fragment, event)}
            >
              <button
                type="button"
                className="hold-board__replace-handle"
                draggable
                data-action-button="true"
                aria-label={`Drag ${fragment.fragment_id} to replace an edit fragment`}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                onMouseDown={(event) => {
                  event.stopPropagation();
                }}
                onDragStart={(event) => {
                  event.stopPropagation();
                  event.dataTransfer.effectAllowed = 'move';
                  event.dataTransfer.setData('text/plain', fragment.fragment_id);
                  onReplaceDragStart(fragment.fragment_id);
                }}
                onDragEnd={onReplaceDragEnd}
              >
                Replace
              </button>
              <FragmentTile
                fragment={fragment}
                variant="reserved"
                isSelected={selectedFragmentId === fragment.fragment_id}
                isFocusExpanded={false}
                isTimeLens={false}
                isDimmed={!!(focusExpandedId || timeLensId) && selectedFragmentId !== fragment.fragment_id}
                isPlaying={playingFragmentId === fragment.fragment_id}
                playProgress={playingFragmentId === fragment.fragment_id ? playProgress : 0}
                onSingleClick={() => onSelect(fragment)}
                onPlayToggle={() => onPlayToggle(fragment)}
                onRestoreFromHold={() => onRestore(fragment)}
                onThumbnailError={onThumbnailError}
              />
            </div>
          );
        })}
      </div>
    </section>
  );
}
