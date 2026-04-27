// src/features/pbe/pbeWindow.ts
import { Fragment } from "@/data/fragmentData";
import { getUid } from "@/lib/pbeEngine";

/** Helper: same source neighbors */
function getSourceNeighbors(sourcePool: Fragment[], frag: Fragment | null) {
    if (!frag) return { prev: null as Fragment | null, next: null as Fragment | null };
    const sameSource = sourcePool
        .filter((f) => f.source_video === frag.source_video)
        .sort((a, b) => (a.start_frame ?? 0) - (b.start_frame ?? 0));
    const idx = sameSource.findIndex((f) => getUid(f) === getUid(frag));
    if (idx < 0) return { prev: null, next: null };
    return {
        prev: idx > 0 ? sameSource[idx - 1] : null,
        next: idx < sameSource.length - 1 ? sameSource[idx + 1] : null,
    };
}

/** Helper: deduplicate by uid */
export function uniqueByUid(frags: Array<Fragment | null | undefined>): Fragment[] {
    const map = new Map<string, Fragment>();
    frags.forEach((f) => {
        if (!f) return;
        map.set(getUid(f), f);
    });
    return Array.from(map.values());
}

/** M1 – build window according to document §6 */
export function buildPbeWindow(params: {
    leftFragment: Fragment | null;
    rightFragment: Fragment | null;
    sourcePool: Fragment[];
}): Fragment[] {
    const { leftFragment, rightFragment, sourcePool } = params;

    // same‑source case
    if (leftFragment && rightFragment && leftFragment.source_video === rightFragment.source_video) {
        const { prev: prevL } = getSourceNeighbors(sourcePool, leftFragment);
        const { next: nextR } = getSourceNeighbors(sourcePool, rightFragment);
        return uniqueByUid([prevL, leftFragment, rightFragment, nextR]).slice(0, 4);
    }

    // cross‑source case
    if (leftFragment && rightFragment && leftFragment.source_video !== rightFragment.source_video) {
        const { next: nextL } = getSourceNeighbors(sourcePool, leftFragment);
        const { prev: prevR } = getSourceNeighbors(sourcePool, rightFragment);
        return uniqueByUid([leftFragment, nextL, prevR, rightFragment]).slice(0, 4);
    }

    // single‑left edge
    if (leftFragment && !rightFragment) {
        const { prev: prevL } = getSourceNeighbors(sourcePool, leftFragment);
        return uniqueByUid([prevL, leftFragment]).slice(0, 2);
    }

    // single‑right edge
    if (!leftFragment && rightFragment) {
        const { next: nextR } = getSourceNeighbors(sourcePool, rightFragment);
        return uniqueByUid([rightFragment, nextR]).slice(0, 2);
    }

    return [];
}
