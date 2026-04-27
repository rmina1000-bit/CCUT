import { Fragment, applyPairBoundary, processCentralGap, InvariantValidator } from "./pbeCore";

/**
 * PBE 연결 어댑터 (Adapter between UI State and Core Logic)
 */

export interface PBEInternalState {
    fragments: Fragment[];
    leftFrag: Fragment;
    rightFrag: Fragment;
    hL_frame: number; // leftBoundaryFrame: frames from start of leftSource
    hR_frame: number; // rightBoundaryFrame: frames from end of rightSource
}

export function computePBEFinalResult(state: PBEInternalState): Fragment[] {
    const { fragments, leftFrag, rightFrag, hL_frame, hR_frame } = state;

    // 1. Same-source case
    if (leftFrag.source_video === rightFrag.source_video) {
        // Find adjacent pair
        const pairAIdx = fragments.findIndex(f => f.fragment_id === leftFrag.fragment_id);
        const pairBIdx = fragments.findIndex(f => f.fragment_id === rightFrag.fragment_id);
        if (pairAIdx === -1 || pairBIdx === -1) return fragments;

        // Apply boundary using x (displacement on combined axis)
        // x is current total left source frames (hL_frame)
        const result = applyPairBoundary(leftFrag, rightFrag, hL_frame);

        const newFragments = [...fragments];
        // Replace old pair with new set (sel/rem/sel)
        const toAdd = [result.fA_sel, result.fA_rem, result.fB_sel, result.fB_rem].filter((f): f is Fragment => f !== undefined);
        newFragments.splice(pairAIdx, 2, ...toAdd);
        return newFragments;
    }

    // 2. Cross-source case (Gap in between or adjacent)
    else {
        const leftIdx = fragments.findIndex(f => f.fragment_id === leftFrag.fragment_id);
        const rightIdx = fragments.findIndex(f => f.fragment_id === rightFrag.fragment_id);
        if (leftIdx === -1 || rightIdx === -1) return fragments;

        const centralIdxs = [];
        for (let i = leftIdx + 1; i < rightIdx; i++) centralIdxs.push(i);

        if (centralIdxs.length === 1) {
            const m_frag = fragments[centralIdxs[0]];
            // m_frag is the non-selection gap
            const a = hL_frame - leftFrag.duration; // take from gap
            const b = rightFrag.duration - hR_frame; // take from gap
            const results = processCentralGap(m_frag, a, b);

            const newFragments = [...fragments];
            const toAdd = [results.left_sub, results.mid_rem, results.right_sub].filter((f): f is Fragment => f !== undefined);
            newFragments.splice(centralIdxs[0], 1, ...toAdd);
            return newFragments;
        }
    }

    return fragments;
}
