import React, { useCallback, useEffect } from 'react';
import { AppStateProvider } from './context/AppStateContext.jsx';
import { WorkspaceProvider, useWorkspace } from './context/WorkspaceContext.jsx';
import { LayoutProvider } from './context/LayoutContext.jsx';
import { VideoProvider } from './context/VideoContext.jsx';
import MainLayout from './layout/MainLayout.jsx';
import UploadDecisionModal from './UploadDecisionModal.jsx';
import { logEvent } from './utils/logEvent.js';

function AppContent() {
  const {
    selectedWorkspaceId,
    getSelectedWorkspaceData,
    updateWorkspaceData
  } = useWorkspace();

  const workspaceData = getSelectedWorkspaceData() || {};
  const fragments = workspaceData?.fragments || [];

  const handleWorkspaceDataChange = useCallback((patch) => {
    if (selectedWorkspaceId) {
      updateWorkspaceData(selectedWorkspaceId, patch);
    }
  }, [selectedWorkspaceId, updateWorkspaceData]);

  const onFragmentsLoad = useCallback((newFrags) => {
    handleWorkspaceDataChange({ fragments: newFrags });
  }, [handleWorkspaceDataChange]);

  const handleSetFragments = useCallback((newFrags) => {
    const resolvedFrags = typeof newFrags === 'function' ? newFrags(fragments) : newFrags;
    handleWorkspaceDataChange({ fragments: resolvedFrags });
  }, [fragments, handleWorkspaceDataChange]);

  const onAction = useCallback(async (action) => {
    if (typeof action === 'string') {
      logEvent('CHAT_MESSAGE_SENT', { text: action });
      return;
    }
    if (action && action.type) {
      logEvent(action.type, action.payload);
    }
  }, []);

  if (!selectedWorkspaceId) return null; // Wait for context seeding

  return (
    <LayoutProvider>
      <VideoProvider>
        <MainLayout
          key={selectedWorkspaceId}
          workspaceData={workspaceData}
          onWorkspaceDataChange={handleWorkspaceDataChange}
          fragments={fragments}
          onFragments={handleSetFragments}
          onAction={onAction}
          onFragmentsLoad={onFragmentsLoad}
        />
        <UploadDecisionModal />
      </VideoProvider>
    </LayoutProvider>
  );
}

export default function App() {
  return (
    <AppStateProvider>
      <WorkspaceProvider>
        <AppContent />
      </WorkspaceProvider>
    </AppStateProvider>
  );
}
