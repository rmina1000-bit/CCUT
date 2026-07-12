/**
 * [EDIT-CONTRACT-B0] 공통 편집 계약 코어 (TS — 제품용).
 * Python 대응 구현: ccut_backend/edit_contract/ — fixtures JSON으로 동등성 증명.
 *
 * 규칙 원문·미규정 처리 결정은 ccut_backend/edit_contract/edit_state.py 도크스트링과 동일
 * (단일 원천은 fixtures — 두 구현이 같은 케이스 벡터를 통과해야 한다).
 */

export const SCHEMA_VERSION = 1;

export const LAST_ORIGIN_VALUES = [
  "PBE",
  "TEXT_EDITOR",
  "NATURAL_LANGUAGE",
  "MIGRATION",
  "SYSTEM",
  "INHERIT",
] as const;

export type MsRange = [number, number];

export interface EditStateInput {
  anchor_start_ms: number;
  anchor_end_ms: number;
  trim_start_ms: number;
  trim_end_ms: number;
  excluded_ranges?: MsRange[];
  removed?: boolean;
}

export interface CanonicalEditState {
  anchor_start_ms: number;
  anchor_end_ms: number;
  trim_start_ms: number;
  trim_end_ms: number;
  excluded_ranges: MsRange[];
  removed: boolean;
}

export type ReceiptEntry = Record<string, unknown> & { rule: string };

/** v0.4 확정 변환식: floor(seconds × 1000 + 0.5). 전제: 시간 >= 0. */
export function toMs(seconds: number): number {
  if (seconds < 0) throw new Error("time must be >= 0");
  return Math.floor(seconds * 1000 + 0.5);
}

/** 표시·Preview·Export 전달용 */
export function msToSeconds(ms: number): number {
  return ms / 1000.0;
}

function canonicalOf(
  anchor: MsRange,
  trim: MsRange,
  excluded: MsRange[],
  removed: boolean
): CanonicalEditState {
  return {
    anchor_start_ms: anchor[0],
    anchor_end_ms: anchor[1],
    trim_start_ms: trim[0],
    trim_end_ms: trim[1],
    excluded_ranges: excluded,
    removed,
  };
}

/** 입력 편집 상태 → [canonical 상태, receipt]. anchor는 절대 불변. */
export function normalize(state: EditStateInput): [CanonicalEditState, ReceiptEntry[]] {
  const receipt: ReceiptEntry[] = [];
  const anchor: MsRange = [Math.trunc(state.anchor_start_ms), Math.trunc(state.anchor_end_ms)];
  const trimIn: MsRange = [Math.trunc(state.trim_start_ms), Math.trunc(state.trim_end_ms)];
  const excludedIn: MsRange[] = (state.excluded_ranges ?? []).map(
    (r) => [Math.trunc(r[0]), Math.trunc(r[1])] as MsRange
  );
  const removed = !!state.removed;

  if (removed) {
    if (excludedIn.length) receipt.push({ rule: "removed_input_clears_excluded" });
    return [canonicalOf(anchor, trimIn, [], true), receipt];
  }

  let ts = trimIn[0];
  let te = trimIn[1];
  if (ts >= te) {
    receipt.push({ rule: "empty_trim_to_removed" });
    return [canonicalOf(anchor, trimIn, [], true), receipt];
  }

  // 창 밖 무시 / 걸침 절단 / 무효 무시 (입력 순서대로 판정)
  const kept: MsRange[] = [];
  for (const [s, e] of excludedIn) {
    if (s >= e) {
      receipt.push({ rule: "ignored_invalid", range: [s, e] });
      continue;
    }
    if (e <= ts || s >= te) {
      receipt.push({ rule: "ignored_outside", range: [s, e] });
      continue;
    }
    const cs = Math.max(s, ts);
    const ce = Math.min(e, te);
    if (cs !== s || ce !== e) {
      receipt.push({ rule: "clamped", from: [s, e], to: [cs, ce] });
    }
    kept.push([cs, ce]);
  }

  // 1) 정렬
  const swept = kept.slice().sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]));
  const orderChanged = swept.some((r, i) => r[0] !== kept[i][0] || r[1] !== kept[i][1]);
  if (orderChanged) receipt.push({ rule: "sorted" });

  // 2) 겹침·맞닿음 병합
  const merged: MsRange[] = [];
  const groups: MsRange[][] = [];
  for (const r of swept) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) {
      groups[groups.length - 1].push([r[0], r[1]]);
      if (r[1] > last[1]) last[1] = r[1];
    } else {
      merged.push([r[0], r[1]]);
      groups.push([[r[0], r[1]]]);
    }
  }
  for (let i = 0; i < merged.length; i++) {
    if (groups[i].length > 1) {
      receipt.push({ rule: "merged", from: groups[i], to: [merged[i][0], merged[i][1]] });
    }
  }

  // 4) 전체 제거 → removed
  if (merged.length === 1 && merged[0][0] === ts && merged[0][1] === te) {
    receipt.push({ rule: "fully_excluded_to_removed" });
    return [canonicalOf(anchor, trimIn, [], true), receipt];
  }

  // 3) 경계 흡수 (병합 후 disjoint·비접촉 — 각 측 1회로 충분)
  if (merged.length && merged[0][0] === ts) {
    const r = merged.shift() as MsRange;
    ts = r[1];
    receipt.push({ rule: "absorbed_start", range: r, trim_start_ms: ts });
  }
  if (merged.length && merged[merged.length - 1][1] === te) {
    const r = merged.pop() as MsRange;
    te = r[0];
    receipt.push({ rule: "absorbed_end", range: r, trim_end_ms: te });
  }

  // 5) 잔여 = 순내부 구간
  return [canonicalOf(anchor, [ts, te], merged, false), receipt];
}

/** compile(state) → removed ? [] : subtract(trim, excluded). 순수 함수 — 저장하지 않는다. */
export function compileSpans(canonical: CanonicalEditState): MsRange[] {
  if (canonical.removed) return [];
  const spans: MsRange[] = [];
  let cur = canonical.trim_start_ms;
  for (const [s, e] of canonical.excluded_ranges) {
    if (s > cur) spans.push([cur, s]);
    cur = e;
  }
  if (cur < canonical.trim_end_ms) spans.push([cur, canonical.trim_end_ms]);
  return spans;
}

/** ed_id = "{edit_state_id}_k{순번}" (1-기점, 결정론). */
export function edIds(editStateId: string, spans: MsRange[]): string[] {
  return spans.map((_, i) => `${editStateId}_k${i + 1}`);
}

/** 재조각화 시 anchor(±tol_ms) 재매칭 — anchor는 덮어쓰지 않는다. 첫 매칭 인덱스 또는 null. */
export function rematchAnchor(
  anchor: MsRange,
  candidates: MsRange[],
  tolMs = 10
): number | null {
  const [aS, aE] = anchor;
  for (let i = 0; i < candidates.length; i++) {
    const [cS, cE] = candidates[i];
    if (Math.abs(cS - aS) <= tolMs && Math.abs(cE - aE) <= tolMs) return i;
  }
  return null;
}
