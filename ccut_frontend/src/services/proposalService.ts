/**
 * CCUT Editing Proposal Service (Service Layer)
 */

import { API_BASE_URL, fetcher } from "./api";
import { Fragment } from "@/data/fragmentData";

export interface Proposal {
    id: string;
    label: string;
    title: string;
    description: string;
    thumbnailHue: number;
    sequence: string[]; // List of fragment IDs
}

export const proposalService = {
    /**
     * Generate A/B editing proposals from the backend based on current fragments.
     */
    generateProposals: async (fragments: Fragment[]): Promise<{ a: Proposal; b: Proposal }> => {
        try {
            // Simplify fragments for the backend request
            const payload = {
                fragments: fragments.map(f => ({
                    id: f.fragment_id,
                    start: f.start_frame / 30.0,
                    hook_score: f.intelligence?.hook || 0.5
                }))
            };

            const response = await fetch(`${API_BASE_URL}/proposals/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error("Proposal generation failed");
            const data = await response.json();

            // Map backend response back to the Proposal interface
            return {
                a: {
                    id: data.A.label,
                    label: data.A.label,
                    title: data.A.title,
                    description: data.A.description,
                    thumbnailHue: 211,
                    sequence: data.A.sequence
                },
                b: {
                    id: data.B.label,
                    label: data.B.label,
                    title: data.B.title,
                    description: data.B.description,
                    thumbnailHue: 30,
                    sequence: data.B.sequence
                }
            };
        } catch (err) {
            console.error("[PROPOSAL] Backend failed, using fallback:", err);
            // Fallback logic: A (original), B (reverse or random)
            return {
                a: {
                    id: "A", label: "A", title: "내러티브 중심 (V-log)",
                    description: "촬영 순서를 유지하여 자연스러운 흐름 강조",
                    thumbnailHue: 211, sequence: fragments.map(f => f.fragment_id)
                },
                b: {
                    id: "B", label: "B", title: "비주얼 중심 (YouTube)",
                    description: "역동적인 편집을 위해 훅 점수 순으로 재배치",
                    thumbnailHue: 30, sequence: [...fragments].reverse().map(f => f.fragment_id)
                }
            };
        }
    }
};
