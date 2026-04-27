import { Fragment } from "@/data/fragmentData";

/** A fragment visible on the board (not excluded) */
export interface VisibleFragment {
  fragment: Fragment;
  /** Index in the full fragments array */
  realIndex: number;
}

/** A fragment excluded from render but structurally present */
export interface ExcludedStructuralFragment {
  fragment: Fragment;
  realIndex: number;
}

/** An internal boundary between two structurally adjacent fragments */
export interface InternalBoundary {
  id: string;
  /** Index of the left fragment in the full fragments array */
  leftRealIndex: number;
  /** Index of the right fragment in the full fragments array */
  rightRealIndex: number;
  leftFragmentId: string;
  rightFragmentId: string;
}

/** A synthetic collapsed seam: the visual join between two visible fragments
 *  that hides one or more excluded structural fragments. */
export interface SyntheticCollapsedSeam {
  leftVisibleFragmentId: string;
  rightVisibleFragmentId: string;
  hiddenExcludedFragmentIds: string[];
  internalBoundaries: InternalBoundary[];
  /** Index of left visible fragment in full array */
  leftRealIndex: number;
  /** Index of right visible fragment in full array */
  rightRealIndex: number;
}

/** State for the precision overlay */
export interface PrecisionOverlayState {
  seam: SyntheticCollapsedSeam;
  /** All fragments in the revealed chain (left visible + excluded + right visible) */
  chainRealIndices: number[];
  /** Anchor position for overlay placement */
  anchorRect: DOMRect;
}

/** Detect all synthetic collapsed seams in a fragment array.
 *  A seam exists wherever one or more consecutive excluded fragments
 *  sit between two non-excluded (visible) fragments. */
export function detectSyntheticSeams(fragments: Fragment[]): SyntheticCollapsedSeam[] {
  const seams: SyntheticCollapsedSeam[] = [];
  let i = 0;
  while (i < fragments.length) {
    // Find a non-excluded fragment
    if (fragments[i].excluded) { i++; continue; }

    const leftIdx = i;
    // Look ahead for excluded run followed by another non-excluded
    let j = i + 1;
    while (j < fragments.length && fragments[j].excluded) j++;

    // j now points to next non-excluded (or end)
    if (j > i + 1 && j < fragments.length) {
      // We have excluded fragments between leftIdx and j
      const excludedIds: string[] = [];
      const boundaries: InternalBoundary[] = [];

      for (let k = i + 1; k < j; k++) {
        excludedIds.push(fragments[k].fragment_id);
      }

      // Build internal boundaries for the full chain [leftIdx .. j]
      for (let k = leftIdx; k < j; k++) {
        boundaries.push({
          id: `${fragments[k].fragment_id}-${fragments[k + 1].fragment_id}`,
          leftRealIndex: k,
          rightRealIndex: k + 1,
          leftFragmentId: fragments[k].fragment_id,
          rightFragmentId: fragments[k + 1].fragment_id,
        });
      }

      seams.push({
        leftVisibleFragmentId: fragments[leftIdx].fragment_id,
        rightVisibleFragmentId: fragments[j].fragment_id,
        hiddenExcludedFragmentIds: excludedIds,
        internalBoundaries: boundaries,
        leftRealIndex: leftIdx,
        rightRealIndex: j,
      });
    }

    i = j > i + 1 ? j : i + 1;
  }
  return seams;
}

/** Find the seam that contains a given pair of visible fragment indices */
export function findSeamForVisiblePair(
  seams: SyntheticCollapsedSeam[],
  leftVisibleId: string,
  rightVisibleId: string,
): SyntheticCollapsedSeam | null {
  return seams.find(
    s => s.leftVisibleFragmentId === leftVisibleId && s.rightVisibleFragmentId === rightVisibleId
  ) ?? null;
}
