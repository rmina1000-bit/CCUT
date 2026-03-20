import type { Fragment } from '../types/boundaryTypes';

const FALLBACK_STOPS = [50, 45, 55, 35, 65, 25, 75];

function buildThumbnailSvg(fragment: Fragment): string {
  const hue = fragment.thumbnail_hue;
  const accentHue = (hue + 22) % 360;
  const mid = Math.round(fragment.start_frame + fragment.duration / 2);
  const label = encodeURIComponent(fragment.fragment_id);
  const duration = encodeURIComponent(`${fragment.duration}f`);
  const stamp = encodeURIComponent(`@${mid}`);

  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180" preserveAspectRatio="none">`,
    `<defs>`,
    `<linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">`,
    `<stop offset="0%" stop-color="hsl(${hue} 58% 28%)"/>`,
    `<stop offset="100%" stop-color="hsl(${accentHue} 42% 16%)"/>`,
    `</linearGradient>`,
    `<linearGradient id="shine" x1="0%" y1="0%" x2="100%" y2="0%">`,
    `<stop offset="0%" stop-color="hsla(0 0% 100% / 0.08)"/>`,
    `<stop offset="100%" stop-color="hsla(0 0% 100% / 0)"/>`,
    `</linearGradient>`,
    `</defs>`,
    `<rect width="320" height="180" fill="url(#g)"/>`,
    `<rect x="0" y="0" width="320" height="180" fill="url(#shine)"/>`,
    `<rect x="18" y="18" width="284" height="144" rx="18" fill="hsla(228 12% 10% / 0.18)" stroke="hsla(0 0% 100% / 0.14)"/>`,
    `<path d="M20 120 Q90 55 150 96 T300 78" fill="none" stroke="hsla(0 0% 100% / 0.18)" stroke-width="8" stroke-linecap="round"/>`,
    `<path d="M12 136 Q96 100 160 118 T310 110" fill="none" stroke="hsla(0 0% 100% / 0.11)" stroke-width="14" stroke-linecap="round"/>`,
    `<text x="28" y="44" fill="rgba(255,255,255,0.92)" font-size="22" font-family="Inter,system-ui,sans-serif" font-weight="700">${label}</text>`,
    `<text x="28" y="154" fill="rgba(255,255,255,0.84)" font-size="14" font-family="Inter,system-ui,sans-serif">${duration}</text>`,
    `<text x="250" y="154" fill="rgba(255,255,255,0.7)" font-size="12" font-family="Inter,system-ui,sans-serif">${stamp}</text>`,
    `</svg>`
  ].join('');
}

export function createFragmentThumbnail(fragment: Fragment) {
  const thumbnailTime = FALLBACK_STOPS[0];
  return {
    thumbnail_url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(buildThumbnailSvg(fragment))}`,
    thumbnail_time: thumbnailTime,
    extraction_version: 1,
    last_updated: Date.now()
  };
}

export function ensureFragmentThumbnail(fragment: Fragment): Fragment {
  if (fragment.thumbnail?.thumbnail_url) {
    return fragment;
  }

  return {
    ...fragment,
    thumbnail: createFragmentThumbnail(fragment)
  };
}

export function refreshFragmentThumbnailIfNeeded(next: Fragment, previous?: Fragment): Fragment {
  const nextCenter = next.start_frame + next.duration / 2;
  const prevCenter = previous ? previous.start_frame + previous.duration / 2 : nextCenter;
  const shiftRatio = previous ? Math.abs(nextCenter - prevCenter) / Math.max(previous.duration, 1) : 1;

  if (!next.thumbnail?.thumbnail_url || shiftRatio > 0.18) {
    return {
      ...next,
      thumbnail: createFragmentThumbnail(next)
    };
  }

  return next;
}

export function getFallbackThumbnail(fragment: Fragment): string {
  return createFragmentThumbnail(fragment).thumbnail_url || '';
}
