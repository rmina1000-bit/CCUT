/*
 * STORY-GATE copy lives here first, as one file.
 *
 * Voice rules:
 * - User-facing text should be short, soft, and shown only on meaningful changes.
 * - Do not repeat the same sentence back-to-back.
 * - Avoid exposing internal words: 모드, 전환, 상태, 활성화, 렌더, 세션, 버전ID, 스냅샷.
 *
 * Growth rule:
 * - Keep this as a single file until it grows past one-file readability, needs
 *   multiple languages, or splits into clear step/feature groups.
 */

export const STORY_GATE_COPY = {
  actions: {
    saveStory: "스토리 저장",
    saveStoryTitle: "지금 이야기를 저장합니다. 저장하면 A·B 제안을 만듭니다.",
    saveStoryAgainTitle: "고친 이야기를 새로 저장합니다. 같은 프로젝트 안에 하나 더 남습니다.",
    saveStoryAs: "다른 이름으로 스토리 저장",
    saveStoryAsTitle: "이름을 새로 붙여 이야기를 하나 더 저장합니다.",
    saveStoryPrompt: "저장할 이야기 이름을 적어 주세요.",
  },
  versionBar: {
    label: "스토리 버전",
  },
  chat: {
    storySaved: "이야기를 저장했어요. 이제 편집으로 가볼까요?",
    editStarted: "편집을 시작할게요. 조각을 누르면 소리와 화면을 다듬을 수 있어요.",
    storyReturned: "이야기로 돌아왔어요. 조각을 고르고 빼는 중이에요.",
  },
  chatActions: {
    startEditing: "편집 시작",
  },
  precisionPanel: {
    storyHeading: "이야기",
    editHeading: "편집",
    editBody: "소리와 화면을 다듬는 자리는 여기입니다.",
    editSoon: "세부 손질은 다음 카드에서 이어집니다.",
  },
  editVersionBar: {
    label: "편집본",
  },
  abCards: {
    heading: "편집 제안",
    large: "크게 보기",
    choose: "고르기",
    seconds: "초",
  },
  toast: {
    storySaved: "이야기를 저장했어요",
  },
} as const;
