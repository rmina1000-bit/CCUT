/**
 * [LEGACY] CLIENT-SIDE PROPOSAL FALLBACK ONLY.
 * Do not use as official proposal/narrative SSOT.
 * Backend ProposalEngine is canonical for multi-source proposal_story/proposal_explanation/source_usage.
 */
import { Fragment } from "@/data/fragmentData";
import { DirectionSnapshot, Proposal, ProposalSlotTrace } from "./proposalTypes";
import {
    MARKET_BASE_TEMPLATE, MARKET_REACTION_TEMPLATE,
    ScenarioTemplate, USER_BASE_TEMPLATE, USER_CONTEXT_TEMPLATE,
} from "./scenarioTemplates";
import {
    allocateSlots, getHookScore, getRole,
    getStartFrame, getTranscript,
} from "./slotAllocator";
import { validateScenarioPair } from "./proposalValidator";

function hasEnoughRole(fragments: Fragment[], role: string, count = 1): boolean {
    return fragments.filter((f) => getRole(f) === role).length >= count;
}

function hasRichContext(fragments: Fragment[]): boolean {
    return fragments.filter(
        (f) => getRole(f) === "Context" && getTranscript(f).length > 0
    ).length >= 2;
}

function pickMarketTemplate(fragments: Fragment[]): ScenarioTemplate {
    if (hasEnoughRole(fragments, "Reaction", 2)) return MARKET_REACTION_TEMPLATE;
    return MARKET_BASE_TEMPLATE;
}

function pickUserTemplate(fragments: Fragment[]): ScenarioTemplate {
    if (hasRichContext(fragments)) return USER_CONTEXT_TEMPLATE;
    return USER_BASE_TEMPLATE;
}

function applyDirectionToTemplate(
    template: ScenarioTemplate,
    snapshot: DirectionSnapshot,
    mode: "market" | "user"
): ScenarioTemplate {
    const d = snapshot.active_direction;

    if (mode === "market") {
        if (d.structure === "chronological") {
            return {
                ...template,
                id: `${template.id}_chronological_bias`,
                slots: ["Hook", "Main", "Bridge", "Payoff", "Reaction", "Closing"],
            };
        }
        if (d.highlight === "웃긴") {
            return {
                ...template,
                id: `${template.id}_funny_bias`,
                slots: ["Reaction", "Hook", "Reaction", "Main", "Payoff", "Closing"],
            };
        }
        return template;
    }

    if (d.shorten_intro) {
        return {
            ...template,
            id: `${template.id}_short_intro`,
            slots: template.slots.filter((s, idx) => !(idx === 0 && s === "Intro")),
        };
    }
    if (d.highlight === "설명") {
        return {
            ...template,
            id: `${template.id}_explain_bias`,
            slots: ["Intro", "Context", "Context", "Main", "Bridge", "Closing"],
        };
    }
    if (d.structure === "hook-priority") {
        return {
            ...template,
            id: `${template.id}_hookish`,
            slots: ["Intro", "Main", "Context", "Bridge", "Payoff", "Closing"],
        };
    }
    return template;
}

function buildProposal(
    id: "A" | "B",
    mode: "market" | "user",
    template: ScenarioTemplate,
    snapshot: DirectionSnapshot,
    selected: Fragment[],
    trace: ProposalSlotTrace[]
): Proposal {
    let title = template.title;
    let desc = template.desc;

    if (mode === "market" && snapshot.active_direction.highlight === "웃긴") {
        title = "반응강조형 편집";
        desc = "웃긴 장면과 반응 조각을 전진 배치한 시장형 편집안입니다.";
    }
    if (mode === "user" && snapshot.active_direction.highlight === "설명") {
        title = "설명강화형 편집";
        desc = "맥락 이해를 살리기 위해 설명 흐름을 강화한 사용자형 편집안입니다.";
    }

    const avgHook =
        selected.length > 0
            ? selected.reduce((acc, f) => acc + getHookScore(f), 0) / selected.length
            : 0;

    return {
        id,
        mode,
        title,
        desc,
        score: `${Math.round(Math.max(0.5, avgHook) * 100)}%`,
        key_fragments: selected.map((f) => f.fragment_id),
        direction: snapshot.active_direction,
        snapshot_id: snapshot.snapshot_id,
        template_id: template.id,
        slot_trace: trace,
    };
}

