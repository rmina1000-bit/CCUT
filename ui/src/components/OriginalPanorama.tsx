import { useEffect, useMemo, useRef } from 'react';
import { FragmentTile } from './FragmentTile';
import type { Fragment, SourceVideo } from '../types/boundaryTypes';

interface OriginalPanoramaProps {
  sources: SourceVideo[];
  fragments: Fragment[];
  activeSource: string;
  selectedFragmentId: string | null;
  highlightedFragmentId: string | null;
  focusExpandedId: string | null;
  intelligenceOn: boolean;
  fragmentOverrides: Map<string, number>;
  onSourceChange: (sourceId: string) => void;
  onFragmentSelect: (fragment: Fragment) => void;
  onToggleIntelligence: () => void;
  onThumbnailError?: (fragmentId: string) => void;
}

export function OriginalPanorama({
  sources,
  fragments,
  activeSource,
  selectedFragmentId,
  highlightedFragmentId,
  focusExpandedId,
  intelligenceOn,
  fragmentOverrides,
  onSourceChange,
  onFragmentSelect,
  onToggleIntelligence,
  onThumbnailError
}: OriginalPanoramaProps) {
  const stripRef = useRef<HTMLDivElement | null>(null);

  const sourceFragments = useMemo(
    () =>
      fragments
        .filter((fragment) => fragment.source_video === activeSource)
        .sort((left, right) => left.start_frame - right.start_frame),
    [activeSource, fragments]
  );

  useEffect(() => {
    if (!highlightedFragmentId || !stripRef.current) {
      return;
    }

    const node = stripRef.current.querySelector<HTMLElement>(`[data-fragment-id="${highlightedFragmentId}"]`);
    if (node) {
      node.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    }
  }, [highlightedFragmentId, activeSource]);

  return (
    <section className="workspace-section workspace-section--panorama">
      <div className="section-header">
        <div>
          <span className="eyebrow">오리지널 파노라마</span>
          <h3>원본맵</h3>
        </div>
        <button type="button" className="ghost-button" onClick={onToggleIntelligence}>
          {intelligenceOn ? 'Intelligence On' : 'Intelligence Off'}
        </button>
      </div>
      <div className="source-tabs" role="tablist" aria-label="Source videos">
        {sources.map((source) => (
          <button
            key={source.id}
            type="button"
            className={`source-tab${source.id === activeSource ? ' is-active' : ''}`}
            onClick={() => onSourceChange(source.id)}
            role="tab"
            aria-selected={source.id === activeSource}
          >
            {source.label}
          </button>
        ))}
      </div>
      <div className="panorama-strip" ref={stripRef}>
        {sourceFragments.map((fragment) => {
          const isSelected = selectedFragmentId === fragment.fragment_id || highlightedFragmentId === fragment.fragment_id;
          const isDimmed = !!focusExpandedId && focusExpandedId !== fragment.fragment_id;
          return (
            <FragmentTile
              key={fragment.fragment_id}
              fragment={fragment}
              variant="panorama"
              isSelected={isSelected}
              isFocusExpanded={false}
              isTimeLens={false}
              isDimmed={isDimmed}
              isPlaying={false}
              playProgress={0}
              intelligenceOn={intelligenceOn}
              durationOverride={fragmentOverrides.get(fragment.fragment_id)}
              highlighted={highlightedFragmentId === fragment.fragment_id}
              onSingleClick={() => onFragmentSelect(fragment)}
              onThumbnailError={onThumbnailError}
            />
          );
        })}
      </div>
    </section>
  );
}
