/**
 * left_panel.jsx
 * --------------
 * CCUT Left Panel: upload, workspace list, fixed layout.
 * 18% width, fixed top/bottom sections.
 */

import React, { useState, useRef, useCallback } from 'react';
import { useVideo } from './context/VideoContext';
import mockFragments from './mock/mock_fragments.json';

const FAKE_WORKSPACES = [
  { id: 'ws1', name: 'Video 1', createdAt: '2026-03-05 18:30' },
  { id: 'ws2', name: 'Video 2', createdAt: '2026-03-05 17:12' },
  { id: 'ws3', name: 'Video 3', createdAt: '2026-03-05 15:45' },
];

export default function LeftPanel({ isEditing, onWorkspaceCreate, onWorkspaceSelect, onFragmentsLoad }) {
  const fileInputRef = useRef(null);
  const [selectedWs, setSelectedWs] = useState(null);
  const { setVideoURL, videoURL } = useVideo();

  const handleUploadClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback((e) => {
    const file = e.target.files[0];
    if (!file) return;
    // Reject unsupported files
    const allowed = ['video/mp4', 'video/quicktime', 'video/webm'];
    if (!allowed.includes(file.type)) {
      alert('Unsupported file type. Please upload MP4, MOV, or WebM.');
      e.target.value = '';
      return;
    }
    // Create object URL
    const url = URL.createObjectURL(file);
    setVideoURL(url);
    // Create workspace
    const newWs = {
      id: `ws_${Date.now()}`,
      name: file.name,
      createdAt: new Date().toLocaleString('en-GB'),
    };
    onWorkspaceCreate?.(newWs);
    setSelectedWs(newWs);
    onWorkspaceSelect?.(newWs);
    // Load mock fragments
    onFragmentsLoad?.(mockFragments);
    e.target.value = '';
  }, [setVideoURL, onWorkspaceCreate, onWorkspaceSelect, onFragmentsLoad]);

  const handleSelect = useCallback((ws) => {
    setSelectedWs(ws);
    onWorkspaceSelect?.(ws);
  }, [onWorkspaceSelect]);

  const handleDeleteWorkspace = useCallback(() => {
    if (!selectedWs) return;
    // Revoke object URL to prevent memory leak
    if (videoURL) {
      URL.revokeObjectURL(videoURL);
      setVideoURL(null);
    }
    setSelectedWs(null);
    // TODO: notify parent to clear fragments
  }, [selectedWs, videoURL, setVideoURL]);

  return (
    <div style={{
      width: '100%',
      height: '100vh',
      background: '#07090f',
      borderRight: '1px solid #1e2a3a',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: "'Courier New', monospace",
      color: '#c8d0e0',
    }}>
      {/* TOP (fixed) */}
      <div style={{
        padding: '14px 12px',
        background: '#0d1117',
        borderBottom: '1px solid #1e2a3a',
        flexShrink: 0,
      }}>
        <div style={{
          fontSize: 13,
          fontWeight: 'bold',
          color: '#38bdf8',
          letterSpacing: 1,
          marginBottom: 6,
        }}>
          C-CUT 1.0.0
        </div>
        <div style={{ fontSize: 10, color: '#4b5563' }}>
          Archive
        </div>
        <div style={{ fontSize: 10, color: '#4b5563' }}>
          SNS
        </div>
        <div style={{ fontSize: 10, color: '#4b5563' }}>
          Reports
        </div>
      </div>

      {/* CENTER */}
      <div style={{
        flex: 1,
        padding: '12px',
        overflowY: 'auto',
      }}>
        {isEditing && (
          <>
            {/* Workspace List */}
            <div style={{ fontSize: 9, color: '#374151', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>
              Workspaces
            </div>
            {FAKE_WORKSPACES.map((ws) => (
              <div
                key={ws.id}
                onClick={() => handleSelect(ws)}
                style={{
                  padding: '6px 8px',
                  marginBottom: 4,
                  background: selectedWs?.id === ws.id ? '#111820' : 'transparent',
                  border: selectedWs?.id === ws.id ? '1px solid #1e3a5a' : '1px solid transparent',
                  borderRadius: 3,
                  cursor: 'pointer',
                  fontSize: 11,
                }}
              >
                <div style={{ fontWeight: 'bold' }}>{ws.name}</div>
                <div style={{ fontSize: 9, color: '#6b7280' }}>{ws.createdAt}</div>
              </div>
            ))}
          </>
        )}
      </div>

      {/* BOTTOM (fixed) */}
      <div style={{
        padding: '10px 12px',
        background: '#0d1117',
        borderTop: '1px solid #1e2a3a',
        flexShrink: 0,
      }}>
        <div style={{ fontSize: 10, color: '#4b5563' }}>User ID: demo_user</div>
        <div style={{ fontSize: 10, color: '#4b5563', marginTop: 2 }}>Settings</div>
      </div>
    </div>
  );
}
