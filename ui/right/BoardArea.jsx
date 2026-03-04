import React, { useState, useCallback, useRef } from 'react';
import { useVideo } from '../context/VideoContext.js';

const FRAG_COLORS = [
  '#1e3a5a', '#1a3a2a', '#3a1e3a', '#3a2a1a', '#1a2a3a', '#2a1a3a',
];

const INIT_OFFSET = { x: 16, y: 28 };
const COL_STEP    = 72;

function makeInitialPositions(frags) {
  return frags.map((f, i) => ({
    ...f,
    x: INIT_OFFSET.x + i * COL_STEP,
    y: INIT_OFFSET.y,
  }));
}

export default function BoardArea({ initialFragments = [] }) {
  const [fragments, setFragments] = useState(() =>
    makeInitialPositions(initialFragments),
  );
  const [selected, setSelected]   = useState(null);
  const { hoverPlay, hoverStop }  = useVideo();

  const dragState = useRef(null);
  const boardRef  = useRef(null);

  const onMouseDown = useCallback((e, id) => {
    e.stopPropagation();
    setSelected(id);
    const frag = fragments.find((f) => f.id === id);
    if (!frag) return;
    dragState.current = {
      id,
      startMouseX: e.clientX,
      startMouseY: e.clientY,
      startFragX:  frag.x,
      startFragY:  frag.y,
    };

    const onMove = (me) => {
      const { id, startMouseX, startMouseY, startFragX, startFragY } = dragState.current;
      const dx = me.clientX - startMouseX;
      const dy = me.clientY - startMouseY;
      const board = boardRef.current;
      const maxX  = board ? board.offsetWidth  - 60 : 9999;
      const maxY  = board ? board.offsetHeight - 32 : 9999;
      setFragments((prev) =>
        prev.map((f) =>
          f.id === id
            ? { ...f, x: Math.max(0, Math.min(maxX, startFragX + dx)),
                       y: Math.max(0, Math.min(maxY, startFragY + dy)) }
            : f,
        ),
      );
    };

    const onUp = () => {
      dragState.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup',   onUp);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup',   onUp);
  }, [fragments]);

  const onEnter = useCallback(
    (frag, e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      hoverPlay(frag.id, frag.src || '', frag.start, rect);
    },
    [hoverPlay],
  );

  return (
    <div ref={boardRef} className="board-area">
      <span className="board-label">Board</span>
      {fragments.map((frag, i) => {
        const color = FRAG_COLORS[i % FRAG_COLORS.length];
        return (
          <div
            key={frag.id}
            className={`board-fragment${selected === frag.id ? ' selected' : ''}`}
            data-frag-id={frag.id}
            style={{ background: color, left: frag.x, top: frag.y }}
            onMouseDown={(e) => onMouseDown(e, frag.id)}
            onMouseEnter={(e) => onEnter(frag, e)}
            onMouseLeave={() => hoverStop(frag.id)}
            title={`${frag.label || frag.id} — ${frag.duration}s`}
          >
            {frag.label || frag.id}
          </div>
        );
      })}
    </div>
  );
}
