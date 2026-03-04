import React, { useMemo, useCallback, useRef, useEffect } from 'react';
import { useVideo } from '../context/VideoContext.js';
import { logEvent } from '../utils/logEvent.js';

const FRAG_COLORS = [
  '#1e3a5a', '#1a3a2a', '#3a1e3a', '#3a2a1a', '#1a2a3a', '#2a1a3a',
];
const MIN_GAP = 0.8;

function clamp(lo, hi, v) { return v < lo ? lo : v > hi ? hi : v; }

export default React.memo(function OriginalPanorama({ fragments = [], onFragmentsChange }) {
  const { hoverPlay, hoverStop, setHoverEnabled } = useVideo();
  const trackRef   = useRef(null);
  const fragEls    = useRef([]);
  const handleEls  = useRef([]);
  const fragsRef   = useRef(fragments);

  // Keep ref current so drag closure always has latest data
  useEffect(() => { fragsRef.current = fragments; }, [fragments]);

  const totalDur = useMemo(
    () => fragments.reduce((s, f) => s + f.duration, 0) || 1,
    [fragments],
  );
  const totalDurRef = useRef(totalDur);
  useEffect(() => { totalDurRef.current = totalDur; }, [totalDur]);

  // Compute cumulative left-pct + width-pct for each fragment
  const positions = useMemo(() => {
    let cum = 0;
    return fragments.map((f) => {
      const leftPct  = (cum / totalDur) * 100;
      const widthPct = (f.duration / totalDur) * 100;
      cum += f.duration;
      return { leftPct, widthPct };
    });
  }, [fragments, totalDur]);

  /* ── Hover ─────────────────────────────────────────── */
  const onEnter = useCallback(
    (frag, e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      hoverPlay(frag.id, frag.src || '', frag.start, rect);
    },
    [hoverPlay],
  );

  /* ── Boundary drag ──────────────────────────────────── */
  const onBoundaryMouseDown = useCallback(
    (e, bIdx) => {
      e.preventDefault();
      e.stopPropagation();

      const track = trackRef.current;
      if (!track) return;

      setHoverEnabled(false);
      const handle = handleEls.current[bIdx];
      if (handle) handle.classList.add('dragging');

      const trackRect  = track.getBoundingClientRect();
      const trackW     = trackRect.width;
      const leftIdx    = bIdx;
      const rightIdx   = bIdx + 1;

      const onMouseMove = (me) => {
        const frags   = fragsRef.current;
        const totDur  = totalDurRef.current;
        const prev    = frags[leftIdx];
        const next    = frags[rightIdx];
        if (!prev || !next) return;

        const relX    = me.clientX - trackRect.left;
        const rawTime = (relX / trackW) * totDur;
        const newTime = clamp(prev.start + MIN_GAP, next.end - MIN_GAP, rawTime);

        // cumulative left of leftIdx fragment (unchanged)
        const leftBasePct = positions[leftIdx]?.leftPct ?? 0;
        const newLeftW    = ((newTime - prev.start) / totDur) * 100;
        const newRightL   = leftBasePct + newLeftW;
        const newRightW   = ((next.end - newTime) / totDur) * 100;

        // Direct DOM — zero React re-render during drag
        const lEl = fragEls.current[leftIdx];
        const rEl = fragEls.current[rightIdx];
        const hEl = handleEls.current[bIdx];
        if (lEl) lEl.style.width = `${newLeftW}%`;
        if (rEl) { rEl.style.left = `${newRightL}%`; rEl.style.width = `${newRightW}%`; }
        if (hEl) hEl.style.left = `calc(${newRightL}% - 2px)`;
      };

      const onMouseUp = (me) => {
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup',   onMouseUp);

        if (handle) handle.classList.remove('dragging');
        setHoverEnabled(true);

        const frags   = fragsRef.current;
        const totDur  = totalDurRef.current;
        const prev    = frags[leftIdx];
        const next    = frags[rightIdx];
        if (!prev || !next || !onFragmentsChange) return;

        const relX    = me.clientX - trackRect.left;
        const rawTime = (relX / trackW) * totDur;
        const newTime = Math.round(
          clamp(prev.start + MIN_GAP, next.end - MIN_GAP, rawTime) * 1000,
        ) / 1000;

        const updated = frags.map((f, i) => {
          if (i === leftIdx)  return { ...f, end: newTime,   duration: Math.round((newTime - f.start) * 1000) / 1000 };
          if (i === rightIdx) return { ...f, start: newTime, duration: Math.round((f.end - newTime) * 1000) / 1000 };
          return f;
        });
        onFragmentsChange(updated);
        logEvent('BOUNDARY_ADJUSTED', {
          fragment_id: frags[rightIdx].id,
          new_start:   newTime,
          new_end:     frags[rightIdx].end,
        });
      };

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup',   onMouseUp);
    },
    [positions, onFragmentsChange, setHoverEnabled],
  );

  return (
    <div className="original-panorama">
      <span className="pano-label">Panorama</span>
      <div className="pano-track" ref={trackRef}>

        {/* Fragment blocks — absolutely positioned */}
        {fragments.map((frag, i) => {
          const { leftPct, widthPct } = positions[i] ?? { leftPct: 0, widthPct: 0 };
          const color = FRAG_COLORS[i % FRAG_COLORS.length];
          return (
            <div
              key={frag.id}
              ref={(el) => { fragEls.current[i] = el; }}
              className="pano-frag"
              data-frag-id={frag.id}
              style={{ left: `${leftPct}%`, width: `${widthPct}%`, background: color }}
              onMouseEnter={(e) => onEnter(frag, e)}
              onMouseLeave={() => hoverStop(frag.id)}
              title={`${frag.label || frag.id} — ${frag.duration}s`}
            >
              <span className="pano-frag-label">{frag.label || frag.id}</span>
            </div>
          );
        })}

        {/* Boundary handles — between adjacent fragments */}
        {fragments.slice(0, -1).map((_, i) => {
          const { leftPct, widthPct } = positions[i] ?? { leftPct: 0, widthPct: 0 };
          const boundaryPct = leftPct + widthPct;
          return (
            <div
              key={`b-${i}`}
              ref={(el) => { handleEls.current[i] = el; }}
              className="pano-boundary"
              style={{ left: `calc(${boundaryPct}% - 2px)` }}
              onMouseDown={(e) => onBoundaryMouseDown(e, i)}
              title="Drag to adjust boundary"
            />
          );
        })}

      </div>
    </div>
  );
});
