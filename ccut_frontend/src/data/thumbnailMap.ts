/**
 * Get the thumbnail image URL for a fragment.
 * Priority: real extracted thumbnail > remote thumbnail > empty string
 */

export const sourceThumbnails: Record<string, string> = {};

export function getFragmentThumbnail(
  fragmentId: string,
  sourceVideo: string,
  realThumbnailUrl?: string
): string {
  // 1. If we have a real provided URL (from L1 scanner/backend), use it.
  if (realThumbnailUrl) {
    // If it's a relative path from DB like 'thumbnails/L1_...', prepend API host
    if (realThumbnailUrl.startsWith('thumbnails/')) {
      return `/static/${realThumbnailUrl}`;
    }
    return realThumbnailUrl;
  }

  // 2. Otherwise return empty. UI (FragmentTile) will use Hue-based background as fallback.
  return "";
}
