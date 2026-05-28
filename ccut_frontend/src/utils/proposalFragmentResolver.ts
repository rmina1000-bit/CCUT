import { Fragment } from "@/data/fragmentData";
import { Proposal } from "@/proposal/proposalTypes";

// [STEP 10-I.5.27-E7-M2] Debug Log Guard
const DEBUG_PROPOSAL_RESOLVER =
  import.meta.env.DEV && localStorage.getItem("CCUT_DEBUG_PROPOSAL_RESOLVER") === "1";

/**
 * [STEP 10-I.2] Proposal Fragment Resolver
 * Proposal ID(또는 sequence)를 실제 Fragment 객체 배열로 해석합니다.
 */

export interface ResolvedFragment extends Fragment {
  stable_key: string;
}

export interface ResolverDiagnostics {
  proposalCount: number;
  matchedCount: number;
  exactMatched: number;
  timeFallbackMatched: number;
  singleFallbackMatched: number;
  missingIds: string[];
}

export interface ResolverResult {
  resolvedFragments: ResolvedFragment[];
  diagnostics: ResolverDiagnostics;
}

/**
 * 1. Alias 수집
 * 조각의 다양한 ID 필드를 수집하여 매칭에 활용합니다.
 */
export const collectFragmentAliases = (f: any): string[] => {
  const ids = new Set<string>();
  if (f.fragment_id) ids.add(f.fragment_id);
  if (f.fragment_uid) ids.add(f.fragment_uid);
  if (f.id) ids.add(f.id);
  if (f.uid) ids.add(f.uid);
  if (f.display_id) ids.add(f.display_id);
  if (f.original_id) ids.add(f.original_id);
  if (f.source_fragment_id) ids.add(f.source_fragment_id);
  if (f.root_fragment_uid) ids.add(f.root_fragment_uid);
  if (f.parent_fragment_uid) ids.add(f.parent_fragment_uid);
  if (f.derivedFrom) ids.add(f.derivedFrom);
  if (f.semantic?.id) ids.add(f.semantic.id);
  if (f.semantic?.fragment_id) ids.add(f.semantic.fragment_id);
  if (f.structural?.source_fragment_id) ids.add(f.structural.source_fragment_id);
  if (f.intelligence?.semantic_fragment_id) ids.add(f.intelligence.semantic_fragment_id);
  if (f.intelligence?.source_fragment_id) ids.add(f.intelligence.source_fragment_id);
  return Array.from(ids);
};

/**
 * 2. 시간 범위 추출
 */
export const getFragmentTimeRange = (f: any): { start: number; end: number } => {
  const fps = 30;
  // [STEP 10-I.5.5] Strict priority matching mapFragments in Index.tsx
  const start = f.start_sec ?? f.start ?? f.start_time ?? f.semantic?.start_sec ?? f.structural?.start_sec ?? (f.start_frame / fps) ?? 0;
  const end = f.end_sec ?? f.end ?? f.end_time ?? f.semantic?.end_sec ?? f.structural?.end_sec ?? (start + (f.duration_sec || f.structural?.duration || f.duration || 5));
  return { start, end };
};

/**
 * 3. Stable Key 생성 규칙
 * proposalId + index + unique_id 조합
 */
export const makeStableFragmentKey = (
  proposalId: string,
  index: number,
  fragment: Fragment
): string => {
  const uid = fragment.fragment_uid || fragment.fragment_id || (fragment as any).display_id || "unknown";
  return `${proposalId}_${index}_${uid}`;
};

/**
 * 4. 중복 제거
 */
export const dedupeResolvedFragments = (resolved: ResolvedFragment[]): ResolvedFragment[] => {
  // 현재는 순서가 중요하므로 중복 제거 로직은 필요시 적용 (동일 위치 동일 조각 방지 등)
  return resolved; 
};

/**
 * 5. 메인 Resolver 함수
 */
