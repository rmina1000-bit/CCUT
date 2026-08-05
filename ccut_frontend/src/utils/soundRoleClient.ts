export type SoundRole = "dialogue" | "background" | "silence" | "unknown";

export const SOUND_ROLES: SoundRole[] = [
  "dialogue",
  "background",
  "silence",
  "unknown",
];

export interface SoundRoleItem {
  ordinal: number;
  timeline_item_id: string;
  fragment_id: string;
  source_id: string | null;
  anchor_start_ms: number | null;
  anchor_end_ms: number | null;
  coord_source: string | null;
  detected_role: SoundRole;
  effective_role: SoundRole;
  reason: string;
  evidence: {
    transcript: {
      available: boolean;
      word_count: number | null;
      segment_count: number | null;
      average_word_probability?: number | null;
    };
    silero: { available: boolean; speech_ratio: number | null };
    audio_energy: { available: boolean; value: number | null };
    silence: { available: boolean; detected: boolean };
  };
  overridden: boolean;
  revision: number | null;
  editable: boolean;
}

interface SoundRoleListResponse {
  ok: boolean;
  program_id: string;
  sequence_source: string;
  item_count: number;
  storage_ready: boolean;
  material_missing_count: number;
  items: SoundRoleItem[];
  error?: string;
  message?: string;
}

interface SoundRoleSaveResponse {
  ok: boolean;
  timeline_item_id: string;
  fragment_id: string;
  detected_role: SoundRole;
  effective_role: SoundRole;
  overridden: boolean;
  revision: number;
  error?: string;
  message?: string;
}

async function readJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | null;
  if (!response.ok || !body || (body as { ok?: boolean }).ok !== true) {
    const detail = body as { error?: string; message?: string } | null;
    throw new Error(detail?.error || detail?.message || `HTTP_${response.status}`);
  }
  return body;
}

export async function fetchSoundRoles(programId: string): Promise<SoundRoleListResponse> {
  const response = await fetch(`/api/sound-role/${encodeURIComponent(programId)}`);
  return readJson<SoundRoleListResponse>(response);
}

export async function saveSoundRole(
  programId: string,
  item: SoundRoleItem,
  role: SoundRole,
): Promise<SoundRoleSaveResponse> {
  const response = await fetch(`/api/sound-role/${encodeURIComponent(programId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      timeline_item_id: item.timeline_item_id,
      fragment_id: item.fragment_id,
      role,
      expected_revision: item.revision,
    }),
  });
  return readJson<SoundRoleSaveResponse>(response);
}
