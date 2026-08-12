/**
 * CCUT 제품 화면에서 허용하는 작은 기호 집합.
 * 화면별로 기호를 직접 쓰지 않고 이 표를 통해서만 사용한다.
 */
export const GLYPH = {
  play: "▶",
  pause: "❚❚",
  close: "✕",
  prev: "‹",
  next: "›",
  fold: "▸",
  unfold: "▾",
  grip: "⠿",
} as const;

export type GlyphKey = keyof typeof GLYPH;
