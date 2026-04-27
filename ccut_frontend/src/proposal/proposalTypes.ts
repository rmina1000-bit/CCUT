export type ProposalMode = "market" | "user";

export type DirectionTone = "emotional" | "natural" | "hook-first";
export type DirectionPace = "fast" | "slow" | "medium";
export type DirectionStructure = "hook-priority" | "chronological" | "balanced";

export type FragmentRole =
    | "Hook"
    | "Intro"
    | "Context"
    | "Main"
    | "Reaction"
    | "Bridge"
    | "Payoff"
    | "Closing";

export interface Direction {
    tone?: DirectionTone | string;
    pace?: DirectionPace | string;
    structure?: DirectionStructure | string;
    highlight?: string;
    shorten_intro?: boolean;
    emphasize_role?: FragmentRole;
}

export interface DirectionSnapshot {
    snapshot_id: string;
    active_direction: Direction;
    change_log: string[];
}

export interface ProposalSlotTrace {
    slot: string;
    fragment_id: string;
    role: FragmentRole | "Unknown";
    hook_score: number;
}

export interface Proposal {
    id: "A" | "B";
    mode: ProposalMode;
    title: string;
    desc: string;
    score: string;
    key_fragments: string[];
    direction: Direction;
    snapshot_id: string;
    template_id: string;
    slot_trace: ProposalSlotTrace[];
}