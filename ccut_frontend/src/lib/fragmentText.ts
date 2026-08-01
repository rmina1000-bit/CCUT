/**
 * [#18 근본 — 텍스트 단일 진실 원천 2026-07-19]
 *
 * 헌장 "두 진실 금지"를 텍스트 계층에 강제한다. 조각(fragment)의 표시 텍스트는
 * 오직 여기 하나에서 나온다. 모든 화면 계층(우측 전사 · 중앙 스토리카드 · 스토리박스 ·
 * 원고)이 이 함수를 거친다.
 *
 * 진실 원천 = 클램프된 ASR words (ledger가 조각 시간창으로 잘라 준 것).
 *  - words가 있으면 그 글자 그대로(공백 조인). 큐원/VL이 다시 쓴 문장·지문(stage_direction,
 *    "병원" 등 장소 번역)은 절대 섞지 않는다 — 그게 "조각맵에 없는 단어"가 새던 구멍이었다.
 *  - words가 없고 dialogue만 있으면(단어 타임스탬프 없는 ASR) dialogue 폴백(여전히 ASR 원문).
 *  - 둘 다 없으면(무음·환각) 빈 문자열. 표시 계층이 무음 마커를 그린다(계층 공통).
 *
 * 큐원은 조각을 '고르고 배열'만 한다. 글자는 원문 그대로 — 재작성 금지.
 */
import type { CSSProperties } from "react";

/**
 * [#21 잔여 — 폰트 단일화 2026-07-19] 화면 내 모든 '조각 텍스트'(우측 전사·중앙 스토리카드)는
 * 이 폰트 하나를 쓴다. 한글 글리프 있는 SANS(앱 기본 Inter는 한글 폴백이라 계층마다 달라 보였다).
 */
export const FRAGMENT_TEXT_FONT =
  `-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif`;

export const FRAGMENT_TEXT_ACTIVE_COLOR = "rgba(231,232,236,1)";
// [CONTRAST-1 2026-08-01] 비활성 조각 텍스트. 0.34 -> 0.55 (카드 배경 기준 2.76:1 -> 5.00:1).
// 뜻은 그대로 남는다 — 활성은 13.42:1 이라 여전히 두 배 넘게 밝다. 흐림은 정보이되,
// 읽으려고 화면에 얼굴을 대야 하는 흐림은 정보가 아니라 장벽이다.
export const FRAGMENT_TEXT_INACTIVE_COLOR = "rgba(231,232,236,0.55)";
// [#21-c R8 2026-07-20] 제외(범위·단어) 표시색 — 우측 전사가 하드코딩하던 회색. 계약으로 흡수.
// [CONTRAST-1 2026-08-01] 제외 단어색. 45% -> 55% (3.35:1 -> 4.77:1, AA 통과).
// 활성 13.42:1 과의 간격은 그대로라 '잘려 나간 말'이라는 표시는 유지된다.
export const FRAGMENT_TEXT_EXCLUDED_COLOR = "hsl(220,5%,55%)";

export function fragmentTextColor(active: boolean): string {
  return active ? FRAGMENT_TEXT_ACTIVE_COLOR : FRAGMENT_TEXT_INACTIVE_COLOR;
}

/**
 * [#21 잔여 — R8 유령 6호 2026-07-20] 조각 텍스트 '표시 스타일' 단일 계약(색·기울임까지).
 * 계층마다 italic·foreground/85를 하드코딩해 폰트가 기울어(쓰러져) 보이던 것을 봉인한다.
 * 표시 계층(중앙 스토리카드·우측 전사)은 이 스타일 객체만 쓴다 — 앱 기본은 정자체(normal).
 */
export const FRAGMENT_TEXT_STYLE: CSSProperties = {
  color: FRAGMENT_TEXT_ACTIVE_COLOR,
  fontStyle: "normal",
};
/** 무음 마커 — 활성 텍스트와 같은 색·같은 정자체. (구 중앙 italic 제거) */
export const FRAGMENT_SILENT_STYLE: CSSProperties = {
  color: FRAGMENT_TEXT_ACTIVE_COLOR,
  fontStyle: "normal",
};
/** 제외 표시 — 회색 + 취소선. 우측 전사가 쓰던 인라인 하드코딩을 대체한다. */
export const FRAGMENT_EXCLUDED_STYLE: CSSProperties = {
  color: FRAGMENT_TEXT_EXCLUDED_COLOR,
  textDecoration: "line-through",
};

export interface FragmentTextSource {
  words?: Array<{ w: string }> | null;
  dialogue?: string | null;
}

/** 조각의 단일 진실 표시 텍스트. 모든 계층이 이것만 쓴다. */
export function fragmentTranscriptText(item: FragmentTextSource | null | undefined): string {
  if (!item) return "";
  if (Array.isArray(item.words) && item.words.length > 0) {
    return item.words.map((w) => w.w).join(" ").replace(/\s+/g, " ").trim();
  }
  return (item.dialogue ?? "").replace(/\s+/g, " ").trim();
}

/** 무음(텍스트 없음) 여부 — 표시 계층이 마커를 그릴지 판단. */
export function isFragmentSilent(item: FragmentTextSource | null | undefined): boolean {
  return fragmentTranscriptText(item).length === 0;
}
