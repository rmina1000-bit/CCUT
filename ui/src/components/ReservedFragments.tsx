import { Undo2 } from 'lucide-react';
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
  onSelect: (fragment: Fragment) => void;
  onRepositionStart: (fragment: Fragment, event: React.MouseEvent<HTMLDivElement>) => void;
  onRestoreToEdit?: (fragment: Fragment) => void;
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
  onSelect,
  onRepositionStart,
  onRestoreToEdit,
  onThumbnailError
}: ReservedFragmentsProps) {
  return (
    <section className="workspace-section workspace-section--hold">
      <div className="section-header section-header--inline">
        <h3>보류맵</h3>
        <span className="section-count">{fragments.length}</span>
      </div>
      <div className="hold-board hold-board--flex">
        {fragments.length ? null : <p className="hold-empty">Move fragments here to remove them from the edit structure without deleting identity.</p>}
        {fragments.map((fragment) => (
          <div
            key={fragment.fragment_id}
            className="hold-board__item hold-board__item--inline"
            style={{ position: 'relative' }}
            onMouseDown={(event) => onRepositionStart(fragment, event)}
          >
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
              onThumbnailError={onThumbnailError}
            />
            {onRestoreToEdit && (
              <button
                data-action-button="true"
                onClick={(e) => { e.stopPropagation(); onRestoreToEdit(fragment); }}
                className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-secondary/80 flex items-center justify-center hover:bg-primary/20 transition-colors z-10"
                title="편집 대상으로 복귀"
              >
                <Undo2 size={10} className="text-foreground/60" />
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
