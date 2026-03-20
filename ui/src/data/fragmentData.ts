import { ensureFragmentThumbnail } from '../services/thumbnailService';
import type { Fragment, HoldPosition, SourceVideo } from '../types/boundaryTypes';

const SOURCE_HUES: Record<string, number> = {
  A: 30,
  B: 200,
  C: 120,
  D: 0,
  E: 280,
  F: 50,
  G: 320
};

const sourceVideos: SourceVideo[] = [
  { id: 'A', label: 'A', totalFrames: 720, fps: 24, description: 'Opening conversation beats and establishing shots.' },
  { id: 'B', label: 'B', totalFrames: 840, fps: 24, description: 'Secondary reactions and supporting cutaways.' },
  { id: 'C', label: 'C', totalFrames: 900, fps: 24, description: 'Interview core narrative with alternate trims.' },
  { id: 'D', label: 'D', totalFrames: 780, fps: 24, description: 'Detail inserts and pacing control moments.' },
  { id: 'E', label: 'E', totalFrames: 840, fps: 24, description: 'Closing callback and end-card lead-in.' },
  { id: 'F', label: 'F', totalFrames: 660, fps: 24, description: 'Reserved b-roll options.' },
  { id: 'G', label: 'G', totalFrames: 620, fps: 24, description: 'Reserved alternate reaction shots.' }
];

function intelligence(base: number) {
  return {
    narrative: Math.min(0.96, 0.48 + base * 0.06),
    emotional: Math.min(0.95, 0.4 + base * 0.05),
    action: Math.min(0.95, 0.3 + base * 0.04),
    dialogue: Math.min(0.95, 0.46 + base * 0.03),
    hook: Math.min(0.95, 0.34 + base * 0.04),
    callback: Math.min(0.95, 0.28 + base * 0.05),
    confidence: Math.min(0.98, 0.62 + base * 0.03)
  };
}

function makeFragment(
  fragmentId: string,
  source: string,
  start: number,
  duration: number,
  excluded = false
): Fragment {
  return ensureFragmentThumbnail({
    fragment_id: fragmentId,
    source_video: source,
    start_frame: start,
    end_frame: start + duration,
    duration,
    thumbnail_hue: SOURCE_HUES[source],
    excluded,
    intelligence: intelligence(Number(fragmentId.replace(/\D/g, '')) || 1)
  });
}

const initialEditFragments: Fragment[] = [
  makeFragment('A2', 'A', 78, 68),
  makeFragment('A3', 'A', 146, 56),
  makeFragment('B1', 'B', 32, 74),
  makeFragment('C1', 'C', 64, 68),
  makeFragment('C2', 'C', 132, 34, true),
  makeFragment('C3', 'C', 166, 72),
  makeFragment('D1', 'D', 96, 58),
  makeFragment('D2', 'D', 154, 28, true),
  makeFragment('D3', 'D', 182, 26, true),
  makeFragment('D4', 'D', 208, 64),
  makeFragment('E1', 'E', 88, 82)
];

const initialReservedFragments: Fragment[] = [
  makeFragment('F1', 'F', 120, 60),
  makeFragment('G2', 'G', 210, 54)
];

const initialHoldAreaPositions: Record<string, HoldPosition> = {
  F1: { x: 24, y: 24 },
  G2: { x: 148, y: 48 }
};

export function buildInitialBoardState() {
  return {
    sourceVideos,
    editFragments: initialEditFragments,
    reservedFragments: initialReservedFragments,
    holdAreaPositions: initialHoldAreaPositions
  };
}
