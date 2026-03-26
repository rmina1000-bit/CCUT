/**
 * proposalService.ts
 * ------------------
 * Requests A/B proposals from the backend, with a deterministic fallback
 * when the backend is unavailable.
 *
 * Backend: POST /generate-proposals  → { A: [id,...], B: [id,...] }
 * Frontend: Proposal[] (enriched with title, description, editSequence)
 */

import type { Fragment, Proposal } from '../types/boundaryTypes';

const API_BASE = 'http://localhost:8000';
const PROPOSAL_TIMEOUT_MS = 30_000;

/**
 * Request A/B proposals from the backend.
 * Falls back to a deterministic client-side generator on failure.
 */
export async function generateProposals(fragments: Fragment[]): Promise<[Proposal, Proposal]> {
  try {
    // Convert to backend schema: { id, start, end, duration }
    const backendFragments = fragments.map((f) => ({
      id: f.fragment_id,
      start: f.start_frame / 30,
      end: f.end_frame / 30,
      duration: f.duration / 30,
    }));

    const res = await fetch(`${API_BASE}/generate-proposals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fragments: backendFragments }),
      signal: AbortSignal.timeout(PROPOSAL_TIMEOUT_MS),
    });

    if (!res.ok) throw new Error(`Proposal generation failed: ${res.status}`);

    const data: { A: string[]; B: string[] } = await res.json();

    return [
      buildProposal('A', data.A, fragments),
      buildProposal('B', data.B, fragments),
    ];
  } catch {
    // TODO: remove when backend proposals endpoint is ready
    return generateFallbackProposals(fragments);
  }
}

function buildProposal(
  label: 'A' | 'B',
  fragmentIds: string[],
  allFragments: Fragment[],
): Proposal {
  const fragmentMap = new Map(allFragments.map((f) => [f.fragment_id, f]));
  const editSequence = fragmentIds
    .map((id) => fragmentMap.get(id))
    .filter((f): f is Fragment => !!f);

  const isA = label === 'A';
  return {
    id: label,
    label,
    title: isA ? '내러티브 중심' : '비주얼 중심',
    description: isA
      ? `${editSequence.length}개 조각 — 안정적인 흐름의 편집`
      : `${editSequence.length}개 조각 — 역동적인 구성의 편집`,
    thumbnailHue: isA ? 211 : 30,
    fragmentIds,
    editSequence,
  };
}

// TODO: remove when backend proposals endpoint is ready
function generateFallbackProposals(fragments: Fragment[]): [Proposal, Proposal] {
  // Proposal A: original order, skip short fragments
  const aFragments = fragments.filter((f) => f.duration > 30);
  const aIds = (aFragments.length > 0 ? aFragments : [fragments[0]]).map((f) => f.fragment_id);

  // Proposal B: sort by duration descending, interleave top/bottom halves
  const sorted = [...fragments].sort((a, b) => b.duration - a.duration);
  const mid = Math.max(1, Math.floor(sorted.length / 2));
  const top = sorted.slice(0, mid);
  const bot = sorted.slice(mid);
  const bIds: string[] = [];
  for (let i = 0; i < Math.max(top.length, bot.length); i++) {
    if (i < top.length) bIds.push(top[i].fragment_id);
    if (i < bot.length) bIds.push(bot[i].fragment_id);
  }

  return [
    buildProposal('A', aIds, fragments),
    buildProposal('B', bIds, fragments),
  ];
}
