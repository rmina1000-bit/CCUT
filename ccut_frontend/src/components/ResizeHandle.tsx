import React from "react";

/**
 * [DRAG-ONE 2026-08-02 국장 지시] 드래그바는 여기 하나뿐이다.
 *
 * 왜 만들었나: 창 경계 드래그바가 네 곳에 각자 있었고, 폭·색·안쪽 선·커서가
 *   따로 적혀 있었다. 국장이 "조금 더 넓게" 한 번 말하면 실행자가 네 곳을
 *   찾아다녀야 했고, 관제실에서는 서로 겹쳐 잡히지도 않았다.
 *   ★새 드래그바가 필요하면 이 파일을 쓴다. 새로 만들지 마라.
 *   ★폭·색·두께를 바꾸려면 이 파일만 고친다. 다른 곳은 손대지 않는다.
 *
 * 쓰는 법 — 드래그 로직(mousemove/mouseup)은 호출부가 그대로 갖는다.
 *   이 부품은 '손잡이의 생김새와 잡히는 넓이'만 책임진다.
 *     <ResizeHandle active={isNavDragging} onStart={() => setIsNavDragging(true)} />
 */

/** 잡히는 폭(px). 6px 은 잡기 힘들다는 국장 실사용 불만으로 12px 이 됐다. */
export const DRAG_HANDLE_W = 12;
/** 안쪽에 보이는 선의 두께(px). 넓게 잡히되 눈에는 얇게 보이는 것이 목적이다. */
const INNER_W = 2;

export interface ResizeHandleProps {
  /** 드래그 중인가 — 색이 진해진다 */
  active?: boolean;
  /** 손잡이를 누른 순간. 이후 mousemove/mouseup 은 호출부가 처리한다 */
  onStart: (e: React.MouseEvent) => void;
  /**
   * 배치 방식.
   *   "flow"     — 두 칸 사이에 형제로 놓인다(메뉴창·채팅창·아카이브). 기본값.
   *   "overlay"  — 이미 자리를 차지한 패널의 가장자리에 겹쳐 놓는다(관제실 AI 보조).
   *                ★overlay 는 음수 마진을 쓰지 않는다. 그것이 관제실에서 옆 손잡이와
   *                  서로 물려 안 잡히던 원인이었다.
   */
  variant?: "flow" | "overlay";
  /** overlay 일 때 어느 쪽 가장자리에 붙는가 */
  side?: "left" | "right";
  title?: string;
}

export const ResizeHandle: React.FC<ResizeHandleProps> = ({
  active = false,
  onStart,
  variant = "flow",
  side = "left",
  title = "드래그하여 폭 조절",
}) => {
  const base = "flex items-center justify-center cursor-col-resize group transition-colors";
  const tone = active ? "bg-primary/15" : "hover:bg-primary/8";

  const style: React.CSSProperties =
    variant === "overlay"
      ? { width: DRAG_HANDLE_W, position: "absolute", top: 0, bottom: 0, [side]: 0, zIndex: 20 }
      : { width: DRAG_HANDLE_W };

  return (
    <div
      className={`${variant === "flow" ? "flex-shrink-0 " : ""}${base} ${tone}`}
      style={style}
      title={title}
      onMouseDown={(e) => {
        e.preventDefault();
        onStart(e);
      }}
    >
      {/* 넓게 잡히되 얇게 보인다 — 잡는 넓이와 보이는 굵기는 다른 문제다 */}
      <div
        className={`rounded-full transition-all duration-150 ${
          active
            ? "bg-primary/60 h-16"
            : "bg-border/40 h-10 group-hover:bg-primary/40 group-hover:h-14"
        }`}
        style={{ width: INNER_W }}
      />
    </div>
  );
};

export default ResizeHandle;
