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

/**
 * [#21 잔여 — 폰트 단일화 2026-07-19] 화면 내 모든 '조각 텍스트'(우측 전사·중앙 스토리카드)는
 * 이 폰트 하나를 쓴다. 한글 글리프 있는 SANS(앱 기본 Inter는 한글 폴백이라 계층마다 달라 보였다).
 */
export const FRAGMENT_TEXT_FONT =
  `-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif`;

export const FRAGMENT_TEXT_ACTIVE_COLOR = "rgba(231,232,236,1)";
export const FRAGMENT_TEXT_INACTIVE_COLOR = "rgba(231,232,236,0.34)";

export function fragmentTextColor(active: boolean): string {
  return active ? FRAGMENT_TEXT_ACTIVE_COLOR : FRAGMENT_TEXT_INACTIVE_COLOR;
}

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
