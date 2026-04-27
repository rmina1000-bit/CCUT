// src/features/pbe/pbeTypes.ts
export type PBEOpenPayload = {
    mode: "left-edge" | "right-edge" | "seam";
    leftFragment?: Fragment | null;
    rightFragment?: Fragment | null;
    sourceFragments: Fragment[];
    editFragments: Fragment[];
};

export type PBEWindowResult = {
    fragments: Fragment[]; // max 4
    leftRealIndex?: number;
    rightRealIndex?: number;
    pattern: "L" | "R" | "SS" | "SNS" | "SNNS";
};

export type PBEApplyPayload = {
    updated_fragments: Fragment[];
    removed_fragment_ids: string[];
};
