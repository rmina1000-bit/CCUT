/**
 * pbeBoundaryOps.ts
 * PBE 전용 경계 연산 로직 (비례바편집창_구조.md §8~§10 구현)
 *
 * 사용처: src/features/pbe/PrecisionBoundaryEditor.tsx 만
 *
 * 원 출처: 구 src/lib/pbeEngine.ts 에서 PBE 전용 함수만 분리 이관.
 */

import { Fragment, SelectionState, FragmentStatus } from "@/data/fragmentData";
import { getUid, generateUid, commitFragments } from "@/lib/fragmentIdentity";

export interface BoundaryAdjustment {
    barIndex: number;
    leftFragId: string;
    rightFragId: string;
    frameDelta: number;
}

export interface ApplyBoundaryResult {
    updatedFragments: Fragment[];
    removedFragmentIds: string[];
}

function makeFragment(
    base: Fragment,
    startFrame: number,
    endFrame: number,
    state: SelectionState,
    opts: {
        displaySuffix?: string;
        status?: FragmentStatus;
        parentUid?: string;
        secondaryParentUid?: string;
        derivedFromOverride?: string;
    } = {}
): Fragment {
    const uid = generateUid();
    const rootUid = base.root_fragment_uid ?? getUid(base);
    const parentUid = opts.parentUid ?? getUid(base);
    const rootId = base.root_fragment_uid ? base.fragment_id.replace(/_[LMR]\d*$/, "") : base.fragment_id;
    const suffix = opts.displaySuffix ?? "";
    const fragId = suffix ? `${rootId}${suffix}` : rootId;

    return {
        ...base,
        fragment_uid: uid,
        fragment_id: fragId,
        root_fragment_uid: rootUid,
        parent_fragment_uid: parentUid,
        secondary_parent_uid: opts.secondaryParentUid,
        derivedFrom: opts.derivedFromOverride ?? parentUid,
        display_id: undefined,
        selection_state: state,
        status: opts.status ?? "candidate",
        start_frame: startFrame,
        end_frame: endFrame,
        duration: endFrame - startFrame,
    };
}

/** [Case 3] S|S Boundary Apply */
export function applySSBoundary(
    L: Fragment, R: Fragment, a: number, b: number
): { left: Fragment; leftTrimmed?: Fragment; rightTrimmed?: Fragment; right: Fragment; removed: string[] } {
    const removed: string[] = [];
    const Lprime = makeFragment(L, L.start_frame, L.end_frame - a, "S", { displaySuffix: a > 0 ? "_L" : "", parentUid: getUid(L) });
    const Rprime = makeFragment(R, R.start_frame + b, R.end_frame, "S", { displaySuffix: b > 0 ? "_R" : "", parentUid: getUid(R) });
    
    let leftTrimmed: Fragment | undefined;
    if (a > 0) {
        leftTrimmed = makeFragment(L, L.end_frame - a, L.end_frame, "N", {
            displaySuffix: "_R",
            parentUid: getUid(L)
        });
        removed.push(getUid(L));
    }
    
    let rightTrimmed: Fragment | undefined;
    if (b > 0) {
        rightTrimmed = makeFragment(R, R.start_frame, R.start_frame + b, "N", {
            displaySuffix: "_L",
            parentUid: getUid(R)
        });
        removed.push(getUid(R));
    }
    
    return { left: Lprime, leftTrimmed, rightTrimmed, right: Rprime, removed };
}

/** [Case 4/5] S|N|S Boundary Apply */
export function applySNSBoundary(
    L: Fragment, Ns: Fragment[], R: Fragment, a: number, b: number
): { left: Fragment; leftSub?: Fragment; midRem?: Fragment; rightSub?: Fragment; right: Fragment; removed: string[] } {
    const Nstart = Ns[0].start_frame;
    const Nend = Ns[Ns.length - 1].end_frame;
    const m = Nend - Nstart;
    const removed: string[] = [];
    const safeA = Math.min(a, m);
    const safeB = Math.min(b, m - safeA);
    let leftSub, midRem, rightSub;
    const baseN = Ns[0];
    if (safeA > 0) {
        leftSub = makeFragment(baseN, Nstart, Nstart + safeA, "S", { displaySuffix: "_L", parentUid: getUid(baseN) });
    }
    if (safeA + safeB < m) {
        midRem = makeFragment(baseN, Nstart + safeA, Nend - safeB, "N", { displaySuffix: "_M", parentUid: getUid(baseN) });
    }
    if (safeB > 0) {
        rightSub = makeFragment(baseN, Nend - safeB, Nend, "S", { displaySuffix: "_R", parentUid: getUid(baseN) });
    }
    Ns.forEach(n => removed.push(getUid(n)));
    return { left: L, leftSub, midRem, rightSub, right: R, removed };
}

