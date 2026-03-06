import React, { useEffect, useRef } from 'react';
import { useLayout } from '../context/LayoutContext';

export default function ResizablePanel({ id, children }) {
  const { widths, collapsed, setRef, toggleCollapse } = useLayout();
  const elRef = useRef(null);

  useEffect(() => {
    setRef(id, elRef.current);
  }, [id, setRef]);

  const isCollapsed = collapsed[id];
  const collapseIcon = {
    left: isCollapsed ? '›' : '‹',
    center: isCollapsed ? '›' : '‹',
    right: isCollapsed ? '‹' : '›',
  }[id] ?? '‹';

  return (
    <div
      ref={elRef}
      className={`panel panel-${id}${isCollapsed ? ' collapsed' : ''}`}
      style={{
        width: isCollapsed ? 40 : `${widths[id]}%`,
        position: 'relative',
        height: '100%',
        overflow: 'hidden'
      }}
    >
      <button
        className="collapse-btn"
        onClick={() => toggleCollapse(id)}
        title={isCollapsed ? 'Expand panel' : 'Collapse panel'}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          zIndex: 1000,
          background: 'transparent',
          border: 'none',
          color: '#38bdf8',
          fontSize: 16,
          cursor: 'pointer',
          padding: '4px 8px'
        }}
      >
        ☰
      </button>
      <div className="panel-content" style={{ width: '100%', height: '100%' }}>
        {children}
      </div>
    </div>
  );
}
