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
  const formData = new FormData();
  formData.append('file', file);

  // Derive source label from filename (strip extension)
  const sourceLabel = file.name.replace(/\.[^.]+$/, '') || 'upload';

  const res = await fetch(`${API_BASE}/generate-fragments`, {
    method: 'POST',
    body: formData,
    signal: AbortSignal.timeout(UPLOAD_TIMEOUT_MS),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Upload failed (${res.status}): ${detail}`);
  }

  const data: { fragments: Array<{ id: string; start: number; end: number; duration: number }>; count: number; fps?: number } =
    await res.json();

  // Signal completion if progress callback provided
  onProgress?.(100);

  const fps = data.fps ?? 30;
  return mapRawFragments(data.fragments, sourceLabel, fps);
}
