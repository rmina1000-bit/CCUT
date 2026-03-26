export interface FragmentThumbnail {
  thumbnail_url?: string;
  thumbnail_time?: number;
  extraction_version?: number;
  last_updated?: number;
}

export interface FragmentIntelligence {
  narrative: number;
  emotional: number;
  action: number;
  dialogue: number;
  hook: number;
  callback: number;
  confidence: number;
}

export interface Fragment {
  fragment_id: string;
  source_video: string;
  start_frame: number;
  end_frame: number;
  duration: number;
  thumbnail_hue: number;
  thumbnail?: FragmentThumbnail;
  excluded?: boolean;
  intelligence?: FragmentIntelligence;
}

export type AppState = 'empty' | 'analyzing' | 'proposal' | 'chat';

export interface Proposal {
  id: string;
  label: 'A' | 'B';
  title: string;
  description: string;
  thumbnailHue: number;
  fragmentIds: string[];
  editSequence: Fragment[];
}

export interface SourceVideo {
  id: string;
  label: string;
  totalFrames: number;
  fps: number;
  description: string;
}

export interface InternalBoundary {
  id: string;
  leftRealIndex: number;
  rightRealIndex: number;
  leftFragmentId: string;
  rightFragmentId: string;
}

export interface SyntheticCollapsedSeam {
  leftVisibleFragmentId: string;
  rightVisibleFragmentId: string;
  hiddenExcludedFragmentIds: string[];
  internalBoundaries: InternalBoundary[];
  leftRealIndex: number;
  rightRealIndex: number;
  rowIndex?: number;
  boardCoordinates?: { x: number; y: number };
}

export interface PrecisionOverlayState {
  entryType: 'boundary-click' | 'seam-click' | 'chat' | 'pair-chat';
  mode: 'same-source' | 'cross-source';
  fragmentIds: string[];
  chainRealIndices: number[];
  anchorRect: DOMRect;
  activeBoundaryId: string | null;
}

export type PrecisionEntryHandle =
  | {
      type: 'same-source-boundary';
      leftFragmentId: string;
      rightFragmentId: string;
    }
  | {
      type: 'synthetic-seam';
      leftVisibleFragmentId: string;
      rightVisibleFragmentId: string;
      hiddenFragmentIds: string[];
    }
  | {
      type: 'cross-source-junction';
      leftFragmentId: string;
      rightFragmentId: string;
    };

export type PrecisionEditorScopeResult =
  | { ok: true; mode: 'same-source' | 'cross-source'; fragmentIds: string[] }
  | { ok: false; reason: 'too-many-fragments' | 'not-local-refinement' | 'invalid-handle' };

export type UndoActionType =
  | 'reorder'
  | 'boundary-resize'
  | 'replace-fragment'
  | 'exclude'
  | 'restore'
  | 'move-to-hold'
  | 'restore-from-hold'
  | 'precision-boundary'
  | 'hold-area-reposition';

export interface HoldPosition {
  x: number;
  y: number;
}

export interface UndoReorderOperation {
  kind: 'reorder';
  fragmentId: string;
  fromVisibleIndex: number;
  toVisibleIndex: number;
}

export interface UndoBoundaryOperation {
  kind: 'boundary-resize' | 'precision-boundary';
  leftFragmentId: string;
  rightFragmentId: string;
  deltaFrames: number;
}

export interface UndoReplaceFragmentOperation {
  kind: 'replace-fragment';
  sourceFragmentId: string;
  targetFragmentId: string;
  editIndex: number;
  sourceReservedIndexBefore: number;
  targetReservedIndexAfter: number;
}

export type UndoOperation =
  | UndoReorderOperation
  | UndoBoundaryOperation
  | UndoReplaceFragmentOperation;

export interface UndoEntry {
  type: UndoActionType;
  timestamp: number;
  prevEditFragments: Fragment[];
  prevReservedFragments: Fragment[];
  prevHoldAreaPositions: Record<string, HoldPosition>;
  label: string;
  op?: UndoOperation;
}

export type FragmentTileVariant = 'panorama' | 'edit' | 'reserved';

export type PrimaryInteractionState =
  | 'IDLE'
  | 'FOCUS_EXPANDED'
  | 'TIME_LENS'
  | 'BOUNDARY_DRAGGING'
  | 'PRECISION_OVERLAY'
  | 'PRECISION_DRAGGING'
  | 'HOLD_DRAGGING';

export interface ToastMessage {
  id: string;
  kind: 'info' | 'error';
  message: string;
}

export interface StableBoardState {
  editFragments: Fragment[];
  reservedFragments: Fragment[];
  holdAreaPositions: Record<string, HoldPosition>;
}

export interface StructuralBoundaryItem {
  type: 'boundary';
  leftFragment: Fragment;
  rightFragment: Fragment;
  leftRealIndex: number;
  rightRealIndex: number;
}

export interface StructuralSeamItem {
  type: 'seam';
  seam: SyntheticCollapsedSeam;
}

export interface StructuralFragmentItem {
  type: 'fragment';
  fragment: Fragment;
  realIndex: number;
  visibleIndex: number;
}

export type StructuralItem =
  | StructuralBoundaryItem
  | StructuralSeamItem
  | StructuralFragmentItem;
