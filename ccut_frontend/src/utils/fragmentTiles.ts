/**
 * [R2 수리] 조각맵 분할 타일 = "상태의 순수 파생".
 * 뿌리 조각 + fragment_edit_state(spans) → 표시 타일 목록을 매번 통째로 재계산한다.
 * 입력 배열에 _c 자식이 섞여 있어도 먼저 뿌리로 접은 뒤 다시 파생하므로
 * 같은 상태면 몇 번을 돌려도 같은 결과(멱등) — _c1_c1 중첩은 원리적으로 불가.
 * 세션 내 Apply 경로와 새로고침 재수화 경로가 이 모듈 하나를 쓴다.
 */
import { rangeDisplayName } from "@/lib/fragmentIdentity";
import { toMs } from "./editContract";
import type { EditStateRow } from "./editContractClient";

const rootFidOf = (fr: Record<string, any>): string =>
  String(fr.root_fragment_uid ?? fr.fragment_id ?? fr.fragment_uid ?? "");

/** _c 자식에서 뿌리 조각 표현을 복원 (좌표는 orig_* 우선, 없으면 state anchor). */
function rootRepOf<T extends Record<string, any>>(fr: T, st: EditStateRow | undefined): T {
  const fid = rootFidOf(fr);
  if (String(fr.fragment_id ?? fr.fragment_uid ?? "") === fid) return fr; // 이미 뿌리
  const s = fr.orig_start_sec ?? (st ? st.anchor_start_ms / 1000 : fr.start_sec);
  const e = fr.orig_end_sec ?? (st ? st.anchor_end_ms / 1000 : fr.end_sec);
  return {
    ...fr,
    fragment_id: fid,
    fragment_uid: fid,
    root_fragment_uid: undefined,
    // stable_key는 resolver가 "그 시점 그 조각"에 발급한 것 — 접힌 대표의 것을 승계하면
    // 파생 타일들이 같은 key를 갖게 된다. 지우면 FragmentMap이 uid(유일)로 fallback.
    stable_key: undefined,
    display_name: rangeDisplayName(fr.display_name, s, e),
    start_sec: s, end_sec: e,
    start_time: s, end_time: e,
    start_frame: Math.round(s * 30), end_frame: Math.round(e * 30),
    duration: Math.max(1, Math.round(e * 30) - Math.round(s * 30)),
  };
}

/** (뿌리조각, edit_state) → 표시 타일[]. 순수 함수 — spans 1개=trim, N개=_cN, removed=[] */
export function tilesForRoot<T extends Record<string, any>>(
  root: T,
  st: EditStateRow | undefined,
): T[] {
  if (!st) return [root];
  if (st.removed || st.spans.length === 0) return []; // REMOVE → 사용본 제외
  const fid = rootFidOf(root);
  if (st.spans.length === 1) {
    const [s, e] = st.spans[0];
    return [{
      ...root,
      stable_key: undefined,  // 승계 금지 — key는 uid로
      start_sec: s / 1000, end_sec: e / 1000,
      start_time: s / 1000, end_time: e / 1000,
      start_frame: Math.round((s / 1000) * 30), end_frame: Math.round((e / 1000) * 30),
      duration: Math.max(1, Math.round((e / 1000) * 30) - Math.round((s / 1000) * 30)),
      orig_start_sec: st.anchor_start_ms / 1000, orig_end_sec: st.anchor_end_ms / 1000,
      trim_applied: true,
    }];
  }
  return st.spans.map(([s, e], k) => ({
    ...root,
    stable_key: undefined,  // 승계 금지 — key는 uid(_cN, 유일)로
    fragment_id: `${fid}_c${k + 1}`,
    fragment_uid: `${fid}_c${k + 1}`,
    root_fragment_uid: fid,
    display_name: rangeDisplayName(root.display_name, s / 1000, e / 1000),
    start_sec: s / 1000, end_sec: e / 1000,
    start_time: s / 1000, end_time: e / 1000,
    start_frame: Math.round((s / 1000) * 30), end_frame: Math.round((e / 1000) * 30),
    duration: Math.max(1, Math.round((e / 1000) * 30) - Math.round((s / 1000) * 30)),
    orig_start_sec: st.anchor_start_ms / 1000, orig_end_sec: st.anchor_end_ms / 1000,
    trim_applied: true,
  }));
}

/** 뿌리 fid → 상태 매칭. parent_fragment_id 우선(중복 시 선호 item id), 다음 anchor ±10ms. */
function stateForRoot(
  fid: string,
  root: Record<string, any>,
  states: EditStateRow[],
  preferredItemIdFor?: (rootFid: string) => string,
): EditStateRow | undefined {
  const byParent = states.filter((s) => s.parent_fragment_id === fid);
  if (byParent.length === 1) return byParent[0];
  if (byParent.length > 1) {
    const want = preferredItemIdFor?.(fid);
    return byParent.find((s) => s.timeline_item_id === want) ?? byParent[0];
  }
  const aS = toMs(Number(root.orig_start_sec ?? root.start_sec ?? root.start_time ?? root.start ?? 0));
  const aE = toMs(Number(root.orig_end_sec ?? root.end_sec ?? root.end_time ?? root.end ?? 0));
  return states.find(
    (s) => s.source_id === root.source_id
      && Math.abs(s.anchor_start_ms - aS) <= 10 && Math.abs(s.anchor_end_ms - aE) <= 10,
  );
}

/**
 * 화면 배열 전체 재구성. 뿌리 최초 등장 위치에 파생 타일을 앉히고,
 * 같은 뿌리의 나머지 항목(_c 자식 등)은 접는다.
 */
export function rebuildFragmentTiles<T extends Record<string, any>>(
  fragments: T[],
  states: EditStateRow[],
  preferredItemIdFor?: (rootFid: string) => string,
): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const fr of fragments) {
    const fid = rootFidOf(fr);
    if (!fid) { out.push(fr); continue; }
    if (seen.has(fid)) continue; // 같은 뿌리의 후속 자식 — 이미 파생 완료
    seen.add(fid);
    const st = stateForRoot(fid, fr, states, preferredItemIdFor);
    out.push(...tilesForRoot(rootRepOf(fr, st), st));
  }
  return out;
}
