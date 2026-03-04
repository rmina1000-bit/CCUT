import React, { useRef, useCallback } from 'react';
import { useLayout } from '../context/LayoutContext.js';

const MIN_PX = 40;

export default function ResizeHandle({ between }) {
  const { domRefs, updateWidths } = useLayout();
  const activeRef = useRef(false);
  const handleRef = useRef(null);

  const onMouseDown = useCallback(
    (e) => {
      e.preventDefault();

      const container = domRefs.container;
      const leftEl    = domRefs.left;
      const centerEl  = domRefs.center;
      const rightEl   = domRefs.right;
      if (!container || !leftEl || !centerEl || !rightEl) return;

      activeRef.current = true;
      if (handleRef.current) handleRef.current.classList.add('active');

      const totalW     = container.offsetWidth;
      const startX     = e.clientX;
      const startLeft  = leftEl.offsetWidth;
      const startCtr   = centerEl.offsetWidth;
      const startRight = rightEl.offsetWidth;

      const onMove = (me) => {
        if (!activeRef.current) return;
        const dx = me.clientX - startX;

        if (between === 'lc') {
          const newLeft = Math.max(MIN_PX, startLeft + dx);
          const newCtr  = Math.max(MIN_PX, startCtr  - dx);
          leftEl.style.width   = newLeft + 'px';
          centerEl.style.width = newCtr  + 'px';
        } else {
          const newCtr   = Math.max(MIN_PX, startCtr   + dx);
          const newRight = Math.max(MIN_PX, startRight  - dx);
          centerEl.style.width = newCtr   + 'px';
          rightEl.style.width  = newRight + 'px';
        }
      };

      const onUp = () => {
        activeRef.current = false;
        if (handleRef.current) handleRef.current.classList.remove('active');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup',   onUp);

        updateWidths({
          left:   (leftEl.offsetWidth   / totalW) * 100,
          center: (centerEl.offsetWidth / totalW) * 100,
          right:  (rightEl.offsetWidth  / totalW) * 100,
        });
      };

      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup',   onUp);
    },
    [between, domRefs, updateWidths],
  );

  return (
    <div
      ref={handleRef}
      className="resize-handle"
      onMouseDown={onMouseDown}
    />
  );
}
