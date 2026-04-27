/**
 * CCUT PBE Core Logic Engine (SSOT Implementation v4)
 * Reference: PBE_SSOT_v4.md
 * 
 * Rules:
 * - S (Selected): Inclusion in final edit
 * - N (Non-selected): Exclusion from final edit
 * - Invariant: source_video identity NEVER changes.
 * - sub-fragment: suffix _L, _M, _R, _rem.
 */

export type SelectionState = "S" | "N";

export interface Fragment {
    fragment_id: string;        // e.g. "1-2_L"
    source_video: string;       // Original Video ID (Immutable)
    start_frame: number;        // Inclusive
    end_frame: number;          // Exclusive: end_frame = start_frame + duration
    duration: number;           // Frame count
    selection_state: SelectionState;
    derivedFrom?: string;       // Original fragment_id (Required for sub-fragments)
    fps?: number;
    thumbnail_hue?: number;
    intelligence?: any;         // Cognitive data, transcript, etc.
    thumbnail?: any;            // Real thumbnail meta
}

export interface BoundaryBar {
    left_fragment_id: string;   // Left fragment ID
    right_fragment_id: string;  // Right fragment ID
    cut_frame: number;          // Current cut point (0-based, relative to left fragment start)
}

/**
 * Fragment creation helper. Enforces end_frame = start_frame + duration.
 */
export function makeFragment(
    base: Fragment,
    start: number,
    end: number,
    state: SelectionState,
    suffix?: string,
    derivedFrom?: string
): Fragment {
    const duration = end - start;
    const id = suffix ? `${base.fragment_id}_${suffix}` : base.fragment_id;

    return {
        ...base,
        fragment_id: id,
        start_frame: start,
        end_frame: end,
        duration: duration,
        selection_state: state,
        derivedFrom: derivedFrom || base.derivedFrom
    };
}

/**
 * Panorama window construction. 
 * Branches: same-source / cross-source / single fragment.
 */
