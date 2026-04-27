export type SelectionState = "S" | "N";
export type FragmentStatus = "analyzed" | "pending" | "candidate" | "committed" | "removed";

export interface Fragment {
  fragment_uid: string;
  fragment_id: string;
  root_fragment_uid?: string;
  parent_fragment_uid?: string;
  secondary_parent_uid?: string;
  derivedFrom?: string;
  display_id?: string;
  source_video: string;
  start_frame: number;
  end_frame: number;
  duration: number;
  selection_state: SelectionState;
  status: FragmentStatus;
  intelligence?: {
    hook_score: number;
    role: string;
    description: string;
  };
  thumbnail?: {
    thumbnail_url: string;
  };
  thumbnail_hue?: number;
  excluded?: boolean;
}



export const allFragments: Record<string, Fragment[]> = {};

export const initialEditFragments: Fragment[] = [];
export const initialReservedFragments: Fragment[] = [];

export function formatDuration(frames: number, fps: number = 30): string {
  const seconds = frames / fps;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(0);
  return `${m}:${s.padStart(2, "0")}`;
}
