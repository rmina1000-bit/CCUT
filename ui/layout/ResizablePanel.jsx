import React, { useEffect, useRef } from 'react';
import { useLayout } from '../context/LayoutContext';

export default function ResizablePanel({ id, headerLeft = null, children }) {
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
        flexGrow: isCollapsed ? 0 : widths[id],
        flexShrink: isCollapsed ? 0 : 1,
        position: 'relative',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        overflow: id === 'right' ? 'visible' : 'hidden'
      }}
    >
      <div className="panel-content" style={{ flex: 1, width: '100%', overflow: id === 'right' ? 'visible' : 'hidden', display: 'flex', flexDirection: 'column' }}>
        {children}
      </div>
    </div>
  );
}
