import React, { useEffect, useRef } from 'react';
import { useLayout } from '../context/LayoutContext.js';
import ResizablePanel from './ResizablePanel.jsx';
import ResizeHandle from './ResizeHandle.jsx';
import RightPanel from '../right/RightPanel.jsx';
import VideoUploader from '../components/VideoUploader.jsx';

function LeftPanelContent({ onFragments }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <VideoUploader onFragments={onFragments} />
      <div className="panel-placeholder" style={{ flex: 1, overflowY: 'auto' }}>
        <h4>Asset Browser</h4>
        <p>Upload a video to generate fragments.</p>
      </div>
    </div>
  );
}

function CenterPanelContent() {
  return (
    <div className="panel-placeholder">
      <h4>Timeline</h4>
      <p>Cut timeline will appear here.</p>
    </div>
  );
}

export default function MainLayout({ fragments = [], onFragments }) {
  const { setRef } = useLayout();
  const containerRef = useRef(null);

  useEffect(() => {
    setRef('container', containerRef.current);
  }, [setRef]);

  return (
    <div ref={containerRef} className="main-layout" id="main-layout">
      <ResizablePanel id="left">
        <LeftPanelContent onFragments={onFragments} />
      </ResizablePanel>

      <ResizeHandle between="lc" />

      <ResizablePanel id="center">
        <CenterPanelContent />
      </ResizablePanel>

      <ResizeHandle between="cr" />

      <ResizablePanel id="right">
        <RightPanel fragments={fragments} onFragmentsChange={onFragments} />
      </ResizablePanel>
    </div>
  );
}
