/**
 * [#21·#22 조각은 하나] 조각맵 타일 = "상태의 순수 파생" — 뿌리당 타일 1개.
 * 헌장 §6 조각 헌법: 조각은 자동 분할되지 않는다. 중간 제외 = 조각 내부의
 * 비활성 구간 (삭제 ❌ 렌더 제외 ✔ 구조 유지). _cN 파생 표시는 폐지
 * (2026-07-17 국장 판정 ①-나). 살아남는 구간은 spans_ms 속성으로 타일에 동봉.
 * 입력 배열에 저장 잔재 _c 자식이 섞여 있어도 뿌리로 접은 뒤 재파생 (멱등).
 * 세션 내 Apply 경로와 새로고침 재수화 경로가 이 모듈 하나를 쓴다.
 */
import { rangeDisplayName } from "@/lib/fragmentIdentity";
import { toMs } from "./editContract";
import type { EditStateRow } from "./editContractClient";

const rootFidOf = (fr: Record<string, any>): string =>
  // [#21 데이터 호환] 저장 잔재 _cN uid는 root_fragment_uid가 없어도 접미사를 벗겨 뿌리로 접는다
  // (중첩 _c1_c1 포함). 신규 _cN 생산은 폐지 — 이 폴백은 과거 데이터 전용.
  String(fr.root_fragment_uid ?? fr.fragment_id ?? fr.fragment_uid ?? "").replace(/(_c\d+)+$/, "");

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

const fmtMs = (ms: number): string => {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

/**
 * (뿌리조각, edit_state) → 표시 타일 0~1개. 순수 함수.
 * removed=[] / spans 1개=trim / spans N개=타일 1개 + 내부 제외 마커 — _cN 파생 없음.
 * 좌표 = 생존 외피(spans 첫 시작~끝 끝), duration = 살아남는 길이,
 * 표기 = "제목 · 살아남/전체 ✂n구간" (내부 제외 존재 시).
 */
export function tilesForRoot<T extends Record<string, any>>(
  root: T,
  st: EditStateRow | undefined,
): T[] {
  if (!st) return [root];
  if (st.removed || st.spans.length === 0) return []; // REMOVE → 사용본 제외
  const first = st.spans[0][0];
  const last = st.spans[st.spans.length - 1][1];
  const aliveMs = st.spans.reduce((acc, [s, e]) => acc + (e - s), 0);
  const totalMs = st.anchor_end_ms - st.anchor_start_ms;
  const nSpans = st.spans.length;
  const title = root.display_name ? String(root.display_name).split(" · ")[0] : undefined;
  const display_name = nSpans > 1
    ? `${title ? `${title} · ` : ""}${fmtMs(aliveMs)}/${fmtMs(totalMs)} ✂${nSpans}구간`
    : rangeDisplayName(root.display_name, first / 1000, last / 1000);
  return [{
    ...root,
    stable_key: undefined,  // 승계 금지 — key는 uid로
    display_name,
    start_sec: first / 1000, end_sec: last / 1000,
    start_time: first / 1000, end_time: last / 1000,
    start_frame: Math.round((first / 1000) * 30), end_frame: Math.round((last / 1000) * 30),
    duration: Math.max(1, Math.round((aliveMs / 1000) * 30)),
    orig_start_sec: st.anchor_start_ms / 1000, orig_end_sec: st.anchor_end_ms / 1000,
    spans_ms: st.spans.map(([s, e]) => [s, e]),   // 생존 구간 동봉 (ms 정수 단일 권위)
    has_excluded_inside: nSpans > 1,              // 내부 제외 존재 마커
    trim_applied: true,
  }];
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
  const want = preferredItemIdFor?.(fid);
  const aS = toMs(Number(root.orig_start_sec ?? root.start_sec ?? root.start_time ?? root.start ?? 0));
  const aE = toMs(Number(root.orig_end_sec ?? root.end_sec ?? root.end_time ?? root.end ?? 0));
  return states.find(
    (s) => (!want || s.timeline_item_id === want || s.carried_from_item_id === want)
      && s.source_id === root.source_id
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

/**
 * // [HANDS-3 2026-08-10] 조각 **풀**에 편집 좌표만 입힌다 — 빠진 조각도 남긴다.
 *
 * rebuildFragmentTiles 와 하는 일이 같되 딱 한 가지가 다르다: tilesForRoot 가
 * removed 뿌리를 배열에서 **지우는데**(:56), 풀에서 지우면 되살리기가 깨진다.
 * 국장 조각맵(FragmentMap storyOnly)은 풀을 fid → 조각 사전으로 쓰고
 * storyFragmentIds 로 골라 그린다(FragmentMap.tsx:174-180). 되살린 fid 가
 * 풀에 없으면 그 타일은 화면에 못 돌아온다 — "되살렸어요"라고 말해 놓고
 * 화면은 그대로인 바로 그 모양이다.
 *
 * 무엇을 빼고 무엇을 넣을지(선택·순서)는 storyFragmentIds 가 이미 정한다.
 * 여기서는 **길이와 잘린 자리**만 진실로 맞춘다 — 층을 안 넘는다.
 */
export function applyEditGeometry<T extends Record<string, any>>(
  fragments: T[],
  states: EditStateRow[],
  preferredItemIdFor?: (rootFid: string) => string,
): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const fr of fragments) {
    const fid = rootFidOf(fr);
    if (!fid) { out.push(fr); continue; }
    if (seen.has(fid)) continue;
    seen.add(fid);
    const st = stateForRoot(fid, fr, states, preferredItemIdFor);
    const rep = rootRepOf(fr, st);
    const tiles = tilesForRoot(rep, st);
    // removed / spans 0 → tilesForRoot 는 [] 를 준다. 풀에서는 뿌리를 남긴다.
    out.push(...(tiles.length ? tiles : [rep]));
  }
  return out;
}
