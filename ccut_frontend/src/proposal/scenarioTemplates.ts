import { ProposalMode } from "./proposalTypes";

export type ScenarioSlot =
    | "Hook" | "Intro" | "Context" | "Main"
    | "Reaction" | "Bridge" | "Payoff" | "Closing";

export interface ScenarioTemplate {
    id: string;
    mode: ProposalMode;
    title: string;
    desc: string;
    slots: ScenarioSlot[];
}

export const MARKET_BASE_TEMPLATE: ScenarioTemplate = {
    id: "market_base",
    mode: "market",
    title: "시장형 편집",
    desc: "초반 흡입력과 반응성을 우선한 편집안입니다.",
    slots: ["Hook", "Main", "Reaction", "Bridge", "Payoff", "Closing"],
};

export const MARKET_REACTION_TEMPLATE: ScenarioTemplate = {
    id: "market_reaction",
    mode: "market",
    title: "반응강조형 편집",
    desc: "반응 장면을 전진 배치해 체감 임팩트를 강화한 시장형 편집안입니다.",
    slots: ["Reaction", "Hook", "Reaction", "Main", "Payoff", "Closing"],
};

export const USER_BASE_TEMPLATE: ScenarioTemplate = {
    id: "user_base",
    mode: "user",
    title: "사용자친화형 편집",
    desc: "원본 흐름과 자연스러운 연결감을 유지한 편집안입니다.",
    slots: ["Intro", "Context", "Main", "Bridge", "Payoff", "Closing"],
};

export const USER_CONTEXT_TEMPLATE: ScenarioTemplate = {
    id: "user_context",
    mode: "user",
    title: "설명강화형 편집",
    desc: "맥락 이해를 위해 설명 흐름을 더 살린 사용자형 편집안입니다.",
    slots: ["Intro", "Context", "Context", "Bridge", "Payoff", "Closing"],
};
