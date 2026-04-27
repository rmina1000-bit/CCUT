import { Fragment } from "@/data/fragmentData";
import { getRole } from "./slotAllocator";

export interface ProposalPairValidation {
    pass: boolean;
    reason: string;
    overlap: number;
    firstDiff: boolean;
    roleSequenceDiff: boolean;
}

export function calcOverlap(a: string[], b: string[]): number {
    const setA = new Set(a);
    const setB = new Set(b);
    const intersection = [...setA].filter((x) => setB.has(x)).length;
    const denom = Math.max(1, Math.min(setA.size, setB.size));
    return intersection / denom;
}

export function validateScenarioPair(
    aFragments: Fragment[],
    bFragments: Fragment[]
): ProposalPairValidation {
    const aIds = aFragments.map((f) => f.fragment_id);
    const bIds = bFragments.map((f) => f.fragment_id);

    const firstDiff = (aIds[0] ?? "") !== (bIds[0] ?? "");
    const overlap = calcOverlap(aIds, bIds);
    const aRoles = aFragments.map((f) => getRole(f)).join(">");
    const bRoles = bFragments.map((f) => getRole(f)).join(">");
    const roleSequenceDiff = aRoles !== bRoles;

    // 조각 수와 상관없이 50% 이상 겹치면 FAIL (strict diversity)
    const overlapThreshold = 0.5;

    if (!firstDiff) {
        return { pass: false, reason: "same_first_fragment", overlap, firstDiff, roleSequenceDiff };
    }
    if (!roleSequenceDiff) {
        return { pass: false, reason: "same_role_sequence", overlap, firstDiff, roleSequenceDiff };
    }
    if (overlap >= overlapThreshold) {
        return { pass: false, reason: "too_much_overlap", overlap, firstDiff, roleSequenceDiff };
    }

    return { pass: true, reason: "ok", overlap, firstDiff, roleSequenceDiff };
}