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
    // [PROPOSAL_PREVIEW] 백엔드 렌더링된 preview mp4 URL
    preview_url?: string | null;
    preview_duration?: number;
}

export type StoryDirectionOption = {
  id: "market_highlight" | "user_memory" | "fast" | "emotional" | "balanced";
  label: string;
  description: string;
};

export type NarrativeConsultationStatus =
  | "pending"
  | "draft_ready"
  | "user_requested_change"
  | "confirmed";

export type ConsultationMessage = {
  id: string;
  sender: "ai" | "user";
  text: string;
  timestamp: number;
  // [관문D 2026-07-21] 큐원 판단근거 {fragment_id: ["scene: ...","speech: ...","context: ...","meta: ..."]}
  candidate_evidence?: Record<string, string[]>;
};

export type StoryPlanPreview = {
  story_plan_id: string;
  project_type: string;
  detected_theme: string;
  default_direction: "market_highlight" | "user_memory";
  direction_options: StoryDirectionOption[];
  source_roles: Record<string, string>;
  risk_sources: Array<{
    source_id: string;
    label: string;
    reason: string;
    status: "WEAK" | "JUNK_SUSPECT" | "EXCLUDE_RECOMMENDED";
  }>;
  confirmation_status: "pending" | "confirmed" | "adjusted";
  selected_direction?: string;
  consultation_status?: NarrativeConsultationStatus;
  narrative_draft?: string;
  user_notes?: string;
  messages?: ConsultationMessage[]; 
  story_intent?: {
    pace?: "slow" | "medium" | "fast";
    mood?: "calm" | "warm" | "emotional" | "dynamic";
    focus?: "people" | "landscape" | "balanced" | "memory";
    coverage?: "quality_first" | "balanced_sources" | "user_priority";
    avoid?: string[];
    emphasize?: string[];
  };
};