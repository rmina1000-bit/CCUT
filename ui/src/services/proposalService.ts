/**
 * proposalService.ts
 * ------------------
 * Backend API calls for fragment generation and A/B proposal pipeline.
 *
 * Flow: uploadVideo() → generateProposals() → Proposal[]
 */

import type { Fragment } from '../types/boundaryTypes';

const API_BASE = 'http://localhost:8000';

/* ── Types ─────────────────────────────────────────────────── */

export interface BackendFragment {
  id: string;
  start: number;
  end: number;
  duration: number;
  editStack: unknown[];
}

export interface Proposal {
  label: 'A' | 'B';
  editSequence: Fragment[];
  description: string;
}

/* ── Fragment Generation ───────────────────────────────────── */

export async function uploadAndGenerateFragments(
  file: File,
): Promise<Fragment[]> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/generate-fragments`, {
    method: 'POST',
    body: formData,
    signal: AbortSignal.timeout(120_000),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Fragment generation failed (${res.status}): ${text}`);
  }

  const data = await res.json();
  const rawFragments: BackendFragment[] = data.fragments ?? [];

  console.log('[FRAG] Backend returned', rawFragments.length, 'fragments');

  return rawFragments.map((f, i) => toUIFragment(f, i));
}

/* ── Proposal Generation ───────────────────────────────────── */

export async function generateProposals(
  fragments: Fragment[],
): Promise<Proposal[]> {
  const backendFragments = fragments.map((f) => ({
    id: f.fragment_id,
    start: f.start_frame / 30,
    end: f.end_frame / 30,
    duration: f.duration,
    editStack: [],
  }));

  try {
    const res = await fetch(`${API_BASE}/generate-proposals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fragments: backendFragments }),
      signal: AbortSignal.timeout(30_000),
    });

    if (!res.ok) throw new Error(`Proposals failed: ${res.status}`);

    const raw = await res.json();
    console.log('[PROPOSAL] Backend response:', JSON.stringify(raw));

    return parseProposals(raw, fragments);
  } catch (err) {
    console.warn('[PROPOSAL] Backend failed, using fallback:', err);
    return generateFallbackProposals(fragments);
  }
}

/* ── Parse backend {A: [...], B: [...]} response ───────────── */

function parseProposals(
  raw: { A?: string[]; B?: string[] },
  fragments: Fragment[],
): Proposal[] {
  const fragMap = new Map(fragments.map((f) => [f.fragment_id, f]));

  const toSequence = (ids: string[]) =>
    ids.map((id) => fragMap.get(id)).filter(Boolean) as Fragment[];

  return [
    {
      label: 'A',
      editSequence: toSequence(raw.A ?? []),
      description: '내러티브 중심 — 원본 순서 기반 큐레이션',
    },
    {
      label: 'B',
      editSequence: toSequence(raw.B ?? []),
      description: '비주얼 중심 — 듀레이션 가중 인터리브',
    },
  ];
}

/* ── Fallback: client-side A/B when backend unavailable ───── */

function generateFallbackProposals(fragments: Fragment[]): Proposal[] {
  if (fragments.length === 0) {
    return [
      { label: 'A', editSequence: [], description: '조각 없음' },
      { label: 'B', editSequence: [], description: '조각 없음' },
    ];
  }

  // A: original order
  const a = [...fragments];

  // B: reversed order (simple differentiation)
  const b = [...fragments].reverse();

  // Ensure A != B by swapping last two if same
  if (
    a.length >= 2 &&
    a.map((f) => f.fragment_id).join() === b.map((f) => f.fragment_id).join()
  ) {
    const tmp = b[b.length - 1];
    b[b.length - 1] = b[b.length - 2];
    b[b.length - 2] = tmp;
  }

  return [
    { label: 'A', editSequence: a, description: '내러티브 중심 (fallback)' },
    { label: 'B', editSequence: b, description: '비주얼 중심 (fallback)' },
  ];
}

/* ── Backend fragment → UI Fragment conversion ─────────────── */

const SOURCE_HUES: Record<string, number> = {
  A: 30, B: 200, C: 120, D: 0, E: 280, F: 50, G: 320,
};

function toUIFragment(bf: BackendFragment, index: number): Fragment {
  const sourceKey = String.fromCharCode(65 + (index % 7)); // A~G rotation
  const fps = 30;
  return {
    fragment_id: bf.id,
    source_video: sourceKey,
    start_frame: Math.round(bf.start * fps),
    end_frame: Math.round(bf.end * fps),
    duration: Math.round(bf.duration * fps),
    thumbnail_hue: SOURCE_HUES[sourceKey] ?? 200,
    intelligence: {
      narrative: 0.6 + Math.random() * 0.2,
      emotional: 0.5 + Math.random() * 0.2,
      action: 0.4 + Math.random() * 0.2,
      dialogue: 0.5 + Math.random() * 0.15,
      hook: 0.4 + Math.random() * 0.2,
      callback: 0.3 + Math.random() * 0.2,
      confidence: 0.7 + Math.random() * 0.15,
    },
  };
}
