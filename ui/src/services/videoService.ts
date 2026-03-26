/**
 * videoService.ts
 * ---------------
 * Uploads a video file to the backend and returns parsed Fragment[].
 *
 * Flow: File → FormData → POST /generate-fragments → mapRawFragments → Fragment[]
 */

import type { Fragment } from '../types/boundaryTypes';
import { mapRawFragments } from './fragmentMapper';

const API_BASE = 'http://localhost:8000';
const UPLOAD_TIMEOUT_MS = 60_000;

/**
 * Upload a video file and receive generated fragments.
 *
 * @param file       - Video file selected by user
 * @param onProgress - Optional progress callback (0–100). Only works with XHR fallback.
 * @returns Parsed Fragment[] ready for UI consumption
 */
export async function uploadVideo(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<Fragment[]> {
  console.log('[D4] uploadVideo 호출:', file.name, file.size + ' bytes');
  const formData = new FormData();
  formData.append('file', file);

  // Derive source label from filename (strip extension)
  const sourceLabel = file.name.replace(/\.[^.]+$/, '') || 'upload';

  console.log('[D4] fetch 시작:', `${API_BASE}/generate-fragments`);
  const res = await fetch(`${API_BASE}/generate-fragments`, {
    method: 'POST',
    body: formData,
    signal: AbortSignal.timeout(UPLOAD_TIMEOUT_MS),
  });

  console.log('[D4] 응답 status:', res.status, res.statusText);
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Upload failed (${res.status}): ${detail}`);
  }

  const data: { fragments: Array<{ id: string; start: number; end: number; duration: number }>; count: number; fps?: number } =
    await res.json();

  console.log('[D4] raw 응답:', JSON.stringify(data).slice(0, 300));

  // Signal completion if progress callback provided
  onProgress?.(100);

  const fps = data.fps ?? 30;
  const fragments = mapRawFragments(data.fragments, sourceLabel, fps);
  console.log('[D4] 매핑된 Fragment 수:', fragments.length, '첫 번째:', fragments[0]?.fragment_id);
  return fragments;
}
