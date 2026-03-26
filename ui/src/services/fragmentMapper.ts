/**
 * fragmentMapper.ts
 * -----------------
 * Maps backend fragment_api.py response to frontend Fragment type.
 *
 * Backend schema: { id, start, end, duration }
 * Frontend type:  { fragment_id, source_video, start_frame, end_frame, duration, thumbnail_hue, intelligence }
 */

import type { Fragment } from '../types/boundaryTypes';

const DEFAULT_FPS = 30;
const DEFAULT_HUE = 210;
const DEFAULT_INTELLIGENCE = {
  narrative: 0.5,
  emotional: 0.5,
  action: 0.5,
  dialogue: 0.5,
  hook: 0.5,
  callback: 0.5,
  confidence: 0.5,
};

interface RawFragment {
  id: string;
  start: number;
  end: number;
  duration: number;
  editStack?: unknown[];
}

/**
 * Convert a single backend fragment to the frontend Fragment shape.
 *
 * @param raw        - Fragment dict from /generate-fragments response
 * @param sourceLabel - Source video label (filename-derived or default)
 * @param fps        - Frames per second (from server response or default 30)
 * @param hue        - Thumbnail hue override
 */
export function mapRawToFragment(
  raw: RawFragment,
  sourceLabel: string,
  fps: number = DEFAULT_FPS,
  hue: number = DEFAULT_HUE,
): Fragment {
  return {
    fragment_id: raw.id,
    source_video: sourceLabel,
    start_frame: Math.round(raw.start * fps),
    end_frame: Math.round(raw.end * fps),
    duration: Math.round(raw.duration * fps),
    thumbnail_hue: hue,
    excluded: false,
    intelligence: { ...DEFAULT_INTELLIGENCE },
  };
}

/**
 * Convert an array of backend fragments.
 */
export function mapRawFragments(
  rawFragments: RawFragment[],
  sourceLabel: string,
  fps?: number,
  hue?: number,
): Fragment[] {
  return rawFragments.map((raw) => mapRawToFragment(raw, sourceLabel, fps, hue));
}