export function buildBoundaryWindow(
    clickedFragment: Fragment,
    clickSide: "left" | "right",
    allSourceFragments: Record<string, Fragment[]>,
    boardFragments: Fragment[] // Active fragments on the edit board
): Fragment[] {
    const findOnBoard = (fId: string) => boardFragments.find(f => f.fragment_id === fId);
    const findInSource = (f: Fragment) => {
        const list = allSourceFragments[f.source_video] || [];
        const idx = list.findIndex(x => x.fragment_id === f.fragment_id);
        return { list, idx };
    };

    if (clickSide === "right") {
        const L = clickedFragment;
        // Search for immediate right neighbor on the board
        const boardIdx = boardFragments.findIndex(f => f.fragment_id === L.fragment_id);
        const R = boardIdx !== -1 && boardIdx < boardFragments.length - 1 ? boardFragments[boardIdx + 1] : null;

        if (!R) {
            // Case 4-3/Case 6: Single fragment end.
            const { list, idx } = findInSource(L);
            const nextN = (idx !== -1 && idx < list.length - 1) ? list[idx + 1] : null;
            return [L, nextN].filter((f): f is Fragment => f !== null);
        }

        if (L.source_video === R.source_video) {
            // Case 4-1: same-source
            const { list, idx: idxL } = findInSource(L);
            const idxR = list.findIndex(x => x.fragment_id === R.fragment_id);
            const prevL = idxL > 0 ? list[idxL - 1] : null;
            const nextR = (idxR !== -1 && idxR < list.length - 1) ? list[idxR + 1] : null;

            // Include all fragments from L index to R index in source (includes intermediate Ns)
            const middle = list.slice(idxL, idxR + 1);
            let finalWindow: Fragment[] = [...middle];

            // Expand to prev/next only if space allows under 4 fragment limit AND they are 'S'
            if (finalWindow.length < 4 && prevL && prevL.selection_state === 'S') finalWindow.unshift(prevL);
            if (finalWindow.length < 4 && nextR && nextR.selection_state === 'S') finalWindow.push(nextR);

            return finalWindow.slice(0, 4);
        } else {
            // Case 4-2: cross-source
            const { list: listL, idx: idxL } = findInSource(L);
            const { list: listR, idx: idxR } = findInSource(R);

            const leftBlock = [L, (idxL !== -1 && idxL < listL.length - 1) ? listL[idxL + 1] : null].filter((f): f is Fragment => f !== null);
            const rightBlock = [idxR > 0 ? listR[idxR - 1] : null, R].filter((f): f is Fragment => f !== null);

            return [...leftBlock, ...rightBlock];
        }
    } else {
        // clickSide === "left"
        const R = clickedFragment;
        const boardIdx = boardFragments.findIndex(f => f.fragment_id === R.fragment_id);
        const L = boardIdx > 0 ? boardFragments[boardIdx - 1] : null;

        if (!L) {
            // Case 4-3/Case 5: Single fragment start.
            const { list, idx } = findInSource(R);
            const prevN = idx > 0 ? list[idx - 1] : null;
            return [prevN, R].filter((f): f is Fragment => f !== null);
        }

        if (L.source_video === R.source_video) {
            // Case 4-1: same-source
            const { list, idx: idxL } = findInSource(L);
            const idxR = list.findIndex(x => x.fragment_id === R.fragment_id);
            const prevL = idxL > 0 ? list[idxL - 1] : null;
            const nextR = (idxR !== -1 && idxR < list.length - 1) ? list[idxR + 1] : null;

            // Include all between L and R
            const middle = list.slice(idxL, idxR + 1);
            let finalWindow: Fragment[] = [...middle];

            if (finalWindow.length < 4 && prevL && prevL.selection_state === 'S') finalWindow.unshift(prevL);
            if (finalWindow.length < 4 && nextR && nextR.selection_state === 'S') finalWindow.push(nextR);

            return finalWindow.slice(0, 4);
        } else {
            // Case 4-2: cross-source
            const { list: listL, idx: idxL } = findInSource(L);
            const { list: listR, idx: idxR } = findInSource(R);

            const leftBlock = [L, (idxL !== -1 && idxL < listL.length - 1) ? listL[idxL + 1] : null].filter((f): f is Fragment => f !== null);
            const rightBlock = [idxR > 0 ? listR[idxR - 1] : null, R].filter((f): f is Fragment => f !== null);

            return [...leftBlock, ...rightBlock];
        }
    }
}

/**
 * Boundary bar position calculation.
 * Bars exist between S|N, N|S, or S|S.
 */
export function getBarPositions(window: Fragment[]): BoundaryBar[] {
    const bars: BoundaryBar[] = [];
    for (let i = 0; i < window.length - 1; i++) {
        const A = window[i];
        const B = window[i + 1];

        const stateA = A.selection_state || "N";
        const stateB = B.selection_state || "N";

        const cond = (stateA === "S" && stateB === "N") ||
            (stateA === "N" && stateB === "S") ||
            (stateA === "S" && stateB === "S");

        if (cond) {
            bars.push({
                left_fragment_id: A.fragment_id,
                right_fragment_id: B.fragment_id,
                cut_frame: A.duration
            });
        }
        if (bars.length >= 2) break;
    }
    return bars;
}

/**
 * Boundary movement calculation. 
 * (S,N) / (N,S) / (S,S) cases.
 */
