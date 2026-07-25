// [SAVE-INTEGRITY] 대사 텍스트에디터 순수 로직 — React 무의존 단일 진실원천.
//   브라우저 에디터(ledgerTextEditor.tsx)와 헤드리스 치유 스크립트(scripts/heal_excluded.ts)가
//   같은 이 모듈을 import 한다. 로직 2벌 금지.

export type MsRange = [number, number];
export interface WordTok { w: string; s_ms: number; e_ms: number; p?: number | null; excluded?: boolean; }
export interface Char { ch: string; s_ms: number | null; e_ms: number | null; }
export interface TextEditing { itemId: string; chars: Char[]; inactive: Set<number>; caret: number; }

export const wordsToChars = (words: WordTok[]): Char[] => {
  const chars: Char[] = [];
  words.forEach((w, wi) => {
    const arr = Array.from(w.w);
    const per = arr.length ? (w.e_ms - w.s_ms) / arr.length : 0;
    arr.forEach((ch, i) => chars.push({
      ch, s_ms: Math.round(w.s_ms + i * per), e_ms: Math.round(w.s_ms + (i + 1) * per),
    }));
    if (wi < words.length - 1) chars.push({ ch: " ", s_ms: null, e_ms: null });
  });
  return chars;
};

export const editingFromWords = (itemId: string, words: WordTok[], excludedRanges: number[][] = [], caret = 0): TextEditing => {
  const chars = wordsToChars(words);
  const inactive = new Set<number>();
  // (a) 기존 excluded_ranges 겹침 복원
  excludedRanges.forEach(([s, e]) => {
    chars.forEach((c, i) => {
      if (c.s_ms != null && c.s_ms < e && (c.e_ms ?? 0) > s) inactive.add(i);
    });
  });
  // (b) [SAVE-INTEGRITY] 백엔드가 비선택으로 표시한 단어(word.excluded: trim 밖·기존 제외 포함)를
  //     단어 전체 단위로 union — 화면 취소선과 저장 산식의 두 진실을 하나로 합친다.
  let ci = 0;
  for (const w of words) {
    const n = Array.from(w.w).length;
    if (w.excluded) for (let k = 0; k < n; k++) inactive.add(ci + k);
    ci += n + 1; // 단어 글자 + 뒤 공백 1칸 (wordsToChars 레이아웃과 동일)
  }
  return { itemId, chars, inactive, caret };
};

export const excludedRangesFromEditing = (editing: TextEditing): { ranges: number[][]; droppedZero: number } => {
  const chars = editing.chars;
  // 1) 글자를 단어로 묶는다 (공백 = 타임스탬프 null 로 분리)
  const words: { idxs: number[]; s: number; e: number }[] = [];
  let cur: number[] = [];
  const flush = () => {
    if (!cur.length) return;
    const withT = cur.filter((i) => chars[i].s_ms != null && chars[i].e_ms != null);
    if (withT.length) {
      const s = Math.min(...withT.map((i) => chars[i].s_ms as number));
      const e = Math.max(...withT.map((i) => chars[i].e_ms as number));
      words.push({ idxs: cur, s, e });
    }
    cur = [];
  };
  chars.forEach((c, i) => {
    if (c.s_ms == null || c.e_ms == null) flush();
    else cur.push(i);
  });
  flush();
  // 2) 단어 안 글자가 하나라도 inactive면 그 단어 전체를 제외한다 (단어단위 — 부분 잔존/웅얼 방지).
  //    연속 제외 단어는 한 구간으로 병합. 길이 0 단어(ASR 0폭 토큰)는 이웃 경계로 잇는다(조용한 드롭 금지).
  const ranges: number[][] = [];
  let open: number[] | null = null;
  words.forEach((w, wi) => {
    const excluded = w.idxs.some((i) => editing.inactive.has(i));
    if (!excluded) {
      if (open) { ranges.push(open); open = null; }
      return;
    }
    let s = w.s;
    let e = w.e;
    if (!(e > s)) { // 길이 0/음수 — 인접 보간으로 폭 확보
      const next = words[wi + 1];
      const prev = words[wi - 1];
      if (next && next.s > s) e = next.s;
      else if (prev && s > prev.e) s = prev.e;
      else e = s + 1;
    }
    if (!open) open = [s, e];
    else open[1] = Math.max(open[1], e);
  });
  if (open) ranges.push(open);
  return { ranges, droppedZero: 0 };
};

export const moveTextCaret = (from: number, dir: -1 | 1, chars: Char[]) =>
  Math.max(0, Math.min(chars.length, from + dir));
