import { ResolvedFragment, getFragmentTimeRange } from "./proposalFragmentResolver";

/**
 * [STEP 10-I.2] Physical EDL Builder
 * 렌더링에 필요한 물리적 정보를 담은 클립 데이터 구조를 정의합니다.
 */

export interface PhysicalClip {
  order: number;
  source_id: string;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  fragment_id: string;
  display_id: string;
}

/**
 * 1. 클립 유효성 검사 강화
 * source_id 존재 여부, 시간 정합성(end > start), 양수의 재생 시간을 검사합니다.
 */
export const validateExportClips = (clips: PhysicalClip[]): boolean => {
  if (!clips || clips.length === 0) return false;
  return clips.every(c => 
    c.source_id && 
    c.source_id !== "" &&
    c.duration_sec > 0 && 
    c.end_sec > c.start_sec
  );
};

/**
 * 2. Physical EDL 생성기
 * fragment_id가 아닌 source_id + start_sec + end_sec 기반으로 생성합니다.
 * source_id가 없을 경우 강제 fallback 대신 빈 문자열을 넣어 validation에서 걸러지게 합니다.
 */
export const buildExportClipsFromResolvedFragments = (
  resolvedFragments: ResolvedFragment[]
): PhysicalClip[] => {
  return resolvedFragments.map((f, idx) => {
    const { start, end } = getFragmentTimeRange(f);
    const duration = end - start;

    return {
      order: idx,
      // source_id fallback 제거 (A 강제 할당 금지)
      source_id: (f as any).source_id || f.source_video || "", 
      start_sec: Number(start.toFixed(3)),
      end_sec: Number(end.toFixed(3)),
      duration_sec: Number(duration.toFixed(3)),
      fragment_id: f.fragment_id,
      display_id: (f as any).display_id || f.fragment_id,
    };
  });
};