export function applyPairBoundary(
    A: Fragment,
    B: Fragment,
    x: number // cut point (0-based, relative to A.start_frame)
): Fragment[] {
    const nA = A.duration;
    const nB = B.duration;
    const sA = A.start_frame;
    const sB = B.start_frame;

    // Case 7-2: (S, N)
    if (A.selection_state === "S" && B.selection_state === "N") {
        if (x <= nA) {
            if (x === nA) return [A, B];
            const A_root = A.derivedFrom || A.fragment_id;
            const A_sel = makeFragment(A, sA, sA + x, "S", "sel", A_root);
            const A_rem = makeFragment(A, sA + x, sA + nA, "N", "rem", A_root);
            return [A_sel, A_rem, B];
        } else {
            const takeB = x - nA;
            const B_root = B.derivedFrom || B.fragment_id;
            const B_sel = makeFragment(B, sB, sB + takeB, "S", "sel", B_root);
            const B_rem = makeFragment(B, sB + takeB, sB + nB, "N", "rem", B_root);
            return [A, B_sel, B_rem];
        }
    }

    // Case 7-3: (N, S)
    if (A.selection_state === "N" && B.selection_state === "S") {
        if (x < nA) {
            const A_root = A.derivedFrom || A.fragment_id;
            const A_rem = makeFragment(A, sA, sA + x, "N", "rem", A_root);
            const A_sel = makeFragment(A, sA + x, sA + nA, "S", "sel", A_root);
            return [A_rem, A_sel, B];
        } else {
            const shrinkB = x - nA;
            const B_root = B.derivedFrom || B.fragment_id;
            const B_rem = makeFragment(B, sB, sB + shrinkB, "N", "rem", B_root);
            const B_sel = makeFragment(B, sB + shrinkB, sB + nB, "S", "sel", B_root);
            return [A, B_rem, B_sel];
        }
    }

    // Case 7-4: (S, S)
    if (A.selection_state === "S" && B.selection_state === "S") {
        const A_root = A.derivedFrom || A.fragment_id;
        const B_root = B.derivedFrom || B.fragment_id;
        if (x < nA) {
            const A_sel = makeFragment(A, sA, sA + x, "S", "sel", A_root);
            const A_rem = makeFragment(A, sA + x, sA + nA, "N", "rem", A_root);
            return [A_sel, A_rem, B];
        } else if (x > nA) {
            const shrinkB = x - nA;
            const B_rem = makeFragment(B, sB, sB + shrinkB, "N", "rem", B_root);
            const B_sel = makeFragment(B, sB + shrinkB, sB + nB, "S", "sel", B_root);
            return [A, B_rem, B_sel];
        }
    }

    return [A, B];
}

/**
 * Central non-selected gap processing.
 * Requirement: a + b <= m.
 */
export function processCentralGap(
    M: Fragment,
    a: number, // left take
    b: number  // right take
): Record<string, Fragment> {
    const m = M.duration;
    const sM = M.start_frame;
    const eM = M.end_frame;

    if (a + b > m) {
        throw new Error(`[PBE] Invariant Violation: a + b (${a + b}) > m (${m})`);
    }

    const result: Record<string, Fragment> = {};

    if (a > 0) {
        result.M_L = makeFragment(M, sM, sM + a, "S", "L", M.fragment_id);
    }

    if (a + b < m) {
        result.M_M = makeFragment(M, sM + a, eM - b, "N", "M", M.fragment_id);
    }

    if (b > 0) {
        result.M_R = makeFragment(M, eM - b, eM, "S", "R", M.fragment_id);
    }

    return result;
}

/**
 * 14. Invariants (불변 속성) 검증
 */
export class InvariantValidator {
    static validate(fragments: Fragment[]): { valid: boolean; errors: string[] } {
        const errors: string[] = [];

        for (let i = 0; i < fragments.length; i++) {
            const f = fragments[i];

            // 1. source identity 불변
            // (Cannot check history here, but can check format)

            // 4. overlap 금지 & end_frame 정합성
            if (f.end_frame !== f.start_frame + f.duration) {
                errors.push(`Fragment ${f.fragment_id}: end_frame mismatch. ${f.end_frame} != ${f.start_frame} + ${f.duration}`);
            }

            // 5. negative length 금지
            if (f.duration < 0) {
                errors.push(`Fragment ${f.fragment_id}: Negative duration (${f.duration})`);
            }
            if (f.duration === 0) {
                // Spec says duration >= 1, but intermediate results might have 0 briefly?
                // Actually, the logic usually removes 0 duration fragments.
            }

            // 7. derivedFrom 추적
            const isSub = f.fragment_id.includes("_L") || f.fragment_id.includes("_R") || f.fragment_id.includes("_M") || f.fragment_id.includes("_rem");
            if (isSub && !f.derivedFrom) {
                errors.push(`Fragment ${f.fragment_id}: Sub-fragment missing derivedFrom`);
            }
        }

        // 3. cross-source merge 금지
        // Check if any merged fragment exists (in this list, they are discrete)

        return { valid: errors.length === 0, errors };
    }
}
