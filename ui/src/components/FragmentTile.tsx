import { useEffect, useRef, useState } from 'react';
import { formatDuration } from '../utils/fragmentUtils';
import { getFallbackThumbnail } from '../services/thumbnailService';
import type { Fragment, FragmentTileVariant } from '../types/boundaryTypes';

interface FragmentTileProps {
  fragment: Fragment;
  variant: FragmentTileVariant;
  isSelected: boolean;
  isFocusExpanded: boolean;
  isTimeLens: boolean;
  isDimmed: boolean;
  isPlaying: boolean;
  playProgress: number;
  intelligenceOn?: boolean;
  durationOverride?: number;
  onSingleClick?: () => void;
  onDoubleClick?: () => void;
  onPlayToggle?: () => void;
  onExcludeToggle?: () => void;
  onMoveToHold?: () => void;
  onRestoreFromHold?: () => void;
  onThumbnailError?: (fragmentId: string) => void;
  draggable?: boolean;
  onDragStart?: (event: React.DragEvent<HTMLDivElement>) => void;
  onDragEnd?: () => void;
  onDragOver?: (event: React.DragEvent<HTMLDivElement>) => void;
  onDrop?: (event: React.DragEvent<HTMLDivElement>) => void;
  onPointerDown?: (event: React.PointerEvent<HTMLDivElement>) => void;
  highlighted?: boolean;
}

const DIMMED_SCALE: Record<FragmentTileVariant, number> = {
  panorama: 0.96,
  edit: 0.94,
  reserved: 0.97
};

const SELECTED_SCALE: Record<FragmentTileVariant, number> = {
  panorama: 1.05,
  edit: 1.08,
  reserved: 1.04
};

const HEIGHTS: Record<FragmentTileVariant, number> = {
  panorama: 80,
  edit: 120,
  reserved: 66
};

const MAX_WIDTH: Record<FragmentTileVariant, number> = {
  panorama: 120,
  edit: 220,
  reserved: 120
};

const MIN_WIDTH: Record<FragmentTileVariant, number> = {
  panorama: 56,
  edit: 80,
  reserved: 60
};

