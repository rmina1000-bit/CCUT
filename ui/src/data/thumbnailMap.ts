import { buildInitialBoardState } from './fragmentData';

export const thumbnailMap = Object.fromEntries(
  [...buildInitialBoardState().editFragments, ...buildInitialBoardState().reservedFragments].map((fragment) => [
    fragment.fragment_id,
    fragment.thumbnail?.thumbnail_url || ''
  ])
);

export function getFragmentThumbnail(fragmentId: string): string | null {
  return thumbnailMap[fragmentId] || null;
}
