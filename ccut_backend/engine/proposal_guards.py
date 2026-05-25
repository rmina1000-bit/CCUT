# ccut_backend/engine/proposal_guards.py
import logging

logger = logging.getLogger(__name__)

def is_contiguous_to_selected(frag: dict, selected: list[dict], threshold: float = 0.15) -> bool:
    """
    [STEP 10-K-C1-R36] 이미 선택된 같은 source 조각과 시간상 바로 붙어 있으면 True를 반환합니다.
    """
    if not frag or not selected:
        return False

    source_id = frag.get("source_id")
    if not source_id:
        return False

    start = float(frag.get("start", frag.get("start_time", 0.0)) or 0.0)
    end = float(frag.get("end", frag.get("end_time", start)) or start)

    for prev in selected:
        if prev.get("source_id") != source_id:
            continue

        prev_start = float(prev.get("start", prev.get("start_time", 0.0)) or 0.0)
        prev_end = float(prev.get("end", prev.get("end_time", prev_start)) or prev_start)

        # 바로 뒤에 붙는 경우
        if abs(start - prev_end) < threshold:
            return True

        # 바로 앞에 붙는 경우
        if abs(prev_start - end) < threshold:
            return True

    return False


def hard_guard_final_sequence(sequence: list[dict], threshold: float = 0.15, min_gap_sec: float = 1.0) -> list[dict]:
    """
    [STEP 10-K-C1-R37] 최종 sequence에서 같은 source의 연속 조각 및 시간 역행을 검증 제거합니다.
    [TEMPORAL_SORT_BEFORE_GUARD] 가드 평가 전 시간순 정렬을 선행하여 오탐으로 인한 누수를 예방합니다.
    """
    if not sequence:
        return sequence

    # 시간 오름차순 사전 정렬 적용
    sorted_sequence = sorted(sequence, key=lambda x: float(x.get("start", x.get("start_time", 0.0)) or 0.0))
    result = []

    for frag in sorted_sequence:
        source_id = frag.get("source_id")
        start = float(frag.get("start", frag.get("start_time", 0.0)) or 0.0)
        end = float(frag.get("end", frag.get("end_time", start)) or start)

        blocked = False
        for prev in result:
            if prev.get("source_id") != source_id:
                continue

            prev_start = float(prev.get("start", prev.get("start_time", 0.0)) or 0.0)
            prev_end = float(prev.get("end", prev.get("end_time", prev_start)) or prev_start)

            # 시간 역행 방지
            if start + 0.5 < prev_start:
                blocked = True
                break

            # 1. 인접 조각 차단 (끝점과 시작점 붙음)
            if abs(start - prev_end) < threshold:
                blocked = True
                break

            # 2. 역방향 인접 조각 차단
            if abs(prev_start - end) < threshold:
                blocked = True
                break

            # 3. 너무 가까운 조각 차단
            if abs(start - prev_end) < min_gap_sec:
                blocked = True
                break

        if not blocked:
            result.append(frag)

    return result


def remove_contiguous_fragments(fragments: list[dict], min_items: int = 2) -> list[dict]:
    """
    [STEP 10-K-C1-R35] 연속적으로 나열되는 구간을 건너뛰어 다채로운 전환 흐름을 확보합니다.
    """
    if not fragments or len(fragments) <= min_items:
        return fragments

    result = []
    last_end_by_source = {}

    for frag in fragments:
        source_id = frag.get("source_id")
        start = float(frag.get("start", frag.get("start_time", 0.0)) or 0.0)
        end = float(frag.get("end", frag.get("end_time", start)) or start)

        if not result:
            result.append(frag)
            last_end_by_source[source_id] = end
            continue

        prev_end = last_end_by_source.get(source_id)
        is_contiguous = (
            source_id is not None
            and prev_end is not None
            and abs(start - prev_end) < 0.15
        )

        if is_contiguous:
            continue

        result.append(frag)
        last_end_by_source[source_id] = end

    return result if len(result) >= min_items else fragments


def response_level_sequence_guard(sequence: list[dict], min_gap_frames: int = 15) -> list[dict]:
    """
    [CCUT1.0.4 RESPONSE LEVEL HARD GUARD] API 전송 직전 오디오/컷 정합성 최종 보정
    미세 조각 손실을 최소화하기 위해 기본 최소 간격을 15프레임(0.5초)으로 완화했습니다.
    """
    if not sequence:
        return sequence

    result = []

    for frag in sequence:
        source_key = (
            frag.get("source_id")
            or frag.get("source_video")
            or frag.get("source_label")
            or "UNKNOWN"
        )

        start_frame = frag.get("start_frame")
        end_frame = frag.get("end_frame")

        if start_frame is None:
            start = frag.get("start") or frag.get("start_time") or 0
            start_frame = int(round(float(start) * 30))

        if end_frame is None:
            end = frag.get("end") or frag.get("end_time") or 0
            end_frame = int(round(float(end) * 30))

        blocked = False

        for prev in result:
            prev_source_key = (
                prev.get("source_id")
                or prev.get("source_video")
                or prev.get("source_label")
                or "UNKNOWN"
            )

            if prev_source_key != source_key:
                continue

            prev_start = prev.get("start_frame")
            prev_end = prev.get("end_frame")

            if prev_start is None:
                ps = prev.get("start") or prev.get("start_time") or 0
                prev_start = int(round(float(ps) * 30))

            if prev_end is None:
                pe = prev.get("end") or prev.get("end_time") or 0
                prev_end = int(round(float(pe) * 30))

            # 설정된 최소 프레임 갭 이내로 가까우면 중복 편집으로 간주해 제거
            if abs(int(start_frame) - int(prev_end)) <= min_gap_frames:
                blocked = True
                break

            if abs(int(prev_start) - int(end_frame)) <= min_gap_frames:
                blocked = True
                break

        if not blocked:
            result.append(frag)

    return result