export function FragmentTile({
  fragment,
  variant,
  isSelected,
  isFocusExpanded,
  isTimeLens,
  isDimmed,
  isPlaying,
  playProgress,
  intelligenceOn,
  durationOverride,
  onSingleClick,
  onDoubleClick,
  onPlayToggle,
  onExcludeToggle,
  onMoveToHold,
  onRestoreFromHold,
  onThumbnailError,
  draggable,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
  onPointerDown,
  highlighted
}: FragmentTileProps) {
  const clickTimer = useRef<number | null>(null);
  const [imageSrc, setImageSrc] = useState(fragment.thumbnail?.thumbnail_url || getFallbackThumbnail(fragment));
  const displayDuration = durationOverride ?? fragment.duration;

  useEffect(() => {
    setImageSrc(fragment.thumbnail?.thumbnail_url || getFallbackThumbnail(fragment));
  }, [fragment]);

  useEffect(() => {
    return () => {
      if (clickTimer.current) {
        window.clearTimeout(clickTimer.current);
      }
    };
  }, []);

  const handleTileClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    if (target.dataset.suppressClick === 'true') {
      delete target.dataset.suppressClick;
      return;
    }

    if (!onSingleClick) {
      return;
    }

    if (variant !== 'edit' || !onDoubleClick) {
      onSingleClick();
      return;
    }

    if (clickTimer.current) {
      window.clearTimeout(clickTimer.current);
      clickTimer.current = null;
      onDoubleClick();
      return;
    }

    clickTimer.current = window.setTimeout(() => {
      clickTimer.current = null;
      onSingleClick();
    }, 220);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (!onSingleClick) {
        return;
      }

      if (variant !== 'edit' || !onDoubleClick) {
        onSingleClick();
        return;
      }

      if (clickTimer.current) {
        window.clearTimeout(clickTimer.current);
        clickTimer.current = null;
        onDoubleClick();
        return;
      }

      clickTimer.current = window.setTimeout(() => {
        clickTimer.current = null;
        onSingleClick();
      }, 220);
    }
  };

  const scale = isSelected ? SELECTED_SCALE[variant] : isDimmed ? DIMMED_SCALE[variant] : 1;
  const opacity = isDimmed ? 0.55 : 1;

  return (
    <div
      className={[
        'fragment-tile',
        `fragment-tile--${variant}`,
        isSelected ? 'is-selected' : '',
        isFocusExpanded ? 'is-focus-expanded' : '',
        isTimeLens ? 'is-time-lens' : '',
        fragment.excluded ? 'is-excluded' : '',
        highlighted ? 'is-highlighted' : ''
      ]
        .filter(Boolean)
        .join(' ')}
      style={{
        width: Math.max(MIN_WIDTH[variant], Math.min(MAX_WIDTH[variant], displayDuration / 30 * 40)),
        height: HEIGHTS[variant],
        transform: `scale(${scale})`,
        opacity,
        zIndex: isSelected ? 30 : undefined
      }}
      role="button"
      tabIndex={0}
      aria-selected={isSelected}
      aria-expanded={variant === 'edit' ? isFocusExpanded || isTimeLens : undefined}
      onClick={handleTileClick}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={onDragOver}
      onDrop={onDrop}
      data-fragment-id={fragment.fragment_id}
    >
      <img
        src={imageSrc}
        alt={`${fragment.fragment_id} thumbnail`}
        className="fragment-tile__thumb"
        onError={() => {
          setImageSrc(getFallbackThumbnail(fragment));
          onThumbnailError?.(fragment.fragment_id);
        }}
      />
      <div className="fragment-tile__shade" />
      <span className="fragment-tile__id">{fragment.fragment_id}</span>
      <span className="fragment-tile__duration">{formatDuration(displayDuration)}</span>
      {fragment.excluded && variant === 'edit' ? <span className="fragment-tile__status">Excluded</span> : null}
      {intelligenceOn && fragment.intelligence ? (
        <div className="fragment-tile__dots" aria-hidden="true">
          {['narrative', 'emotional', 'action'].map((key) => (
            <span
              key={key}
              style={{
                opacity: fragment.intelligence?.[key as keyof typeof fragment.intelligence] as number
              }}
            />
          ))}
        </div>
      ) : null}

      {variant === 'edit' && fragment.intelligence ? (
        <div className="fragment-tile__intel-bar" aria-hidden="true">
          <div
            className="fragment-tile__intel-segment"
            style={{
              flex: fragment.intelligence.hook,
              background: `hsl(211 55% ${40 + fragment.intelligence.hook * 30}%)`
            }}
          />
          <div
            className="fragment-tile__intel-segment"
            style={{
              flex: fragment.intelligence.emotional,
              background: `hsl(0 50% ${35 + fragment.intelligence.emotional * 30}%)`
            }}
          />
        </div>
      ) : null}

      {isPlaying ? (
        <>
          <div className="fragment-tile__progress-fill" style={{ width: `${playProgress}%` }} />
          <div className="fragment-tile__progress-line" style={{ left: `${playProgress}%` }} />
          <div className="fragment-tile__progress-bar">
            <div style={{ width: `${playProgress}%` }} />
          </div>
        </>
      ) : null}

      <div className="fragment-tile__actions">
        {variant !== 'panorama' && onPlayToggle ? (
          <button
            type="button"
            className="tile-action"
            onClick={(event) => {
              event.stopPropagation();
              onPlayToggle();
            }}
            data-action-button="true"
            aria-label={isPlaying ? `Stop ${fragment.fragment_id}` : `Play ${fragment.fragment_id}`}
          >
            {isPlaying ? 'Stop' : 'Play'}
          </button>
        ) : null}
        {variant === 'edit' && onExcludeToggle ? (
          <button
            type="button"
            className="tile-action"
            onClick={(event) => {
              event.stopPropagation();
              onExcludeToggle();
            }}
            data-action-button="true"
            aria-label={fragment.excluded ? `Restore ${fragment.fragment_id}` : `Exclude ${fragment.fragment_id}`}
          >
            {fragment.excluded ? 'Restore' : 'Exclude'}
          </button>
        ) : null}
        {variant === 'edit' && onMoveToHold ? (
          <button
            type="button"
            className="tile-action"
            onClick={(event) => {
              event.stopPropagation();
              onMoveToHold();
            }}
            data-action-button="true"
            aria-label={`Move ${fragment.fragment_id} to Hold Area`}
          >
            Hold
          </button>
        ) : null}
        {variant === 'reserved' && onRestoreFromHold ? (
          <button
            type="button"
            className="tile-action"
            onClick={(event) => {
              event.stopPropagation();
              onRestoreFromHold();
            }}
            data-action-button="true"
            aria-label={`Restore ${fragment.fragment_id} to edit structure`}
          >
            Restore
          </button>
        ) : null}
      </div>
    </div>
  );
}
