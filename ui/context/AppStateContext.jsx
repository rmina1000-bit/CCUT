import React, { createContext, useContext, useState, useEffect } from 'react';

const AppStateContext = createContext(null);

export function AppStateProvider({ children }) {
    const [activeView, setActiveView] = useState(() => {
        try {
            return localStorage.getItem('ccut_app_ui_state_v1') || 'workspace';
        } catch {
            return 'workspace';
        }
    });

    const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false);

    // Multi-source Upload Decision Flow
    const [uploadDecisionFlow, setUploadDecisionFlow] = useState({
        files: [], // Batch of files
        step: 0, // 0: inactive, 1: where to put, 2: how to integrate
        targetWorkspaceId: null,
        mode: null, // 'append' | 'new-workspace'
        integration: null // 'source-only' | 'regenerate-proposals'
    });
    const [isRightPanelOpen, setIsRightPanelOpen] = useState(false);

    useEffect(() => {
        try {
            localStorage.setItem('ccut_app_ui_state_v1', activeView);
        } catch (e) {
            console.error('Failed to save UI state', e);
        }
    }, [activeView]);

    return (
        <AppStateContext.Provider value={{
            activeView, setActiveView,
            isLeftPanelCollapsed, setIsLeftPanelCollapsed,
            isRightPanelOpen, setIsRightPanelOpen,
            uploadDecisionFlow, setUploadDecisionFlow
        }}>
            {children}
        </AppStateContext.Provider>
    );
}

export function useAppState() {
    return useContext(AppStateContext);
}
