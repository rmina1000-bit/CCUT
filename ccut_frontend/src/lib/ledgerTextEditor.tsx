import React from "react";

// [SAVE-INTEGRITY] 순수 로직은 React 무의존 core로 이관(단일 진실원천). 여기선 re-export + 뷰만.
export * from "./ledgerTextEditor.core";

export const TextCaret = () => (
  <span
    aria-hidden
    style={{
      display: "inline-block",
      width: 1,
      height: "1.1em",
      verticalAlign: "-0.15em",
      background: "currentColor",
      marginInline: 1,
    }}
  />
);
