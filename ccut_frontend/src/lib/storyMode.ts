export const STORY_APPROVED_STATE = "story_approved";

export function isStoryMode(
  storyState: string | null | undefined,
  reEditActive = false
): boolean {
  return reEditActive || (!!storyState && storyState !== STORY_APPROVED_STATE);
}
