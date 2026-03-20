import { buildInitialBoardState } from '../data/fragmentData';
import { buildStructuralItems, unionSourceFragments } from '../utils/fragmentUtils';
import type { Fragment, PrecisionOverlayState, StructuralSeamItem } from '../types/boundaryTypes';

export function buildSmokeFixtures() {
  const board = buildInitialBoardState();
  const visibleFragment = board.editFragments.find((fragment) => !fragment.excluded);
  const reservedFragment = board.reservedFragments[0];
  const seamItem = buildStructuralItems(board.editFragments).find(
    (item): item is StructuralSeamItem => item.type === 'seam'
  );

  if (!visibleFragment || !reservedFragment || !seamItem) {
    throw new Error('Smoke fixtures could not resolve a visible fragment, reserved fragment, and seam.');
  }

  const overlay: PrecisionOverlayState = {
    entryType: 'boundary-click',
    mode: 'same-source',
    fragmentIds: [
      seamItem.seam.leftVisibleFragmentId,
      ...seamItem.seam.hiddenExcludedFragmentIds,
      seamItem.seam.rightVisibleFragmentId
    ],
    chainRealIndices: Array.from(
      { length: seamItem.seam.rightRealIndex - seamItem.seam.leftRealIndex + 1 },
      (_, index) => seamItem.seam.leftRealIndex + index
    ),
    anchorRect: new DOMRect(320, 180, 24, 24),
    activeBoundaryId: null
  };

  return {
    board,
    sourceFragments: unionSourceFragments(board.editFragments, board.reservedFragments),
    visibleFragment,
    reservedFragment,
    overlay
  };
}

export function noopFragmentHandler(_fragment: Fragment) {
  return;
}
