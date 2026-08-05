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
    saveStoryTitle: "지금 이야기를 저장합니다. 다음에 편집으로 넘어갈 수 있습니다.",
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
    editPreparing: "조각 경계와 소리를 살펴보는 중이에요.",
    proposalPicked: (key: "A" | "B") => `${key}안을 선택하셨어요. 이걸 바탕으로 더 세밀하게 다듬을 수 있어요.`,
    storyReturned: "이야기로 돌아왔어요. 조각을 고르고 빼는 중이에요.",
    editBridgeFailed: "편집 시작으로 잇지 못했어요. 편집 시작 버튼으로 다시 이어볼게요.",
    pastNotice: "지난 알림",
  },
  chatActions: {
    startEditing: "편집 시작",
  },
  precisionPanel: {
    storyHeading: "이야기",
    editHeading: "편집",
    editBody: "소리와 화면을 다듬는 자리는 여기입니다.",
    editMapNote: "이미지 조각을 누르면 세부 손질창이 열립니다.",
  },
  editVersionBar: {
    label: "편집본",
  },
  sound: {
    action: "소리",
    actionTitle: "조각마다 소리를 어떻게 다룰지 봅니다.",
    play: "조각 재생",
    handlingLabel: "편집에서 다룰 방식",
    detailHeading: "소리",
    corrected: "직접 고침",
    loading: "소리를 살펴보는 중",
    loadFailed: "소리를 불러오지 못했어요.",
    saveFailed: "고친 내용을 남기지 못했어요.",
    roles: {
      dialogue: "대사",
      background: "배경",
      silence: "무음",
      unknown: "모르겠음",
    },
    reasons: {
      transcript: (count: number) => `전사 단어 ${count}개가 겹침`,
      transcriptCompact: (count: number) => `${count}단어`,
      speech: "말소리가 잡힘",
      speechCompact: "말소리",
      background: "말은 없고 주변 소리가 잡힘",
      backgroundCompact: "주변 소리",
      silence: "소리가 없는 구간으로 잡힘",
      silenceCompact: "소리 없음",
      noMaterial: "살펴볼 재료가 없음",
      noMaterialCompact: "재료 없음",
      noCoordinates: "조각 시각을 찾지 못함",
      noCoordinatesCompact: "시각 없음",
    },
  },
  abCards: {
    heading: "편집 제안",
    large: "크게 보기",
    largeBlocked: "새 창을 열지 못했어요.",
    choose: "고르기",
    chooseFailed: "아직 이 안을 고를 수 없어요. 다시 열어보고 있습니다.",
    picked: (key: "A" | "B") => `${key}안을 골랐어요.`,
    nearMatch: "이 영상은 짧아서 두 안의 차이가 거의 없어요.",
    seconds: "초",
    variants: {
      A: {
        title: "알맹이만 (A)",
        shortTitle: "알맹이만",
        desc: "말이 살아 있는 부분을 중심으로 앞뒤 늘어짐을 덜어낸 안입니다.",
      },
      B: {
        title: "여유롭게 (B)",
        shortTitle: "여유롭게",
        desc: "앞뒤 숨을 남겨 현장의 흐름을 편안하게 보는 안입니다.",
      },
    },
  },
  toast: {
    storySaved: "이야기를 저장했어요",
  },
} as const;

export function soundRoleReasonText(
  item: {
    reason?: string;
    overridden?: boolean;
    evidence?: { transcript?: { word_count?: number | null } };
  },
  compact: boolean,
): string {
  const wordCount = Number(item.evidence?.transcript?.word_count ?? 0);
  let reason: string;
  switch (item.reason) {
    case "transcript":
      reason = compact
        ? STORY_GATE_COPY.sound.reasons.transcriptCompact(wordCount)
        : STORY_GATE_COPY.sound.reasons.transcript(wordCount);
      break;
    case "silero_speech":
      reason = compact
        ? STORY_GATE_COPY.sound.reasons.speechCompact
        : STORY_GATE_COPY.sound.reasons.speech;
      break;
    case "audio_energy":
      reason = compact
        ? STORY_GATE_COPY.sound.reasons.backgroundCompact
        : STORY_GATE_COPY.sound.reasons.background;
      break;
    case "silence_sensor":
      reason = compact
        ? STORY_GATE_COPY.sound.reasons.silenceCompact
        : STORY_GATE_COPY.sound.reasons.silence;
      break;
    case "missing_coordinates":
      reason = compact
        ? STORY_GATE_COPY.sound.reasons.noCoordinatesCompact
        : STORY_GATE_COPY.sound.reasons.noCoordinates;
      break;
    default:
      reason = compact
        ? STORY_GATE_COPY.sound.reasons.noMaterialCompact
        : STORY_GATE_COPY.sound.reasons.noMaterial;
  }
  return item.overridden && !compact
    ? `${STORY_GATE_COPY.sound.corrected} · ${reason}`
    : reason;
}
