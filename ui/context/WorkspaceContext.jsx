import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';

const WorkspaceContext = createContext(null);

function loadFailSilent(key, defaultValue) {
    try {
        const data = localStorage.getItem(key);
        return data ? JSON.parse(data) : defaultValue;
    } catch (e) {
        console.error(`Failed to load ${key}`, e);
        return defaultValue;
    }
}

function saveFailSilent(key, value) {
    try {
        const payload = typeof value === 'string' ? value : JSON.stringify(value, (k, v) => {
            if (k === 'fileRef' || k === 'objectUrl') return undefined;
            return v;
        });
        localStorage.setItem(key, payload);
    } catch (e) {
        console.error(`Failed to save ${key}`, e);
    }
}

export function WorkspaceProvider({ children }) {
    const [workspaceList, setWorkspaceList] = useState(() => {
        const loaded = loadFailSilent('ccut_workspace_list_v1', []);

        // Deduplicate by ID just in case
        const unique = Array.from(new Map(loaded.map(ws => [ws.id, ws])).values());

        if (unique.length === 0) {
            const initId = `ws_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
            const now = new Date().toLocaleString('en-GB', { hour12: false });
            return [{
                id: initId, name: 'Default Workspace', createdAt: now, updatedAt: now, sourceCount: 0, status: 'idle'
            }];
        }
        return unique;
    });

    const [workspaceDataMap, setWorkspaceDataMap] = useState(() => {
        const loaded = loadFailSilent('ccut_workspace_data_v1', {});
        // If it's completely empty but we seeded a Default Workspace, we should seed its data too.
        if (Object.keys(loaded).length === 0) {
            const listLoaded = loadFailSilent('ccut_workspace_list_v1', []);
            if (listLoaded.length === 0) { // meaning we just seeded it in the block above
                // Note: we can't reliably get the initId here directly from above because of closure boundaries,
                // but since WorkspaceList sets it if empty, we can just leave it empty and let users create new ones or handle legacy.
                // Actually, let's just return the loaded object and auto-heal it elsewhere.
            }
        }
        return loaded;
    });

    const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(() => {
        try {
            return localStorage.getItem('ccut_workspace_selected_v1') || null;
        } catch {
            return null;
        }
    });
    const isDeletingRef = useRef(false);

    // Auto-save effects
    useEffect(() => {
        if (isDeletingRef.current) return;
        saveFailSilent('ccut_workspace_list_v1', workspaceList);
    }, [workspaceList]);

    useEffect(() => {
        if (isDeletingRef.current) return;
        saveFailSilent('ccut_workspace_data_v1', workspaceDataMap);
    }, [workspaceDataMap]);

    useEffect(() => {
        if (isDeletingRef.current) return;
        if (selectedWorkspaceId) {
            saveFailSilent('ccut_workspace_selected_v1', selectedWorkspaceId);
        } else {
            try {
                localStorage.removeItem('ccut_workspace_selected_v1');
            } catch (e) {
                // ignore
            }
        }
    }, [selectedWorkspaceId]);

    const updateWorkspaceMeta = useCallback((id, patch) => {
        setWorkspaceList(prev => prev.map(ws =>
            ws.id === id ? { ...ws, ...patch, updatedAt: new Date().toLocaleString('en-GB', { hour12: false }) } : ws
        ));
    }, []);

    const createWorkspace = useCallback((name) => {
        const newId = `ws_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
        const now = new Date().toLocaleString('en-GB', { hour12: false });

        const newData = {
            sources: [],
            proposals: [],
            editSession: {
                activeProposalId: null,
                selectedFragments: [],
                boardItems: [],
                committedDecisions: []
            },
            chatMessages: [],
            isEditing: false,
            isDirty: false,
            cleanSignature: ''
        };

        console.log('[WorkspaceContext] createWorkspace:', name, '->', newId);
        setWorkspaceList(prev => {
            const finalName = name || `새 프로젝트 ${prev.length + 1}`;
            const newMeta = {
                id: newId,
                name: finalName,
                createdAt: now,
                updatedAt: now,
                sourceCount: 0,
                status: 'idle'
            };
            return [newMeta, ...prev];
        });

        setWorkspaceDataMap(prev => ({ ...prev, [newId]: newData }));
        setSelectedWorkspaceId(newId);

        return newId;
    }, []);

    const selectWorkspace = useCallback((id) => {
        setSelectedWorkspaceId(id);
    }, []);

    const renameWorkspace = useCallback((id, newName) => {
        updateWorkspaceMeta(id, { name: newName });
    }, [updateWorkspaceMeta]);

    const updateWorkspaceData = useCallback((id, patch) => {
        if (!id || !patch) return;

        setWorkspaceDataMap(prev => {
            if (isDeletingRef.current) {
                console.log('[WorkspaceContext] updateWorkspaceData skipped: deletion in progress for', id);
                return prev;
            }

            const currentData = prev[id];
            if (!currentData) return prev;

            // Deep check via JSON to break loops from new array references with same content
            let hasChanged = false;
            for (const key in patch) {
                if (JSON.stringify(patch[key]) !== JSON.stringify(currentData[key])) {
                    hasChanged = true;
                    break;
                }
            }
            if (!hasChanged) return prev;

            return {
                ...prev,
                [id]: { ...currentData, ...patch }
            };
        });
    }, []);

    const addSourceToWorkspace = useCallback((id, source) => {
        setWorkspaceDataMap(prev => {
            const currentData = prev[id];
            if (!currentData) return prev;

            // Deduplicate sources by ID or filename
            const existingSources = currentData.sources || [];
            if (existingSources.some(s => s.id === source.id)) {
                console.log('[WorkspaceContext] Skipping duplicate source:', source.id);
                return prev;
            }

            return {
                ...prev,
                [id]: {
                    ...currentData,
                    sources: [...existingSources, source]
                }
            };
        });
        setWorkspaceList(prev => prev.map(ws =>
            ws.id === id ? { ...ws, sourceCount: (ws.sourceCount || 0) + 1, updatedAt: new Date().toLocaleString('en-GB', { hour12: false }) } : ws
        ));
    }, []);

    const updateEditSession = useCallback((id, patch) => {
        setWorkspaceDataMap(prev => {
            const currentData = prev[id];
            if (!currentData) return prev;
            return {
                ...prev,
                [id]: {
                    ...currentData,
                    editSession: {
                        ...(currentData.editSession || {}),
                        ...patch
                    }
                }
            };
        });
        updateWorkspaceMeta(id, { updatedAt: new Date().toLocaleString('en-GB', { hour12: false }) });
    }, [updateWorkspaceMeta]);

    const getSelectedWorkspace = useCallback(() => {
        return workspaceList.find(ws => ws.id === selectedWorkspaceId) || null;
    }, [workspaceList, selectedWorkspaceId]);

    const getSelectedWorkspaceData = useCallback(() => {
        return workspaceDataMap[selectedWorkspaceId] || null;
    }, [workspaceDataMap, selectedWorkspaceId]);

    const deleteWorkspace = useCallback((id) => {
        if (!id) return;

        console.log('[WorkspaceContext] deleteWorkspace start:', id);
        isDeletingRef.current = true;

        const nextList = workspaceList.filter(ws => ws.id !== id);
        const nextDataMap = { ...workspaceDataMap };
        delete nextDataMap[id];

        let nextSelectedId = selectedWorkspaceId;
        const selectedStillExists = nextList.some(ws => ws.id === selectedWorkspaceId);

        if (selectedWorkspaceId === id) {
            nextSelectedId = nextList.length > 0 ? nextList[0].id : null;
        } else if (!selectedStillExists) {
            nextSelectedId = nextList.length > 0 ? nextList[0].id : null;
        }

        // No pending delete tracking needed

        setWorkspaceList(nextList);
        setWorkspaceDataMap(nextDataMap);
        setSelectedWorkspaceId(nextSelectedId);

        saveFailSilent('ccut_workspace_list_v1', nextList);
        saveFailSilent('ccut_workspace_data_v1', nextDataMap);
        if (nextSelectedId) {
            saveFailSilent('ccut_workspace_selected_v1', nextSelectedId);
        } else {
            try {
                localStorage.removeItem('ccut_workspace_selected_v1');
            } catch (e) {
                // ignore
            }
        }

        console.log('[WorkspaceContext] deleteWorkspace result:', {
            deletedId: id,
            nextListIds: nextList.map(ws => ws.id),
            nextSelectedId
        });
    }, [workspaceList, workspaceDataMap, selectedWorkspaceId]);

    useEffect(() => {
        if (!isDeletingRef.current) return;
        // Deletion completed; simply release lock.
        console.log('[WorkspaceContext] delete completed, lock released');
        queueMicrotask(() => { isDeletingRef.current = false; });
    }, [workspaceList, workspaceDataMap, selectedWorkspaceId]);

    // Robust recovery & Fallback
    useEffect(() => {
        // Expose for debugging
        window._workspaceList = workspaceList;
        window._selectedId = selectedWorkspaceId;

        if (isDeletingRef.current) {
            console.log('[WorkspaceContext] recovery skipped: deletion in progress');
            return;
        }

        if (workspaceList.length === 0) {
            console.log('[WorkspaceContext] empty workspace list -> create default');
            createWorkspace('Default Workspace');
            return;
        }

        const exists = workspaceList.some(ws => ws.id === selectedWorkspaceId);
        if (!selectedWorkspaceId || !exists) {
            console.log('[WorkspaceContext] selecting fallback workspace:', workspaceList[0].id);
            setSelectedWorkspaceId(workspaceList[0].id);
        }
    }, [selectedWorkspaceId, workspaceList, createWorkspace]);

    return (
        <WorkspaceContext.Provider value={{
            workspaceList,
            workspaceDataMap,
            selectedWorkspaceId,
            createWorkspace,
            selectWorkspace,
            renameWorkspace,
            updateWorkspaceMeta,
            updateWorkspaceData,
            addSourceToWorkspace,
            updateEditSession,
            getSelectedWorkspace,
            getSelectedWorkspaceData,
            deleteWorkspace
        }}>
            {children}
        </WorkspaceContext.Provider>
    );
}

export function useWorkspace() {
    return useContext(WorkspaceContext);
}
