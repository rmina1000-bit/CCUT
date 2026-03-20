import { formatDuration } from '../utils/fragmentUtils';
import type { Fragment, SourceVideo } from '../types/boundaryTypes';

interface CenterPanelProps {
  sources: SourceVideo[];
  selectedFragment: Fragment | null;
  activeSource: string;
  focusExpandedId: string | null;
  timeLensId: string | null;
  intelligenceOn: boolean;
  visibleCount: number;
  precisionPairSelectionIds: string[];
  chatInput: string;
  onChatInputChange: (value: string) => void;
  onChatSubmit: (text: string, anchorRect: DOMRect) => void;
}

type TimeLensSlice = {
  id: string;
  label: string;
  startFrame: number;
  endFrame: number;
  duration: number;
  emphasis: number;
};

const TIME_LENS_LABELS = ['Lead-in', 'Beat', 'Pivot', 'Carry', 'Resolve'];

function buildTimeLensSlices(fragment: Fragment): TimeLensSlice[] {
  const sliceCount = Math.min(TIME_LENS_LABELS.length, Math.max(4, Math.ceil(fragment.duration / 18)));
  const baseDuration = Math.floor(fragment.duration / sliceCount);
  const remainder = fragment.duration % sliceCount;
  const center = (sliceCount - 1) / 2;
  let cursor = fragment.start_frame;

  return Array.from({ length: sliceCount }, (_, index) => {
    const duration = baseDuration + (index < remainder ? 1 : 0);
    const startFrame = cursor;
    const endFrame = cursor + duration;
    cursor = endFrame;

    return {
      id: `${fragment.fragment_id}-lens-${index + 1}`,
      label: TIME_LENS_LABELS[index] || `Window ${index + 1}`,
      startFrame,
      endFrame,
      duration,
      emphasis: Math.max(0.34, 1 - Math.abs(index - center) / Math.max(1, center + 0.5))
    };
  });
}

function MetricBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric-row">
      <span>{label}</span>
      <div className="metric-row__bar">
        <div style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
    </div>
  );
}

