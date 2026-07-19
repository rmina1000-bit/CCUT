export const STORY_APPROVED_STATE = "story_approved";
export const STORY_DRAFT_STATE = "story_draft";

/**
 * [R8 유령 1호 2026-07-20] story 진입은 '명시적 신호'만 — 상태 표류로는 진입 불가.
 *   - reEditActive: 재편집 세션(‘다시 편집’·‘이 원고로 재작업’이 세운다) → story 유지
 *   - story_draft: 한 번도 승인 안 된 첫 원고 → story
 * review(승인 후 A/B 확정으로 hash가 바뀐 상태)는 reEditActive일 때만 story다. A/B 미리보기·
 * 확정 왕복이 무대를 스토리로 끌어가던 '심판 과잉'을 봉인한다. 재작업 버튼은 reEditActive를
 * 세우므로 'R7 재작업→story' 성과는 그대로 보존된다.
 */
export function isStoryMode(
  storyState: string | null | undefined,
  reEditActive = false
): boolean {
  return reEditActive || storyState === STORY_DRAFT_STATE;
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
