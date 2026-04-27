import { Fragment } from "@/data/fragmentData";
import { Direction, FragmentRole, ProposalSlotTrace } from "./proposalTypes";
import { ScenarioSlot } from "./scenarioTemplates";

type RoleOrUnknown = FragmentRole | "Unknown";

function safeText(v?: string | null): string {
    return (v || "").trim().toLowerCase();
}

export function getHookScore(fragment: Fragment): number {
    const intel = fragment.intelligence as any;
    return Number(intel?.hook_score ?? intel?.hook ?? 0);
}

export function getRole(fragment: Fragment): RoleOrUnknown {
    const intel = fragment.intelligence as any;
    return (intel?.role as FragmentRole | undefined) ?? "Unknown";
}

export function getTranscript(fragment: Fragment): string {
    return (fragment.intelligence as any)?.transcript ?? "";
}

export function getStartFrame(fragment: Fragment): number {
    return fragment.start_frame ?? 0;
}

export function getDuration(fragment: Fragment): number {
    return fragment.duration ?? Math.max(1, (fragment.end_frame ?? 0) - (fragment.start_frame ?? 0));
}

function includesHighlight(fragment: Fragment, highlight?: string): boolean {
    if (!highlight) return false;
    const q = safeText(highlight);
    const t = safeText(getTranscript(fragment));
    const v = safeText((fragment.intelligence as any)?.visual_description ?? "");
    return t.includes(q) || v.includes(q);
}

function roleMatches(slot: ScenarioSlot, role: RoleOrUnknown): boolean {
    if (role === "Unknown") return false;
    switch (slot) {
        case "Hook": return role === "Hook" || role === "Reaction";
        case "Intro": return role === "Intro";
        case "Context": return role === "Context";
        case "Main": return role === "Main" || role === "Payoff";
        case "Reaction": return role === "Reaction" || role === "Hook";
        case "Bridge": return role === "Bridge";
        case "Payoff": return role === "Payoff" || role === "Main";
        case "Closing": return role === "Closing";
        default: return false;
    }
}

function scoreForSlot(
    fragment: Fragment,
    slot: ScenarioSlot,
    direction: Direction,
    preferChronological: boolean
): number {
    const role = getRole(fragment);
    const hook = getHookScore(fragment);
    const start = getStartFrame(fragment);
    const duration = getDuration(fragment);
    let score = 0;

    if (roleMatches(slot, role)) score += 100;
    score += hook * 30;

    if (direction.highlight && includesHighlight(fragment, direction.highlight)) score += 20;
    if (direction.emphasize_role && role === direction.emphasize_role) score += 25;
    if (direction.tone === "emotional" && (role === "Reaction" || role === "Payoff")) score += 15;
    if (direction.tone === "natural" && (role === "Intro" || role === "Context" || role === "Bridge")) score += 15;
    if (direction.tone === "hook-first" && (role === "Hook" || role === "Reaction")) score += 18;
    if (direction.pace === "fast") {
        if (role === "Bridge" || role === "Context") score -= duration * 0.01;
        if (role === "Hook" || role === "Reaction" || role === "Main") score += 10;
    }
    if (direction.pace === "slow") {
        if (role === "Intro" || role === "Context" || role === "Bridge") score += 10;
    }
    if (direction.shorten_intro && slot === "Intro") score -= duration * 0.03;

    score -= start * (preferChronological ? 0.001 : 0.0002);
    return score;
}

function fallbackSort(fragments: Fragment[], preferChronological: boolean): Fragment[] {
    const arr = [...fragments];
    if (preferChronological) {
        return arr.sort((a, b) => getStartFrame(a) - getStartFrame(b));
    }
    return arr.sort((a, b) => {
        const hookDiff = getHookScore(b) - getHookScore(a);
        return hookDiff !== 0 ? hookDiff : getStartFrame(a) - getStartFrame(b);
    });
}

export function pickBestFragmentForSlot(
    slot: ScenarioSlot,
    fragments: Fragment[],
    usedIds: Set<string>,
    direction: Direction,
    preferChronological: boolean
): Fragment | null {
    const candidates = fragments.filter((f) => !usedIds.has(f.fragment_id));
    if (candidates.length === 0) return null;

    const ranked = [...candidates].sort((a, b) => {
        const diff = scoreForSlot(b, slot, direction, preferChronological)
            - scoreForSlot(a, slot, direction, preferChronological);
        if (diff !== 0) return diff;
        const hookDiff = getHookScore(b) - getHookScore(a);
        return hookDiff !== 0 ? hookDiff : getStartFrame(a) - getStartFrame(b);
    });

    const exact = ranked.find((f) => roleMatches(slot, getRole(f)));
    if (exact) return exact;

    return fallbackSort(candidates, preferChronological)[0] ?? null;
}

export function allocateSlots(
    slots: ScenarioSlot[],
    fragments: Fragment[],
    direction: Direction,
    mode: "market" | "user"
): { selected: Fragment[]; trace: ProposalSlotTrace[] } {
    const usedIds = new Set<string>();
    const selected: Fragment[] = [];
    const trace: ProposalSlotTrace[] = [];
    const preferChronological = mode === "user";

    for (const slot of slots) {
        const picked = pickBestFragmentForSlot(
            slot, fragments, usedIds, direction, preferChronological
        );
        if (!picked) continue;
        usedIds.add(picked.fragment_id);
        selected.push(picked);
        trace.push({
            slot,
            fragment_id: picked.fragment_id,
            role: getRole(picked),
            hook_score: getHookScore(picked),
        });
    }

    return { selected, trace };
}
