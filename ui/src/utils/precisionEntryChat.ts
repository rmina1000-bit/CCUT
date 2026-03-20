import { getVisibleFragments } from './fragmentUtils';
import type { Fragment, PrecisionEntryHandle } from '../types/boundaryTypes';

export type PrecisionChatRequestResult =
  | { ok: true; entryType: 'chat' | 'pair-chat'; handle: PrecisionEntryHandle }
  | {
      ok: false;
      reason:
        | 'unsupported-intent'
        | 'needs-exactly-two-fragments'
        | 'invalid-fragment'
        | 'not-local-refinement';
    };

const PRECISION_KEYWORDS = [
  'precision',
  'boundary',
  'editor',
  'transition',
  'refine',
  'seam',
  'open',
  'adjust',
  '정밀',
  '경계',
  '비례바',
  '편집',
  '전환',
  '열어',
  '창'
];

export function isPrecisionChatInstruction(input: string) {
  const normalized = input.trim().toLowerCase();
  if (!normalized) {
    return false;
  }

  return PRECISION_KEYWORDS.some((keyword) => normalized.includes(keyword));
}

export function extractPrecisionChatFragmentIds(input: string, availableFragmentIds: string[]) {
  const availableMap = new Map(availableFragmentIds.map((fragmentId) => [fragmentId.toUpperCase(), fragmentId]));
  const matches = input.match(/\b[a-z]+\d+\b/gi) || [];
  const resolvedIds = matches
    .map((match) => availableMap.get(match.toUpperCase()) || null)
    .filter((fragmentId): fragmentId is string => !!fragmentId);

  return Array.from(new Set(resolvedIds));
}

function buildPrecisionHandleFromPairIds(
  pairIds: string[],
  editFragments: Fragment[]
): PrecisionEntryHandle | null {
  if (pairIds.length !== 2) {
    return null;
  }

  const pairEntries = pairIds
    .map((fragmentId) => ({
      fragment: editFragments.find((candidate) => candidate.fragment_id === fragmentId) || null,
      realIndex: editFragments.findIndex((candidate) => candidate.fragment_id === fragmentId)
    }))
    .filter((entry): entry is { fragment: Fragment; realIndex: number } => !!entry.fragment && entry.realIndex >= 0)
    .sort((left, right) => left.realIndex - right.realIndex);

  if (pairEntries.length !== 2) {
    return null;
  }

  const [leftEntry, rightEntry] = pairEntries;

  if (leftEntry.fragment.source_video === rightEntry.fragment.source_video) {
    return {
      type: 'same-source-boundary',
      leftFragmentId: leftEntry.fragment.fragment_id,
      rightFragmentId: rightEntry.fragment.fragment_id
    };
  }

  const visibleFragments = getVisibleFragments(editFragments);
  const leftVisibleIndex = visibleFragments.findIndex(
    (fragment) => fragment.fragment_id === leftEntry.fragment.fragment_id
  );
  const rightVisibleIndex = visibleFragments.findIndex(
    (fragment) => fragment.fragment_id === rightEntry.fragment.fragment_id
  );

  if (
    leftVisibleIndex === -1 ||
    rightVisibleIndex === -1 ||
    Math.abs(rightVisibleIndex - leftVisibleIndex) !== 1
  ) {
    return null;
  }

  return {
    type: 'cross-source-junction',
    leftFragmentId: leftEntry.fragment.fragment_id,
    rightFragmentId: rightEntry.fragment.fragment_id
  };
}

export function resolvePrecisionChatRequest(
  input: string,
  pairSelectionIds: string[],
  availableFragmentIds: string[],
  editFragments: Fragment[]
): PrecisionChatRequestResult {
  if (!isPrecisionChatInstruction(input)) {
    return { ok: false, reason: 'unsupported-intent' };
  }

  const explicitFragmentIds = extractPrecisionChatFragmentIds(input, availableFragmentIds);
  if (explicitFragmentIds.length > 2) {
    return { ok: false, reason: 'needs-exactly-two-fragments' };
  }

  if (explicitFragmentIds.length === 2) {
    const handle = buildPrecisionHandleFromPairIds(explicitFragmentIds, editFragments);
    if (!handle) {
      return { ok: false, reason: 'not-local-refinement' };
    }
    return {
      ok: true,
      entryType: 'chat',
      handle
    };
  }

  if (explicitFragmentIds.length === 1) {
    return { ok: false, reason: 'needs-exactly-two-fragments' };
  }

  if (pairSelectionIds.length !== 2) {
    return { ok: false, reason: 'needs-exactly-two-fragments' };
  }

  const handle = buildPrecisionHandleFromPairIds(pairSelectionIds, editFragments);
  if (!handle) {
    return { ok: false, reason: 'not-local-refinement' };
  }

  return {
    ok: true,
    entryType: 'pair-chat',
    handle
  };
}