export const resolveProposalFragments = (
  proposal: Proposal | null,
  editFragments: Fragment[]
): ResolverResult => {
  const diagnostics: ResolverDiagnostics = {
    proposalCount: 0,
    matchedCount: 0,
    exactMatched: 0,
    timeFallbackMatched: 0,
    singleFallbackMatched: 0,
    missingIds: []
  };

  if (!proposal || !editFragments.length) {
    return { resolvedFragments: [], diagnostics };
  }

  const proposalId = proposal.id || (proposal as any).proposal_id || "unknown";
  const proposalFragIds = (proposal as any).key_fragments || proposal.sequence || [];
  const aliases = (proposal as any).resolved_aliases || [];

  diagnostics.proposalCount = proposalFragIds.length;

  const resolvedFragments: ResolvedFragment[] = [];

  proposalFragIds.forEach((id: string, idx: number) => {
    const alias = aliases.find((a: any) => a.proposal_fragment_id === id || a.source_fragment_id === id);
    
    // 1. Exact ID match
    let found = editFragments.find((f) => {
      const fAliases = collectFragmentAliases(f);
      return fAliases.includes(id);
    });

    if (found) {
      diagnostics.exactMatched++;
    } else if (alias) {
      // 2. Time range fallback
      const pStart = alias.start_sec;
      const pEnd = alias.end_sec;
      
      found = editFragments.find((f) => {
        const { start, end } = getFragmentTimeRange(f);
        return Math.abs(start - pStart) < 0.5 && Math.abs(end - pEnd) < 0.5;
      });
      if (found) diagnostics.timeFallbackMatched++;
    }

    // 3. Single fallback
    if (!found && editFragments.length === 1 && proposalFragIds.length === 1) {
      found = editFragments[0];
      if (found) diagnostics.singleFallbackMatched++;
    }

    if (found) {
      // [STEP 10-I.5.2] Semantic/Proposal 기반 정확한 시간 적용
      // alias에 기록된 start_sec/end_sec이 있으면 우선 적용하여 30초 고정 문제를 해결함.
      // 단, 사용자가 PBE 편집 또는 수동 변경 등을 가한 경우 found의 start_frame / end_frame이 변경되어 
      // 존재하므로, 이를 최우선하여 사용자가 조작한 범위를 보존합니다.
      const hasValidFrames = typeof found.start_frame === "number" && typeof found.end_frame === "number";
      const pStart = hasValidFrames ? (found.start_frame / 30) : (alias?.start_sec !== undefined ? alias.start_sec : 0);
      const pEnd = hasValidFrames ? (found.end_frame / 30) : (alias?.end_sec !== undefined ? alias.end_sec : (pStart + 5));
      
      resolvedFragments.push({
        ...found,
        start_frame: Math.round(pStart * 30),
        end_frame: Math.round(pEnd * 30),
        duration: Math.round((pEnd - pStart) * 30),
        stable_key: makeStableFragmentKey(proposalId, idx, found)
      });
      diagnostics.matchedCount++;
    } else {
      diagnostics.missingIds.push(id);
    }
  });

  const result = {
    resolvedFragments: dedupeResolvedFragments(resolvedFragments),
    diagnostics
  };

  // [STEP 10-I.5.12] Diagnostic Logging
  if (DEBUG_PROPOSAL_RESOLVER && editFragments.length > 0) {
    console.log("[proposalResolver] Summary:");
    console.log(`  - Key Count: ${diagnostics.proposalCount}`);
    console.log(`  - Edit Count: ${editFragments.length}`);
    console.log(`  - Exact: ${diagnostics.exactMatched}`);
    console.log(`  - Time Fallback: ${diagnostics.timeFallbackMatched}`);
    console.log(`  - Missing: ${diagnostics.missingIds.length}`);
    if (diagnostics.missingIds.length > 0) {
      console.log(`  - Unmatched Ids (first 10):`, diagnostics.missingIds.slice(0, 10));
    }
    if (aliases.length > 0) {
      console.log(`  - Aliases Sample (first 3):`, aliases.slice(0, 3));
    }
  }

  return result;
};
