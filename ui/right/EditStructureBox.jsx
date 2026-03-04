import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useVideo } from '../context/VideoContext.js';
import { logEvent } from '../utils/logEvent.js';

const FRAG_COLORS = [
  '#1e3a5a', '#1a3a2a', '#3a1e3a', '#3a2a1a', '#1a2a3a', '#2a1a3a',
];
const MAX_BAR       = 180;
const DRAG_THRESH   = 4;    // px before ghost activates

export default function EditStructureBox({ initialFragments = [] }) {
  const [fragments, setFragments] = useState(initialFragments);
  const [selected,  setSelected]  = useState(new Set());
  const { hoverPlay, hoverStop, setHoverEnabled } = useVideo();

  const fragEls  = useRef([]);
  const fragsRef = useRef(fragments);

  // Keep ref current; also sync updated fragment data (start/end) from parent
  // while preserving local reorder
  useEffect(() => {
    fragsRef.current = fragments;
  }, [fragments]);

  useEffect(() => {
    setFragments((prev) => {
      if (!initialFragments.length) return prev;
      const initMap = new Map(initialFragments.map((f) => [f.id, f]));
      const prevIds = new Set(prev.map((f) => f.id));
      const hasOverlap = initialFragments.some((f) => prevIds.has(f.id));
      // New upload (no overlap) → replace entirely
      if (!hasOverlap) return initialFragments;
      // Same set → update data, keep order, drop removed
      return prev
        .filter((f) => initMap.has(f.id))
        .map((f) => initMap.get(f.id));
    });
  }, [initialFragments]);

  /* ── Hover ─────────────────────────────────────────── */
  const onEnter = useCallback(
    (frag, e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      hoverPlay(frag.id, frag.src || '', frag.start, rect);
    },
    [hoverPlay],
  );

  /* ── Physics drag (mousedown-based, no HTML5 drag API) ────── */
  const handleMouseDown = useCallback(
    (e, idx) => {
      if (e.button !== 0) return;
      e.preventDefault();

      // Snapshot rects once — no layout thrash during drag
      const rects = fragEls.current.map((el) => (el ? el.getBoundingClientRect() : null));
      const srcRect = rects[idx];
      if (!srcRect) return;

      const startX  = e.clientX;
      const startY  = e.clientY;
      const offsetX = e.clientX - srcRect.left;
      const offsetY = e.clientY - srcRect.top;
      const fragH   = srcRect.height + 4;  // height + margin

      let isDrag    = false;
      let dropIdx   = idx;
      let ghost     = null;

      // Calculate drop index from mouse Y using snapped rects
      const getDropIdx = (mouseY) => {
        const len = fragsRef.current.length;
        for (let i = 0; i < rects.length; i++) {
          if (i === idx || !rects[i]) continue;
          if (mouseY < rects[i].top + rects[i].height / 2) return i;
        }
        return len;
      };

      // Apply translateY shift to non-dragged elements
      const applyShift = (dIdx) => {
        fragEls.current.forEach((el, i) => {
          if (!el || i === idx) return;
          el.style.transition = 'transform 120ms ease';
          let shift = 0;
          if (dIdx < idx  && i >= dIdx && i < idx)  shift = +fragH;
          if (dIdx > idx  && i >  idx  && i < dIdx) shift = -fragH;
          el.style.transform = shift !== 0 ? `translateY(${shift}px)` : '';
        });
      };

      const onMove = (me) => {
        if (!isDrag) {
          if (Math.abs(me.clientX - startX) < DRAG_THRESH &&
              Math.abs(me.clientY - startY) < DRAG_THRESH) return;
          isDrag = true;

          // Build ghost clone
          const srcEl = fragEls.current[idx];
          if (srcEl) {
            ghost = srcEl.cloneNode(true);
            ghost.style.cssText = [
              `position:fixed`,
              `left:${srcRect.left}px`,
              `top:${srcRect.top}px`,
              `width:${srcRect.width}px`,
              `height:${srcRect.height}px`,
              `pointer-events:none`,
              `z-index:9999`,
              `opacity:0.92`,
              `transform:scale(1.05)`,
              `box-shadow:0 8px 32px rgba(0,0,0,0.65)`,
              `border-radius:4px`,
              `transition:none`,
              `cursor:grabbing`,
              `margin:0`,
            ].join(';');
            document.body.appendChild(ghost);
            srcEl.style.opacity = '0.3';
          }
          document.body.style.cursor = 'grabbing';
          setHoverEnabled(false);
        }

        // Follow cursor
        if (ghost) {
          ghost.style.left = `${me.clientX - offsetX}px`;
          ghost.style.top  = `${me.clientY - offsetY}px`;
        }

        // Update visual slot
        const newDrop = getDropIdx(me.clientY);
        if (newDrop !== dropIdx) {
          dropIdx = newDrop;
          applyShift(newDrop);
        }
      };

      const onUp = (me) => {
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup',   onUp);

        // Restore all visual state
        if (ghost) { ghost.remove(); ghost = null; }
        fragEls.current.forEach((el) => {
          if (!el) return;
          el.style.transition = 'transform 120ms ease';
          el.style.transform  = '';
          el.style.opacity    = '';
        });
        document.body.style.cursor = '';
        setHoverEnabled(true);

        if (!isDrag) {
          // Treat as click — toggle selection
          setSelected((prev) => {
            const next = new Set(me.shiftKey ? prev : []);
            if (me.shiftKey && prev.has(idx)) next.delete(idx);
            else next.add(idx);
            return next;
          });
          return;
        }

        if (dropIdx === idx) return;  // no-op, same position

        // Reorder — single setFragments call
        const frags = [...fragsRef.current];
        const [moved] = frags.splice(idx, 1);
        const insertAt = dropIdx > idx ? dropIdx - 1 : dropIdx;
        frags.splice(insertAt, 0, moved);
        setFragments(frags);
        setSelected(new Set());
        logEvent('FRAGMENTS_REORDERED', { new_order: frags.map((f) => f.id) });
      };

      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup',   onUp);
    },
    [setHoverEnabled],
  );

  /* ── Render ─────────────────────────────────────────── */
  const maxDur = fragments.reduce((m, f) => Math.max(m, f.duration), 1);

  return (
    <div className="edit-structure-box">
      <div className="esb-label">Edit Structure</div>
      {fragments.map((frag, i) => {
        const color = FRAG_COLORS[i % FRAG_COLORS.length];
        const barW  = Math.round((frag.duration / maxDur) * MAX_BAR);
        const isSel = selected.has(i);
        return (
          <div
            key={frag.id}
            ref={(el) => { fragEls.current[i] = el; }}
            className={`esb-fragment${isSel ? ' selected' : ''}`}
            data-frag-id={frag.id}
            onMouseDown={(e) => handleMouseDown(e, i)}
            onMouseEnter={(e) => onEnter(frag, e)}
            onMouseLeave={() => hoverStop(frag.id)}
          >
            <div className="esb-swatch" style={{ background: color }} />
            <div className="esb-info">
              <div className="esb-id">{frag.label || frag.id}</div>
              <div className="esb-meta">
                {frag.start}s → {frag.end}s &nbsp;·&nbsp; {frag.duration}s
              </div>
              <div
                className="esb-duration-bar"
                style={{ width: barW, background: color }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
