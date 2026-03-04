import React, { useEffect, useRef } from 'react';
import { useLayout } from '../context/LayoutContext.js';

export default function ResizablePanel({ id, children }) {
  const { widths, collapsed, setRef, toggleCollapse } = useLayout();
  const elRef = useRef(null);

  useEffect(() => {
    setRef(id, elRef.current);
  }, [id, setRef]);

  const isCollapsed = collapsed[id];
  const collapseIcon = {
    left:   isCollapsed ? '›' : '‹',
    center: isCollapsed ? '›' : '‹',
    right:  isCollapsed ? '‹' : '›',
  }[id] ?? '‹';

  return (
    <div
      ref={elRef}
      className={`panel panel-${id}${isCollapsed ? ' collapsed' : ''}`}
      style={{ width: isCollapsed ? 40 : `${widths[id]}%` }}
    >
      <button
        className="collapse-btn"
        onClick={() => toggleCollapse(id)}
        title={isCollapsed ? 'Expand panel' : 'Collapse panel'}
      >
        {collapseIcon}
      </button>
      <div className="panel-content">
        {children}
      </div>
    </div>
  );
}
