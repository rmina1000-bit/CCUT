import React, { useRef, useCallback, useState } from 'react';
import { useLayout } from './context/LayoutContext.jsx';
import { useAppState } from './context/AppStateContext.jsx';
import { useWorkspace } from './context/WorkspaceContext.jsx';

const WorkspaceItem = ({ ws, isActive, onSelect, onDelete, isCollapsed }) => {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div
      onClick={() => onSelect(ws)}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className="workspace-item"
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '12px 12px',
        margin: '2px 8px', borderRadius: 8, cursor: 'pointer',
        color: isActive ? '#fff' : '#d1d5db',
        background: isActive ? '#1e2a3a' : 'transparent',
        borderLeft: isActive ? '3px solid #38bdf8' : '3px solid transparent',
        fontSize: 14, fontWeight: isActive ? 600 : 300,
        transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        position: 'relative',
        overflow: 'hidden'
      }}
    >
      <div style={{ flexShrink: 0, display: 'flex', color: isActive ? '#fff' : '#71717a' }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16c0 1.1.9 2 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
          <path d="M14 3v5h5M10 13l4 2-4 2v-4z" />
        </svg>
      </div>
      {!isCollapsed && (
        <div style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          <div>{ws.name}</div>
          <div style={{ fontSize: 10, color: '#52525b', marginTop: 2 }}>{ws.updatedAt}</div>
        </div>
      )}

      {isHovered && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(ws.id);
          }}
          className="delete-ws-btn"
          style={{
            padding: '8px',
            color: '#ef4444',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.2s',
            border: 'none',
            position: 'absolute',
            right: 4,
            top: '50%',
            transform: 'translateY(-50%)',
            zIndex: 100,
            background: isActive ? '#1e2a3a' : '#1a1b1e',
            borderRadius: '6px',
            boxShadow: '-10px 0 15px 5px ' + (isActive ? '#1e2a3a' : '#1a1b1e')
          }}
          title="프로젝트 삭제"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          </svg>
        </button>
      )}
    </div>
  );
};