function reallocateUserAlternative(
    fragments: Fragment[],
    snapshot: DirectionSnapshot
): { selected: Fragment[]; trace: ProposalSlotTrace[]; template: ScenarioTemplate } {
    const altTemplate: ScenarioTemplate = {
        ...USER_BASE_TEMPLATE,
        id: "user_alt_timeflow",
        slots: ["Intro", "Main", "Bridge", "Context", "Payoff", "Closing"],
    };
    const { selected, trace } = allocateSlots(
        altTemplate.slots, fragments, snapshot.active_direction, "user"
    );
    return { selected, trace, template: altTemplate };
}

function lastResortSplit(
    fragments: Fragment[]
): { marketSelected: Fragment[]; userSelected: Fragment[] } {
    if (fragments.length < 2) {
        return { marketSelected: [...fragments], userSelected: [...fragments] };
    }

    const sorted_by_hook = [...fragments].sort(
        (a, b) => getHookScore(b) - getHookScore(a)
    );
    const sorted_by_time = [...fragments].sort(
        (a, b) => getStartFrame(a) - getStartFrame(b)
    );

    const half = Math.ceil(fragments.length / 2);
    const marketSelected = sorted_by_hook.slice(0, half);
    const userSelected = sorted_by_time.slice(Math.floor(fragments.length / 2));

    if (
        marketSelected[0]?.fragment_id === userSelected[0]?.fragment_id &&
        userSelected.length > 1
    ) {
        userSelected.reverse();
    }

    return { marketSelected, userSelected };
}

export function buildProposalPair(
    fragments: Fragment[],
    snapshot: DirectionSnapshot
): Record<"A" | "B", Proposal> {
    const marketTemplate = applyDirectionToTemplate(
        pickMarketTemplate(fragments), snapshot, "market"
    );
    const userTemplate = applyDirectionToTemplate(
        pickUserTemplate(fragments), snapshot, "user"
    );

    let { selected: marketSelected, trace: marketTrace } = allocateSlots(
        marketTemplate.slots, fragments, snapshot.active_direction, "market"
    );
    let { selected: userSelected, trace: userTrace } = allocateSlots(
        userTemplate.slots, fragments, snapshot.active_direction, "user"
    );

    let finalMarketTmpl = marketTemplate;
    let finalUserTmpl = userTemplate;

    let validation = validateScenarioPair(marketSelected, userSelected);
    console.log("[validator][1차]", validation);

    if (!validation.pass) {
        const altUser = reallocateUserAlternative(fragments, snapshot);
        userSelected = altUser.selected;
        userTrace = altUser.trace;
        finalUserTmpl = altUser.template;
        validation = validateScenarioPair(marketSelected, userSelected);
        console.log("[validator][2차]", validation);
    }

    if (!validation.pass) {
        const altMarketTmpl: ScenarioTemplate = {
            ...MARKET_REACTION_TEMPLATE,
            id: "market_alt_aggressive",
            slots: ["Hook", "Reaction", "Main", "Reaction", "Payoff", "Closing"],
        };
        const altMarket = allocateSlots(
            altMarketTmpl.slots, fragments, snapshot.active_direction, "market"
        );
        marketSelected = altMarket.selected;
        marketTrace = altMarket.trace;
        finalMarketTmpl = altMarketTmpl;
        validation = validateScenarioPair(marketSelected, userSelected);
        console.log("[validator][3차]", validation);
    }

    if (!validation.pass) {
        console.warn("[proposalEngine] 3차 보정 실패 → 최후 수단 분기");
        const { marketSelected: lastMarket, userSelected: lastUser } =
            lastResortSplit(fragments);

        marketSelected = lastMarket;
        userSelected = lastUser;
        marketTrace = lastMarket.map((f, i) => ({
            slot: `LastResort_A_${i}`, fragment_id: f.fragment_id,
            role: getRole(f), hook_score: getHookScore(f),
        }));
        userTrace = lastUser.map((f, i) => ({
            slot: `LastResort_B_${i}`, fragment_id: f.fragment_id,
            role: getRole(f), hook_score: getHookScore(f),
        }));
        finalMarketTmpl = { ...MARKET_BASE_TEMPLATE, id: "market_last_resort" };
        finalUserTmpl = { ...USER_BASE_TEMPLATE, id: "user_last_resort" };
    }

    const A = buildProposal("A", "market", finalMarketTmpl, snapshot, marketSelected, marketTrace);
    const B = buildProposal("B", "user", finalUserTmpl, snapshot, userSelected, userTrace);

    console.log("[proposalEngine] A template:", A.template_id, "| 첫 조각:", A.key_fragments[0]);
    console.log("[proposalEngine] B template:", B.template_id, "| 첫 조각:", B.key_fragments[0]);
    console.log("[proposalEngine] A/B 첫 조각 다름:", A.key_fragments[0] !== B.key_fragments[0]);

    return { A, B };
}
