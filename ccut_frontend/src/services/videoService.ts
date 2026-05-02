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

    requestProjectProposals: async (projectId: string, sourceIds: string[], targetLength: number = 60.0) => {
        const response = await fetch(`${API_BASE_URL}/proposals/project`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                project_id: projectId,
                source_ids: sourceIds,
                target_length: targetLength
            })
        });
        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`프로젝트 제안 생성 실패 (${response.status}): ${errText}`);
        }
        return await response.json();
    }
};