export default function LeftPanel({ onFileUpload, isRightPanelOpen, setIsRightPanelOpen }) {
  const fileInputRef = useRef(null);

  const { activeView, setActiveView, uploadDecisionFlow, setUploadDecisionFlow } = useAppState();
  const {
    workspaceList,
    selectedWorkspaceId,
    createWorkspace,
    selectWorkspace,
    deleteWorkspace,
    renameWorkspace
  } = useWorkspace();

  const { collapsed, toggleCollapse } = useLayout();
  const isCollapsed = !!collapsed.left;

  const handleUploadClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;

    const allowed = ['video/mp4', 'video/quicktime', 'video/webm'];
    const validFiles = files.filter(f => allowed.includes(f.type));

    if (validFiles.length === 0) {
      alert('Unsupported file type. Please upload MP4, MOV, or WebM.');
      e.target.value = '';
      return;
    }

    if (workspaceList.length === 0) {
      const newId = createWorkspace(validFiles[0].name);
      selectWorkspace(newId);
      setActiveView('workspace');

      setUploadDecisionFlow({
        files: validFiles,
        step: 0,
        targetWorkspaceId: newId,
        mode: 'new-workspace',
        integration: 'regenerate-proposals'
      });
    } else {
      setUploadDecisionFlow({
        files: validFiles,
        step: 1,
        targetWorkspaceId: selectedWorkspaceId || workspaceList[0].id,
        mode: null,
        integration: null
      });
    }

    e.target.value = '';
  }, [createWorkspace, selectWorkspace, setUploadDecisionFlow, setActiveView, workspaceList, selectedWorkspaceId]);

  const handleNewProject = () => {
    const name = window.prompt("생성할 새 프로젝트 이름을 입력하세요:", `새 프로젝트 ${workspaceList.length + 1}`);
    if (name && name.trim()) {
      createWorkspace(name.trim());
      setActiveView('workspace');
    }
  };

  const handleDeleteWs = (wsId) => {
    if (window.confirm("정말로 이 프로젝트를 삭제하시겠습니까? (이 작업은 되돌릴 수 없습니다)")) {
      deleteWorkspace(wsId);
    }
  };

  const handleSelectWs = (ws) => {
    selectWorkspace(ws.id);
    setActiveView('workspace');
  };

  const ArchiveIcon = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polyline points="21 8 21 21 3 21 3 8" /><rect x="1" y="3" width="22" height="5" /><line x1="10" y1="12" x2="14" y2="12" /></svg>;
  const FolderPlusIcon = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /><line x1="12" y1="11" x2="12" y2="17" /><line x1="9" y1="14" x2="15" y2="14" /></svg>;

  const MenuItem = ({ icon, text, onClick, active, color = '#d1d5db' }) => (
    <div
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: isCollapsed ? '10px 0' : '10px 12px',
        justifyContent: isCollapsed ? 'center' : 'flex-start',
        margin: '2px 8px', borderRadius: 8, cursor: 'pointer',
        color: active ? '#ececf1' : color,
        background: active ? '#202123' : 'transparent',
        fontSize: 14, fontWeight: 300,
        transition: 'all 0.2s',
        overflow: 'hidden'
      }}
      onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = '#202123'; }}
      onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent'; }}
    >
      <div style={{ color: active ? '#fff' : '#d4d4d8', display: 'flex', flexShrink: 0 }}>{icon}</div>
      {!isCollapsed && <div style={{ whiteSpace: 'nowrap' }}>{text}</div>}
    </div>
  );

  return (
    <div style={{
      width: isCollapsed ? 60 : 260, height: '100%', background: '#1a1b1e', display: 'flex', flexDirection: 'column',
      userSelect: 'none', overflow: 'hidden',
      borderRight: '1px solid #1e2a3a',
      transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
    }}>
      {/* Unified Master Layout Toolbar */}
      <div style={{
        height: 60, display: 'flex', alignItems: 'center', padding: isCollapsed ? '0' : '0 16px',
        justifyContent: isCollapsed ? 'center' : 'space-between',
        borderBottom: '1px solid rgba(255,255,255,0.03)',
        gap: 8
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* 1. Sidebar Toggle (Internal) */}
          <button
            onClick={() => toggleCollapse('left')}
            style={{
              background: 'transparent', border: 'none', color: '#71717a',
              cursor: 'pointer', padding: 6, display: 'flex', alignItems: 'center', borderRadius: '6px',
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            title={isCollapsed ? "사이드바 확장" : "사이드바 축소"}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M9 3v18" />
            </svg>
          </button>

          {!isCollapsed && <span style={{ fontSize: 13, fontWeight: 600, color: '#ececf1', letterSpacing: '0.1px' }}>WORKSPACE</span>}
        </div>

        {/* 2. Right Panel Toggle (Master External) */}
        {!isCollapsed && (
          <button
            onClick={() => setIsRightPanelOpen(!isRightPanelOpen)}
            style={{
              background: 'transparent', border: 'none', color: isRightPanelOpen ? '#38bdf8' : '#71717a',
              cursor: 'pointer', padding: 8, display: 'flex', alignItems: 'center', borderRadius: '8px',
              transition: 'all 0.2s',
              boxShadow: isRightPanelOpen ? '0 0 15px rgba(56, 189, 248, 0.2)' : 'none'
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            title="구조맵 토글"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="3" y1="12" x2="21" y2="12"></line>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <line x1="3" y2="18" x2="21" y1="18"></line>
            </svg>
          </button>
        )}
      </div>

      <input type="file" ref={fileInputRef} onChange={handleFileChange} style={{ display: 'none' }} accept="video/mp4,video/quicktime,video/webm" />

      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ padding: '12px 6px' }}>
          <MenuItem icon={<ArchiveIcon />} text="Archive" onClick={() => setActiveView('archive')} active={activeView === 'archive'} color="#71717a" />
        </div>

        <div style={{
          padding: '12px 18px 8px 18px', fontSize: 11, fontWeight: 600, color: '#52525b',
          letterSpacing: '0.05em', display: isCollapsed ? 'none' : 'block'
        }}>
          PROJECTS
        </div>

        <MenuItem icon={<FolderPlusIcon />} text="새 프로젝트" onClick={handleNewProject} color="#a1a1aa" />

        <div style={{ marginTop: 4 }}>
          {workspaceList.map(ws => (
            <WorkspaceItem
              key={ws.id}
              ws={ws}
              isActive={selectedWorkspaceId === ws.id}
              isCollapsed={isCollapsed}
              onSelect={handleSelectWs}
              onDelete={handleDeleteWs}
            />
          ))}
        </div>
      </div>

      <div style={{ padding: '16px 12px', borderTop: '1px solid #27272a', display: 'flex', flexDirection: 'column', gap: 12, flexShrink: 0, overflow: 'hidden' }}>
        <div style={{
          padding: '12px 14px', borderRadius: 8, cursor: 'pointer', color: '#d1d5db', fontSize: 14, fontWeight: 500, transition: 'background 0.2s',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          textAlign: isCollapsed ? 'center' : 'left'
        }}
          onMouseEnter={(e) => e.currentTarget.style.background = '#2b2c2f'}
          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
        >
          {isCollapsed ? 'U' : 'demo_user'}
        </div>
        <div
          onClick={() => setActiveView('settings')}
          style={{
            padding: '12px 14px', borderRadius: 8, cursor: 'pointer',
            color: activeView === 'settings' ? '#ececf1' : '#a1a1aa',
            background: activeView === 'settings' ? '#202123' : 'transparent',
            fontSize: 13, transition: 'background 0.2s',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            textAlign: isCollapsed ? 'center' : 'left'
          }}
          onMouseEnter={(e) => { if (activeView !== 'settings') e.currentTarget.style.background = '#2b2c2f'; }}
          onMouseLeave={(e) => { if (activeView !== 'settings') e.currentTarget.style.background = 'transparent'; }}
        >
          {isCollapsed ? 'S' : 'Settings'}
        </div>
      </div>
    </div>
  );
}