export function CenterPanel({
  sources,
  selectedFragment,
  activeSource,
  focusExpandedId,
  timeLensId,
  intelligenceOn,
  visibleCount,
  precisionPairSelectionIds,
  chatInput,
  onChatInputChange,
  onChatSubmit
}: CenterPanelProps) {
  const activeSourceMeta = sources.find((source) => source.id === activeSource) || sources[0];
  const isTimeLensActive = !!selectedFragment && timeLensId === selectedFragment.fragment_id;
  const timeLensSlices = selectedFragment && isTimeLensActive ? buildTimeLensSlices(selectedFragment) : [];

  return (
    <section className="center-panel">
      <div className="panel-card panel-card--summary">
        <div className="panel-header">
          <span className="eyebrow">Source Summary</span>
          <span className="panel-chip">Visible {visibleCount}</span>
        </div>
        <div className="summary-grid">
          {sources.map((source) => (
            <div key={source.id} className={`summary-card${source.id === activeSource ? ' is-active' : ''}`}>
              <span className="summary-card__id">{source.label}</span>
              <strong>{source.totalFrames}f</strong>
              <p>{source.description}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="panel-card panel-card--detail">
        <div className="panel-header">
          <span className="eyebrow">Selected Fragment Detail</span>
          <span className="panel-chip">
            {timeLensId ? 'Time Lens' : focusExpandedId ? 'Focus Expanded' : 'Idle'}
          </span>
        </div>

        {selectedFragment ? (
          <div className="detail-layout">
            <div className="detail-thumb">
              <img src={selectedFragment.thumbnail?.thumbnail_url} alt={`${selectedFragment.fragment_id} thumbnail`} />
            </div>
            <div className="detail-copy">
              <h2>{selectedFragment.fragment_id}</h2>
              <div className="metadata-grid">
                <div>
                  <span>Source</span>
                  <strong>{selectedFragment.source_video}</strong>
                </div>
                <div>
                  <span>Duration</span>
                  <strong>{formatDuration(selectedFragment.duration)}</strong>
                </div>
                <div>
                  <span>Frames</span>
                  <strong>
                    {selectedFragment.start_frame}-{selectedFragment.end_frame}
                  </strong>
                </div>
                <div>
                  <span>Status</span>
                  <strong>{selectedFragment.excluded ? 'Excluded' : 'Visible'}</strong>
                </div>
              </div>
              <p className="structure-context">
                {selectedFragment.fragment_id} is currently aligned with source {activeSourceMeta.label}. Focus and
                Time Lens are kept separate so fragment identity stays stable during inspection.
              </p>
              {isTimeLensActive ? (
                <div className="time-lens-card">
                  <div className="time-lens-card__header">
                    <div>
                      <span className="eyebrow">Time Lens Preview</span>
                      <strong>Read-only internal windows</strong>
                    </div>
                    <span className="panel-chip">{timeLensSlices.length} slices</span>
                  </div>
                  <div className="time-lens-strip" aria-label="Time Lens sub-fragment preview">
                    {timeLensSlices.map((slice, index) => (
                      <div
                        key={slice.id}
                        className={`time-lens-slice${index === Math.floor(timeLensSlices.length / 2) ? ' is-anchor' : ''}`}
                        style={{
                          flex: `${slice.duration} 1 0`,
                          opacity: slice.emphasis
                        }}
                      >
                        <span className="time-lens-slice__label">{slice.label}</span>
                        <strong>{formatDuration(slice.duration)}</strong>
                        <span className="time-lens-slice__frames">
                          {slice.startFrame}-{slice.endFrame}
                        </span>
                      </div>
                    ))}
                  </div>
                  <p className="time-lens-card__note">
                    Time Lens stays read-only for now. It exposes internal pacing windows without turning CCUT into a
                    timeline editor.
                  </p>
                </div>
              ) : null}
              {intelligenceOn && selectedFragment.intelligence ? (
                <div className="metrics-card">
                  <MetricBar label="Narrative" value={selectedFragment.intelligence.narrative} />
                  <MetricBar label="Emotional" value={selectedFragment.intelligence.emotional} />
                  <MetricBar label="Action" value={selectedFragment.intelligence.action} />
                  <MetricBar label="Dialogue" value={selectedFragment.intelligence.dialogue} />
                </div>
              ) : (
                <div className="metrics-placeholder">Intelligence metrics are optional and stay secondary to structure.</div>
              )}
            </div>
          </div>
        ) : (
          <div className="empty-detail">
            Select a fragment from the board, panorama, or Hold Area to inspect its structure identity.
          </div>
        )}
      </div>

      <div className="panel-card panel-card--preview">
        <div className="panel-header">
          <span className="eyebrow">Render Preview</span>
          <span className="panel-chip">Placeholder</span>
        </div>
        <div className="render-preview-placeholder">
          Final playback stays implied by the fragment board. No timeline strip or sequence minimap is rendered here.
        </div>
      </div>

      <div className="panel-card panel-card--chat">
        <div className="panel-header">
          <span className="eyebrow">Chat Bar</span>
          <span className="panel-chip">
            {precisionPairSelectionIds.length === 2
              ? `Pair ${precisionPairSelectionIds.join(' / ')}`
              : 'Precision Entry'}
          </span>
        </div>
        <form
          className="chat-shell"
          onSubmit={(event) => {
            event.preventDefault();
            const formElement = event.currentTarget;
            const inputElement = formElement.querySelector('input');
            const anchorRect =
              inputElement?.getBoundingClientRect() || formElement.getBoundingClientRect();
            onChatSubmit(chatInput, anchorRect);
          }}
        >
          <input
            type="text"
            value={chatInput}
            placeholder="Open precision editor with two fragment ids or two selected edit fragments"
            aria-label="Chat input"
            onChange={(event) => onChatInputChange(event.currentTarget.value)}
          />
          <button type="submit">Send</button>
        </form>
        {precisionPairSelectionIds.length ? (
          <p className="structure-context">
            Precision pair selection: {precisionPairSelectionIds.join(' / ')}. Use Ctrl/Cmd+click on edit fragments to
            update the pair.
          </p>
        ) : (
          <p className="structure-context">
            Precision chat open accepts exactly two fragment ids, or exactly two selected edit fragments plus a precision
            instruction.
          </p>
        )}
      </div>
    </section>
  );
}