/** [Case 1/2] Single Trim */
export function applySingleTrim(
    frag: Fragment, trimFrames: number, side: "left" | "right"
): { kept: Fragment; trimmed?: Fragment; removed: string[] } {
    if (trimFrames <= 0) return { kept: frag, removed: [] };
    let kept, trimmed;
    if (side === "left") {
        trimmed = makeFragment(frag, frag.start_frame, frag.start_frame + trimFrames, "N", { 
            displaySuffix: "_L",
            parentUid: getUid(frag) 
        });
        kept = makeFragment(frag, frag.start_frame + trimFrames, frag.end_frame, "S", { 
            displaySuffix: "_R",
            parentUid: getUid(frag) 
        });
    } else {
        kept = makeFragment(frag, frag.start_frame, frag.end_frame - trimFrames, "S", { 
            displaySuffix: "_L",
            parentUid: getUid(frag) 
        });
        trimmed = makeFragment(frag, frag.end_frame - trimFrames, frag.end_frame, "N", { 
            displaySuffix: "_R",
            parentUid: getUid(frag) 
        });
    }
    return { kept, trimmed, removed: [getUid(frag)] };
}

const _removedLog: any[] = [];
export function getRemovedLog() { return [..._removedLog]; }
export function clearRemovedLog() { _removedLog.length = 0; }

export function applyPBEResultToFragments(
    editFragments: Fragment[],
    originalIds: string[],
    newFragments: Fragment[],
    removedIds: string[]
): Fragment[] {
    const firstIdx = editFragments.findIndex(f => originalIds.includes(getUid(f)));
    if (firstIdx < 0) return editFragments;

    const now = Date.now();
    editFragments.forEach(f => {
        if (removedIds.includes(getUid(f))) {
            _removedLog.push({ ...f, removedAt: now });
        }
    });

    const filtered = editFragments.filter(f =>
        !originalIds.includes(getUid(f)) && !removedIds.includes(getUid(f))
    );

    const committed = commitFragments(newFragments);
    filtered.splice(firstIdx, 0, ...committed);

    // recalcDisplayIds는 호출자(PrecisionBoundaryEditor 또는 Index.tsx)에서 적용
    return filtered;
}

/** 
 * PBE Apply 로직: 전체 timeline(editFragments)에 대해 
 * 드래그된 델타(frameDelta)를 적용하여 새로운 timeline을 반환합니다.
 */
export function applyBoundaryAdjustments(
    fragments: Fragment[],
    adjustments: BoundaryAdjustment[]
): ApplyBoundaryResult {
    // 1. 전체 timeline 복사
    const updated = fragments.map(f => ({ ...f }));

    // 2. 각 조정 사항(adjustment) 적용
    adjustments.forEach(adj => {
        // ID가 일치하는 조각 찾기
        const left = updated.find(f => f.fragment_id === adj.leftFragId);
        const right = updated.find(f => f.fragment_id === adj.rightFragId);

        // 왼쪽 조각의 끝점을 delta만큼 이동
        if (left) {
            left.end_frame += adj.frameDelta;
            left.duration = Math.max(0, left.end_frame - left.start_frame);
        }
        // 오른쪽 조각의 시작점을 delta만큼 이동
        if (right) {
            right.start_frame += adj.frameDelta;
            right.duration = Math.max(0, right.end_frame - right.start_frame);
        }
    });

    return {
        updatedFragments: updated,
        removedFragmentIds: []
    };
}
