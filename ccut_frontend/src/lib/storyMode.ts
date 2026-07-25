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

export type StoryStageKey = "scanned" | "consulting" | "awaiting" | "edit_consult" | "final";

/**
 * [GATE-LOOP-01 3번] 지금 어느 단계인가 — 화면 상단 배지의 단일 진실.
 *
 * 왜 필요한가: 오늘 국장이 스토리 승인 화면을 "임시 페이지"로 오인했다. 화면이 무엇을
 * 하는 중인지 말해주지 않았기 때문이다. 단계를 글자로 박아 재발을 막는다.
 *
 * 상태기계(story_state)에서 파생만 한다 — 배지가 자기 상태를 갖지 않는다(분열 방지).
 *   scanned       재료 없음                     → "분석 중"
 *   story_draft   첫 원고, 승인 전               → "협의중"
 *   story_review  승인 후 원고가 바뀜(복귀)       → "승인대기"
 *   story_approved + 확정 안 함                  → "편집협의"  (A/B 중 고르는 중)
 *   story_approved + 확정함                      → "확정"
 * 재편집 세션(reEditActive)은 승인 상태여도 원고를 다시 만지는 중이므로 "협의중"이다.
 */
export function storyStageBadge(
  storyState: string | null | undefined,
  committedProposalId?: string | null,
  reEditActive = false
): { key: StoryStageKey; label: string; hint: string } {
  if (reEditActive) {
    return { key: "consulting", label: "협의중", hint: "이 원고를 다시 다듬고 있습니다" };
  }
  switch (storyState) {
    case STORY_DRAFT_STATE:
      return { key: "consulting", label: "협의중", hint: "원고를 고치는 중 — 마음에 들면 승인하세요" };
    case STORY_REVIEW_STATE:
      return { key: "awaiting", label: "승인대기", hint: "원고가 바뀌었습니다 — 다시 승인해야 편집으로 갑니다" };
    case STORY_APPROVED_STATE:
      return committedProposalId
        ? { key: "final", label: "확정", hint: `${committedProposalId}안으로 확정 — 내보낼 수 있습니다` }
        : { key: "edit_consult", label: "편집협의", hint: "편집안(A·B)을 고르는 중" };
    default:
      return { key: "scanned", label: "분석 중", hint: "영상에서 조각을 만들고 있습니다" };
  }
}
