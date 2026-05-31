// src/features/pbe/pbeModel.ts

// 진실원천: 초 단위 실수를 기준으로 핵심 정보 식별
export interface PbeClip {
  fragment_id: string;
  source_id: string;
  source_video: string;
  start: number;   // 초 단위 시작 (진실원천)
  end: number;     // 초 단위 종료 (진실원천)
  selection_state: string;
  status: string;
}

// 파생 계산 함수들 (상태로 관리하지 않고 렌더링 시점에 즉석 유추)
export const duration = (c: PbeClip): number => {
  return c.end - c.start;
};

export const toFrame = (sec: number, fps: number): number => {
  return Math.round(sec * fps);
};

export const toPixel = (sec: number, originSec: number, pxPerSec: number): number => {
  return (sec - originSec) * pxPerSec;
};

// 입력 정규화 함수
export const normalizeToPbeClip = (raw: any, defaultFps = 30.0): PbeClip => {
  const fragment_id = raw.fragment_id || "";
  const source_id = raw.source_id || "";
  const source_video = raw.source_video || "";
  const selection_state = raw.selection_state || "S";
  const status = raw.status || "";

  // fps 결정
  let fps = Number(raw.fps);
  if (!fps || !Number.isFinite(fps) || fps <= 0) {
    fps = defaultFps;
    console.warn(`[PbeModel] Invalid or missing fps in raw fragment ${fragment_id}. Falling back to default: ${defaultFps}`);
  }

  // start 초 계산 우선순위:
  // 1. raw.start_time
  // 2. raw.start
  // 3. raw.start_frame / fps 역산
  let start = 0;
  if (raw.start_time !== undefined && raw.start_time !== null) {
    start = Number(raw.start_time);
  } else if (raw.start !== undefined && raw.start !== null) {
    start = Number(raw.start);
  } else if (raw.start_frame !== undefined && raw.start_frame !== null) {
    start = Number(raw.start_frame) / fps;
  }

  // end 초 계산 우선순위:
  // 1. raw.end_time
  // 2. raw.end
  // 3. raw.end_frame / fps 역산
  // 4. (start + duration) fallback
  let end = start;
  if (raw.end_time !== undefined && raw.end_time !== null) {
    end = Number(raw.end_time);
  } else if (raw.end !== undefined && raw.end !== null) {
    end = Number(raw.end);
  } else if (raw.end_frame !== undefined && raw.end_frame !== null) {
    end = Number(raw.end_frame) / fps;
  } else if (raw.duration !== undefined && raw.duration !== null) {
    end = start + Number(raw.duration);
  }

  return {
    fragment_id,
    source_id,
    source_video,
    start,
    end,
    selection_state,
    status
  };
};

// PBE playhead coordinate conversion functions (D4-A single source of truth)
export const playheadToPixel = (playheadSec: number, originSec: number, pxPerSec: number): number => {
  return (playheadSec - originSec) * pxPerSec;
};

export const pixelToPlayhead = (px: number, originSec: number, pxPerSec: number): number => {
  return originSec + px / pxPerSec;
};

export const clampPlayhead = (sec: number, startSec: number, endSec: number): number => {
  return Math.max(startSec, Math.min(endSec, sec));
};



