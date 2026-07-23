export const STORY_APPROVED_STATE = "story_approved";
export const STORY_DRAFT_STATE = "story_draft";
export const STORY_REVIEW_STATE = "story_review";

/**
 * [R8 유령 1호 2026-07-20] story 진입은 '명시적 신호'만 — 상태 표류로는 진입 불가.
 *   - reEditActive: 재편집 세션(‘다시 편집’·‘이 원고로 재작업’이 세운다) → story 유지
 *   - story_draft: 한 번도 승인 안 된 첫 원고 → story
 *   - story_review: 승인 뒤 원고 순서가 바뀌어 재승인이 필요한 원고 → story
 * 승인 지문과 현재 원고가 다르면 렌더가 막히므로, 화면도 같은 상태를 따라야 한다.
 */
export function isStoryMode(
  storyState: string | null | undefined,
  reEditActive = false
): boolean {
  return reEditActive || storyState === STORY_DRAFT_STATE || storyState === STORY_REVIEW_STATE;
}

/**
 * [R8 유령 4호 2026-07-20] 중앙·우측이 '하나의 식'으로 story 무대를 켠다. 후단 조건(원고 존재
 * = item_count)을 유틸 안으로 흡수해, 바깥에서 서로 다른 조건(중앙 `||proposals` vs 우측
 * `item_count`)을 붙이던 분열 경로를 차단한다. story 모드 + 원고가 실제로 있을 때만 참.
 */
export function storyStageVisible(
  story: { story_state?: string | null; item_count?: number | null } | null | undefined,
  reEditActive = false
): boolean {
  return isStoryMode(story?.story_state, reEditActive) && (story?.item_count ?? 0) > 0;
}
