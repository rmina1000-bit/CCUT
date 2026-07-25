/**
 * [EDIT-CONTRACT-B0 IMPL-2b] 프론트 클라이언트 — 게이트 조회·edit-state API·사용본 ID·상태→조각 적용.
 * 게이트 OFF: 이 모듈의 쓰기 함수는 호출되지 않아야 하며(호출부 분기), 호출돼도 서버가 403으로 거부한다.
 */
import { toMs, type MsRange } from "./editContract";

export interface EditStateRow {
  edit_state_id: string;
  program_id: string;
  timeline_item_id: string;
  source_id: string;
  parent_fragment_id: string | null;
  carried_from_item_id: string | null;
  occurrence: number;
  anchor_start_ms: number;
  anchor_end_ms: number;
  trim_start_ms: number;
  trim_end_ms: number;
  excluded_ranges: MsRange[];
  removed: boolean;
  revision: number;
  last_origin: string | null;
  spans: MsRange[];
  ed_ids: string[];
}

let gateCache: boolean | null = null;

/** EDIT_CONTRACT_V2 게이트 — 1회 조회 캐시. 실패 시 false(OFF)로 안전 강하. */
export async function fetchGateEnabled(): Promise<boolean> {
  if (gateCache !== null) return gateCache;
  try {
    const res = await fetch("/api/edit-state/gate");
    const data = await res.json();
    gateCache = data?.enabled === true;
  } catch {
    gateCache = false;
  }
  return gateCache;
}

export async function fetchEditStates(programId: string): Promise<EditStateRow[]> {
  try {
    const res = await fetch(`/api/edit-state/${encodeURIComponent(programId)}`);
    const data = await res.json();
    return Array.isArray(data?.states) ? data.states : [];
  } catch {
    return [];
  }
}

export interface EditStatePost {
  program_id: string;
  timeline_item_id: string;
  source_id: string;
  anchor_start_ms: number;
  anchor_end_ms: number;
  trim_start_ms: number;
  trim_end_ms: number;
  excluded_ranges: MsRange[];
  removed?: boolean;
  revision?: number;
  parent_fragment_id?: string;
  occurrence?: number;
  command_type: "TRIM" | "EXCLUDE_RANGE" | "REMOVE" | "RESTORE";
  origin: "PBE" | "TEXT_EDITOR" | "NATURAL_LANGUAGE";
}

export async function postEditState(payload: EditStatePost): Promise<{ ok: boolean; [k: string]: unknown }> {
  const res = await fetch("/api/edit-state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await res.json();
}

/** djb2 해시 hex 6자리 — B0 시대 결정론 사용본 ID의 프로그램부. */
function hash6(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h.toString(16).padStart(6, "0").slice(-6);
}

/**
 * 결정론 발급식: ITEM_{program해시6}_{fid}_{occ}
 *
 * [STORY-LAYER-01 A-1] 제안키를 뺐다 — 스토리는 program 단위 하나이므로 사용본 ID도
 * 제안과 무관하다. 대사·경계 편집이 A/B 어디서 일어나도 같은 스토리에 쌓인다.
 * 구판(…_{proposal_id}_…)은 A↔B 전환마다 키가 갈려 edit_state 행이 고아가 됐다(NA/B 분열).
 * 서버 발급식(ledger_r0.py `item_id`)과 반드시 동일해야 한다.
 */
export function timelineItemIdFor(programId: string, fid: string, occ = 0): string {
  return `ITEM_${hash6(programId)}_${fid}_${occ}`;
}

/** PBE 적용 payload(segments 초 단위) → excluded_ranges ms (생존 구간 사이 간극). */
export function segmentsToExcludedMs(
  segments: Array<{ startSec: number; endSec: number }>
): { trim: MsRange; excluded: MsRange[] } {
  const spans = segments
    .map((s) => [toMs(s.startSec), toMs(s.endSec)] as MsRange)
    .sort((a, b) => a[0] - b[0]);
  const trim: MsRange = [spans[0][0], spans[spans.length - 1][1]];
  const excluded: MsRange[] = [];
  for (let i = 0; i < spans.length - 1; i++) excluded.push([spans[i][1], spans[i + 1][0]]);
  return { trim, excluded };
}

/**
 * Edit State → 조각 목록 재구성 (재수화의 신 권위 경로).
 * 매칭: parent_fragment_id 우선, 다음 anchor ±10ms. span 1개 = trim 반영,
 * N개 = _cN 파생 분할(적용 핸들러와 동일 표현), removed = 목록에서 제외.
 */
export function applyStatesToFragments<T extends Record<string, any>>(
  fragments: T[],
  states: EditStateRow[]
): T[] {
  if (!states.length) return fragments;
  const byFid = new Map(states.filter((s) => s.parent_fragment_id).map((s) => [s.parent_fragment_id as string, s]));
  const out: T[] = [];
  for (const fr of fragments) {
    const fid: string | undefined = fr.fragment_id ?? fr.fragment_uid;
    let st = fid ? byFid.get(fid) : undefined;
    if (!st) {
      const aS = toMs(Number(fr.start_sec ?? fr.start_time ?? fr.start ?? 0));
      const aE = toMs(Number(fr.end_sec ?? fr.end_time ?? fr.end ?? 0));
      st = states.find(
        (s) => s.source_id === fr.source_id && Math.abs(s.anchor_start_ms - aS) <= 10 && Math.abs(s.anchor_end_ms - aE) <= 10
      );
    }
    if (!st) {
      out.push(fr);
      continue;
    }
    if (st.removed || st.spans.length === 0) continue; // REMOVE → 사용본 제외
    if (st.spans.length === 1) {
      const [s, e] = st.spans[0];
      out.push({
        ...fr,
        start_sec: s / 1000, end_sec: e / 1000,
        start_time: s / 1000, end_time: e / 1000,
        orig_start_sec: st.anchor_start_ms / 1000, orig_end_sec: st.anchor_end_ms / 1000,
        trim_applied: true,
      });
    } else {
      st.spans.forEach(([s, e], k) => {
        out.push({
          ...fr,
          fragment_id: `${fid}_c${k + 1}`,
          fragment_uid: `${fid}_c${k + 1}`,
          root_fragment_uid: fid,
          start_sec: s / 1000, end_sec: e / 1000,
          start_time: s / 1000, end_time: e / 1000,
          start_frame: Math.round((s / 1000) * 30), end_frame: Math.round((e / 1000) * 30),
          orig_start_sec: st.anchor_start_ms / 1000, orig_end_sec: st.anchor_end_ms / 1000,
          trim_applied: true,
        });
      });
    }
  }
  return out;
}
