/**
 * panorama_renderer.js
 * --------------------
 * Horizontal fragment bar.
 * Hover → video.currentTime = fragment.start
 * Click edges → fast panorama scroll.
 * Fixed height, recalculates on window resize.
 */

import React, { useRef, useEffect, useCallback, useState } from 'react';
import { useVideo } from './context/VideoContext';

export default function PanoramaRenderer({ fragments, onHover }) {
  const containerRef = useRef(null);
  const [width, setWidth] = useState(800);
  const [scrollLeft, setScrollLeft] = useState(0);
  const { videoRef } = useVideo();

  // Recalculate on window resize
  useEffect(() => {
    const update = () => {
      if (!containerRef.current) return;
      setWidth(containerRef.current.clientWidth);
    };
    update();
    const r = new ResizeObserver(update);
    r.observe(containerRef.current);
    return () => r.disconnect();
  }, []);

  // Compute fragment widths (proportional to duration)
  const totalDuration = fragments.reduce((sum, f) => sum + (f.end - f.start), 0) || 1;
  const layout = fragments.map((frag) => {
    const dur = frag.end - frag.start;
    const w = Math.max(20, (dur / totalDuration) * width);
    return { ...frag, width: w };
  });

  // Hover fragment: set video currentTime
  const handleFragHover = useCallback((frag) => {
    onHover?.(frag.id);
    if (videoRef.current) {
      videoRef.current.currentTime = frag.start;
    }
  }, [onHover]);

  // Edge scroll: fast pan
  const handleEdgeClick = useCallback((direction) => {
    if (!containerRef.current) return;
    const step = width * 0.4; // 40% of visible width
    const newLeft = direction === 'left' ? Math.max(0, scrollLeft - step) : scrollLeft + step;
    containerRef.current.scrollLeft = newLeft;
    setScrollLeft(newLeft);
  }, [width, scrollLeft]);

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        overflowX: 'auto',
        overflowY: 'hidden',
        background: '#0a1628',
        position: 'relative',
      }}
    >
      {/* Left edge click zone */}
      <div
        onClick={() => handleEdgeClick('left')}
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: 40,
          background: 'linear-gradient(to right, rgba(13,17,23,0.8), transparent)',
          cursor: 'pointer',
          zIndex: 2,
        }}
      />
      {/* Right edge click zone */}
      <div
        onClick={() => handleEdgeClick('right')}
        style={{
          position: 'absolute',
          right: 0,
          top: 0,
          bottom: 0,
          width: 40,
          background: 'linear-gradient(to left, rgba(13,17,23,0.8), transparent)',
          cursor: 'pointer',
          zIndex: 2,
        }}
      />
      {/* Fragment bar */}
      <div style={{
        display: 'flex',
        height: '100%',
        alignItems: 'center',
        padding: '0 40px',
        minWidth: '100%',
      }}>
        {layout.map((frag, i) => (
          <div
            key={frag.id}
            style={{
              width: frag.width,
              height: '60%',
              background: '#1e3a5a',
              border: '1px solid #2d5a8e',
              borderRadius: 3,
              marginRight: i < layout.length - 1 ? 2 : 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 10,
              color: '#c8d0e0',
              cursor: 'pointer',
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = '#2d5a8e';
              handleFragHover(frag);
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = '#1e3a5a';
            }}
          >
            {frag.id}
          </div>
        ))}
      </div>
    </div>
  );
}
