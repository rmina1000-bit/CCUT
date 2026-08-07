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
    // [EDIT-SAVE-1] 편집한 것을 남기는 자리. 스토리 저장과 말이 겹치지 않게 '편집본'으로 부른다.
    saveEdit: "편집본 저장",
    saveEditTitle: "지금 편집한 대로 하나 남깁니다. 나중에 이대로 다시 열 수 있습니다.",
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
  // [LIVING-DRAFT-1 2026-08-08] 초안 카드 — 이미 적용된 초안의 검수 손잡이.
  editDraftCard: {
    reduce: "조금 덜",
    revert: "원래대로",
    keep: "이대로",
    busy: "고치는 중…",
    reducedSaid: "조금 덜 다듬었어요.",
    revertedSaid: "원래대로 되돌렸어요.",
    keptSaid: "남겼어요.",
    reduceFailed: "덜 다듬기에 실패했어요",
    revertFailed: "되돌리지 못했어요",
  },
  // [PROPOSE-1A 2026-08-07] 대화→제안 카드 — 국장 결정 어휘 [해봐]/[됐어] 그대로.
  editProposalCard: {
    apply: "해봐",
    decline: "됐어",
    undo: "되돌리기",
    busy: "적용하는 중…",
    applied: "적용했어요.",
    declined: "알겠어요, 그대로 둘게요.",
    undone: "되돌렸어요.",
    failed: "적용하지 못했어요",
    undoFailed: "되돌리지 못했어요",
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
  editSave: {
    saved: "편집한 내용을 저장했어요.",
    failed: "편집한 내용을 저장하지 못했어요.",
    opened: "저장해 둔 편집본을 열었어요.",
    openFailed: "그 편집본을 불러오지 못했어요.",
    nothingToSave: "지금 화면에 남길 조각이 없어요.",
    missingCoords: (n: number) => `조각 ${n}개의 자리를 찾지 못했어요. 반쪽으로 남기지 않았어요.`,
  },
  // [EDIT-LOCK-1] 편집 자리에서 조각을 빼거나 넣으려 할 때. ★막는 말이 아니라 길을 여는 말이다.
  editLock: {
    notice: "조각을 빼고 넣는 일은 이야기에서 해요. 이야기로 돌아갈까요?",
    goStory: "이야기로 돌아가기",
    stay: "여기 있을게요",
  },
  // [PROGRESS-1 2026-08-06] 진행을 사람 말로. 무엇을 → 어떻게 되었는지, 숫자와 함께 한 줄씩.
  //   ★있는 시점에만 얹는다(새 폴링·타이머 없음). ★같은 문구는 연달아 쌓이지 않는다.
  progress: {
    editStarted: (n: number) => `조각 ${n}개로 편집을 시작할게요.`,
    soundLooking: (n: number) => `조각 ${n}개의 소리를 살펴보고 있어요.`,
    soundDone: (d: number, b: number, s: number) =>
      `소리를 다 살펴봤어요. 대사 ${d} · 배경 ${b} · 조용함 ${s}.`,
    abReady: "편집안 두 가지를 준비했어요. 마음에 드는 쪽을 골라 주세요.",
    abFailed: "편집안을 준비하지 못했어요. 이야기는 그대로 있어요.",
    fragmentTrimmed: (label: string, before: number, after: number) =>
      `${label} 조각을 다듬었어요. ${before.toFixed(1)}초 → ${after.toFixed(1)}초.`,
    fragmentTouched: (label: string) => `${label} 조각을 다듬었어요.`,
    editSaved: (n: number) => `편집본을 남겼어요 — 조각 ${n}개.`,
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
