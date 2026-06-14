/**
 * CCUT Video Intelligence Service
 */

import { fetcher, API_BASE_URL } from "./api";

export const videoService = {
    API_BASE_URL,
    uploadVideo: async (file: File): Promise<{
        status: string;
        file_name: string;
        source_id: string;
        static_url: string;
    }> => {
        const formData = new FormData();
        formData.append("file", file);

        try {
            console.log(`[videoService] Uploading to: ${API_BASE_URL}/upload`);
            const response = await fetch(`${API_BASE_URL}/upload`, {
                method: "POST",
                body: formData,
            });
            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`업로드 실패 (${response.status}): ${errText || "서버 연결을 확인하세요."}`);
            }
            return await response.json();
        } catch (error) {
            console.error("[videoService] uploadVideo Error:", error);
            if (error instanceof TypeError && error.message === "Failed to fetch") {
                throw new Error("백엔드 서버에 연결할 수 없습니다. 127.0.0.1:8000 실행 상태를 확인하세요.");
            }
            throw error;
        }
    },

    generateFragments: async (sourceId: string) => {
        const response = await fetch(
            `${API_BASE_URL}/generate-fragments?source_id=${encodeURIComponent(sourceId)}`,
            { method: "POST" }
        );
        if (!response.ok) throw new Error(`조각 분석 실패: ${response.status}`);
        return await response.json();
    },

    getThumb: (fragId: string) => null,
    getThumbnailUrl: (fragId: string) => null,

    // [FRAGMENT-SEARCH] 채팅 자연어 -> 조각 검색.
    // is_search=false면 검색 의도가 아님(호출측이 기존 채팅 흐름으로 위임).
    chatFragmentSearch: async (
        message: string,
        opts?: { top_k?: number; only_curated?: boolean; program_id?: string }
    ): Promise<{
        status: string;
        is_search: boolean;
        query: string;
        confidence?: number;
        count: number;
        results: Array<{
            fragment_id: string;
            source_id: string;
            start: number;
            end: number;
            duration: number;
            role: string | null;
            visual_desc: string | null;
            transcript: string | null;
            is_curated: boolean;
            keyframe: string | null;
            score: number;
            semantic: number;
            keyword_hit: boolean;
        }>;
    }> => {
        const response = await fetch(`${API_BASE_URL}/chat/fragment-search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message,
                top_k: opts?.top_k ?? 12,
                only_curated: opts?.only_curated ?? false,
                program_id: opts?.program_id ?? null,
            }),
        });
        if (!response.ok) throw new Error(`조각 검색 실패: ${response.status}`);
        return await response.json();
    },

    getFragmentsFromDB: async (sourceId: string) => {
        return await fetcher(`/fragments/${encodeURIComponent(sourceId)}`);
    },

    getFragmentStatus: async (sourceId: string) => {
        return await fetcher(`/generate-fragments/status/${encodeURIComponent(sourceId)}`);
    },

    getFragmentsBySource: async (sourceId: string) => {
        return await fetcher(`/fragments/${encodeURIComponent(sourceId)}`);
    },

    logDecisionToDB: async (fragId: string, action: string, reason: string = "") => {
        return await fetcher("/decisions", {
            method: "POST",
            body: JSON.stringify({ target_id: fragId, action, user_reason: reason })
        });
    },

    requestProjectProposals: async (
        projectId: string, 
        sourceIds: string[], 
        targetLength: number = 60.0,
        userIntent?: any,
        refresh?: boolean
    ) => {
        const response = await fetch(`${API_BASE_URL}/proposals/project`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                project_id: projectId,
                source_ids: sourceIds,
                target_length: targetLength,
                user_intent: userIntent,
                refresh: refresh
            })
        });
        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`프로젝트 제안 생성 실패 (${response.status}): ${errText}`);
        }
        return await response.json();
    },

    getProjectSources: async (projectId: string) => {
        return await fetcher(`/proposals/project/${encodeURIComponent(projectId)}/sources`);
    },
    upsertEditOverlay: async (payload: {
        source_id: string;
        fragment_id: string;
        effective_start_sec: number;
        effective_end_sec: number;
        excluded?: boolean;
        edit_type?: string;
        root_fragment_id?: string | null;
        parent_fragment_id?: string | null;
        overlay_id?: string | null;
    }) => {
        const response = await fetch(`${API_BASE_URL}/edit-overlay`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        return await response.json();
    },
    getEditOverlay: async (sourceId: string) => {
        return await fetcher(`/edit-overlay/${encodeURIComponent(sourceId)}`);
    },

    // [B-5a] 프로젝트 생애주기 API (1급 독립체)
    createProject: async (name?: string) => {
        return await fetcher(`/projects`, {
            method: "POST",
            body: JSON.stringify({ name: name ?? null }),
        });
    },
    listProjects: async () => {
        return await fetcher(`/projects`);
    },
    saveProjectState: async (programId: string, state: {
        active_mode?: string | null;
        chat_state?: string | null;
        reserve_state?: string | null;
        ui_state?: string | null;
    }) => {
        return await fetcher(`/projects/${encodeURIComponent(programId)}/state`, {
            method: "POST",
            body: JSON.stringify(state),
        });
    },
    getProjectState: async (programId: string) => {
        return await fetcher(`/projects/${encodeURIComponent(programId)}/state`);
    },
    deleteProject: async (programId: string) => {
        return await fetcher(`/projects/${encodeURIComponent(programId)}`, { method: "DELETE" });
    },

    // [SOFT-DELETE] 휴지통 프로젝트 복원 (30일 내)
    restoreProject: async (programId: string) => {
        return await fetcher(`/projects/${encodeURIComponent(programId)}/restore`, { method: "POST" });
    },

    // [PROPOSAL-PREVIEW] 제안 즉석 렌더(또는 캐시) -> 재생용 mp4 URL
    makeProposalPreview: async (proposalId: string): Promise<{
        status: string;
        preview_url: string | null;
        duration: number;
    }> => {
        return await fetcher(`/proposals/${encodeURIComponent(proposalId)}/preview`, { method: "POST" });
    },

    // [SOURCE] 원본 영상 이름 변경
    renameSource: async (sourceId: string, name: string) => {
        return await fetcher(`/sources/${encodeURIComponent(sourceId)}/name`, {
            method: "PATCH",
            body: JSON.stringify({ name }),
        });
    },

    // [SOURCE] 원본 삭제. mode='source_only'(파일만) | 'full'(조각까지 전부)
    deleteSource: async (sourceId: string, mode: "source_only" | "full" = "source_only") => {
        return await fetcher(`/sources/${encodeURIComponent(sourceId)}?mode=${mode}`, {
            method: "DELETE",
        });
    },
};