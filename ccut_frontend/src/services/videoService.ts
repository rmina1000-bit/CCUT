/**
 * CCUT Video Intelligence Service
 */

import { fetcher, API_BASE_URL } from "./api";
import {
    beginSpeedTrace,
    finishSpeedTrace,
    markFetchIssued,
    markFirstByte,
    markFirstDom,
} from "@/utils/speedTrace";

// [FIX-RUNTIME-1b] /system/diagnostics 응답(라이브 JSON 기준)
export interface SystemDiagnostics {
    status: "ok" | "warning" | "fail";
    current_asr_provider: string;
    whisper_vulkan_health: { ok?: boolean | null; loaded?: boolean | null; error?: string | null; model_id?: string | null };
    cli_path_exists: boolean;
    model_path_exists: boolean;
    fallback_model_path_exists: boolean;
    ffmpeg_available: boolean;
    runtime_dir_exists: boolean;
    storage_free_gb: number | null;
    cpu_fallback_available: boolean;
    cli_path?: string;
    model_path?: string;
    fallback_model_path?: string;
}

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

    // [FIX-RUNTIME-1b] GPU ASR 런타임 환경진단 (read 전용). 백엔드 /system/diagnostics 소비.
    getSystemDiagnostics: async (): Promise<SystemDiagnostics> => {
        return await fetcher(`/system/diagnostics`);
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

    // [서사층 §2.1] 말의 원장 — 사용자의 말을 대상(source/person/program)에 영구 귀속
    addNarrativeNotes: async (notes: Array<{ target_kind: string; target_id: string; text: string; origin?: string }>) => {
        return await fetcher(`/narrative/notes`, {
            method: "POST",
            body: JSON.stringify({ notes })
        });
    },

    // [TIMELINE] append-only 영속 타임라인 — 사건 즉시 기록(멱등), 커서 페이지네이션
    appendTimeline: async (programId: string, entries: any[]) => {
        return await fetcher(`/projects/${encodeURIComponent(programId)}/timeline`, {
            method: "POST",
            body: JSON.stringify({ entries })
        });
    },
    getTimeline: async (programId: string, limit: number = 300, before?: number) => {
        const q = `limit=${limit}` + (before ? `&before=${before}` : "");
        return await fetcher(`/projects/${encodeURIComponent(programId)}/timeline?${q}`);
    },

    // [ARCHIVE B] 아카이브 포함 승인 시 소스를 프로젝트에 연결 (기존 UI-② 엔드포인트 재사용, 멱등)
    addSourcesToProject: async (programId: string, sourceIds: string[]) => {
        return await fetcher(`/projects/${encodeURIComponent(programId)}/sources`, {
            method: "POST",
            body: JSON.stringify({ source_ids: sourceIds })
        });
    },

    // [INTENT-ROUTER] 백엔드 종업원 — 프론트는 말을 거의 그대로 보내고 해석은 서버가.
    routeEditIntent: async (payload: {
        project_id?: string;
        source_ids: string[];
        input_text: string;
        recent_messages?: any[];
        selected_proposal_id?: string | null;
        // [조각 라벨 지정 편집] 조각맵 타일 라벨("K1") → 조각ID 매핑
        fragment_labels?: Record<string, string>;
    }) => {
        const response = await fetch(`${API_BASE_URL}/intent/route-edit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error(await response.text());
        return await response.json();
    },

    // [F2 스트리밍] 종업원 응답 SSE 수신 — token 이벤트마다 onToken(누적문) 콜백,
    // final 이벤트의 result(기존 계약과 동일 형태)를 반환. 실패는 throw — 호출부가
    // 일괄(routeEditIntent) 폴백한다 (무언 실패 금지).
    routeEditIntentStream: async (
        payload: any,
        onToken?: (accum: string) => void,
    ) => {
        const trace = beginSpeedTrace();
        const body = JSON.stringify(payload);
        const traceHeaders = markFetchIssued(trace);
        const response = await fetch(`${API_BASE_URL}/intent/route-edit/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...traceHeaders },
            body
        });
        if (!response.ok || !response.body) throw new Error(`stream ${response.status}`);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        let accum = "";
        let final: any = null;
        for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            markFirstByte(trace);
            buf += decoder.decode(value, { stream: true });
            let idx;
            while ((idx = buf.indexOf("\n\n")) >= 0) {
                const raw = buf.slice(0, idx).trim();
                buf = buf.slice(idx + 2);
                if (!raw.startsWith("data:")) continue;
                try {
                    const ev = JSON.parse(raw.slice(5));
                    if (ev.type === "token" && typeof ev.text === "string") {
                        accum += ev.text;
                        onToken?.(accum);
                        markFirstDom(trace);
                    } else if (ev.type === "final") {
                        final = ev.result;
                    }
                } catch { /* 조각난 이벤트는 다음 청크에서 완성 */ }
            }
        }
        if (!final) throw new Error("stream ended without final");
        finishSpeedTrace(trace, API_BASE_URL, {
            endpoint: "/intent/route-edit/stream",
            method: "POST",
            body_bytes: new TextEncoder().encode(body).length,
            recent_msgs: Array.isArray(payload?.recent_messages) ? payload.recent_messages.length : 0,
            recent_chars: Array.isArray(payload?.recent_messages)
                ? payload.recent_messages.reduce((n: number, m: any) => n + String(m?.text || "").length, 0)
                : 0,
            source_ids: Array.isArray(payload?.source_ids) ? payload.source_ids.length : 0,
            fragment_labels: payload?.fragment_labels ? Object.keys(payload.fragment_labels).length : 0,
            stream: true,
        }, {
            action: final?.action,
            via: final?.via,
            matched: final?.matched,
            reply_len: String(final?.reply || "").length,
        });
        return final;
    },

    // [#57 REVISION 도구층] 기존 안 국소 수정 — 새 REV_* 제안으로 저장(부모 불변), 새 시퀀스 반환
    reviseProposal: async (payload: {
        proposal_id: string;
        instruction: string;
        source_ids?: string[];
        revision?: any;
    }) => {
        const response = await fetch(`${API_BASE_URL}/revision/proposals`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error(await response.text());
        return await response.json();
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

    /** [SAVE-SPINE 2-C] 이 원고를 버전으로 저장한다.
     *  서버는 전부 저장하거나 아무것도 안 남긴다 — 반쪽은 없다.
     *  좌표·trim·숨김은 서버가 원장에서 채우므로 여기서 보내지 않는다. */
    saveStoryVersion: async (projectId: string, payload: {
        name: string;
        fids: string[];
        selected_span_ids?: string[];
        rough_cut_input_hash?: string | null;
        parent_version_id?: number | null;
        display_ids?: Record<string, string>;
        note?: string;
    }) => {
        const response = await fetch(`${API_BASE_URL}/story-version/${encodeURIComponent(projectId)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const body = await response.json().catch(() => ({}));
        return { ok: response.ok, status: response.status, body };
    },

    listStoryVersions: async (projectId: string) => {
        return await fetcher(`/story-version/${encodeURIComponent(projectId)}`);
    },

    /** [SAVE-TRUTH 2026-08-06] 편집본을 통째로 저장한다 — 원천은 ★화면이다.
     *  구판은 items 없이 보냈고 서버가 승인 원장을 복사해, 화면이 16이든 14든
     *  언제나 승인 원고 15행이 저장됐다(edit_version id=2·3 실측). 이제 화면이 좌표를 싣는다. */
    saveEditVersion: async (projectId: string, payload: {
        name?: string;
        fids?: string[];
        items?: Array<{
            fid: string;
            source_id: string;
            anchor_start_ms: number;
            anchor_end_ms: number;
            trim_start_ms?: number | null;
            trim_end_ms?: number | null;
            hidden?: boolean;
            sound_role?: string | null;
            display_id?: string | null;
            edit_values?: Record<string, unknown>;
        }>;
        proposal_id?: string | null;
        parent_version_id?: number | null;
        created_by?: string;
    }) => {
        const response = await fetch(`${API_BASE_URL}/edit-version/${encodeURIComponent(projectId)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const body = await response.json().catch(() => ({}));
        return { ok: response.ok && body?.ok !== false, status: response.status, body };
    },

    listEditVersions: async (projectId: string) => {
        return await fetcher(`/edit-version/${encodeURIComponent(projectId)}`);
    },

    getEditVersion: async (versionId: number) => {
        return await fetcher(`/edit-version/detail/${versionId}`);
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
    // sourceIds: 아카이브 '신규 프로젝트 생성' — 기존 원본을 재업로드 없이 연결
    createProject: async (name?: string, sourceIds?: string[]) => {
        return await fetcher(`/projects`, {
            method: "POST",
            body: JSON.stringify({ name: name ?? null, source_ids: sourceIds ?? [] }),
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

    // [SOFT-DELETE] 휴지통 목록 (deleted_at 있는 프로젝트, 30일 보관)
    listTrash: async () => {
        return await fetcher(`/projects/trash`);
    },

    // [SOFT-DELETE] 즉시 완전삭제(복원 불가)
    purgeProject: async (programId: string) => {
        return await fetcher(`/projects/${encodeURIComponent(programId)}/purge`, { method: "DELETE" });
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
