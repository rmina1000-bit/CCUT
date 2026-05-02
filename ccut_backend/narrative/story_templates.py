"""
Narrative Templates Definition.
This file contains structural templates for different storytelling styles.
"""

NARRATIVE_TEMPLATES = {
    "highlight": {
        "template_id": "highlight",
        "title": "하이라이트형",
        "suitable_for": "임팩트 있는 장면 위주의 요약 영상",
        "phases": ["opening", "build", "payoff", "closing"],
        "source_role_preference": "diverse",
        "selection_hint": "가장 높은 market_value 조각 우선 선택",
        "anti_monotony_rule": "연속된 동일 소스 3개 이상 금지"
    },
    "record": {
        "template_id": "record",
        "title": "기록형 / 브이로그",
        "suitable_for": "시간 흐름을 유지하며 현장감을 살리는 영상",
        "phases": ["intro", "chronological_events", "outro"],
        "source_role_preference": "sequential",
        "selection_hint": "시간순(Start Frame) 정렬 유지",
        "anti_monotony_rule": "시간 도약 60초 이상 발생 시 브릿지 필수"
    },
    "mood_montage": {
        "template_id": "mood_montage",
        "title": "감성 몽타주",
        "suitable_for": "분위기와 시각적 미학을 강조하는 영상",
        "phases": ["setup", "variation", "climax", "fading"],
        "source_role_preference": "topic_consistency",
        "selection_hint": "유사 토픽 조각 그룹화",
        "anti_monotony_rule": "급격한 오디오 에너지 변화 지양"
    },
    "vlog": {
        "template_id": "vlog",
        "title": "일상 브이로그",
        "suitable_for": "개인적인 스토리와 일상을 공유하는 스타일",
        "phases": ["hook", "narrative_1", "narrative_2", "conclusion"],
        "source_role_preference": "balanced",
        "selection_hint": "말소리(Transcript) 포함 조각 우선",
        "anti_monotony_rule": "무음 구간 5초 이상 지속 금지"
    },
    "comparison": {
        "template_id": "comparison",
        "title": "대조 / 비교형",
        "suitable_for": "두 개 이상의 대상을 비교하거나 대조하는 영상",
        "phases": ["target_a", "target_b", "side_by_side", "conclusion"],
        "source_role_preference": "paired",
        "selection_hint": "동일 역할(Role) 조각 간 교차 배치",
        "anti_monotony_rule": "한쪽 타겟에만 70% 이상 할당 금지"
    },
    "informational": {
        "template_id": "informational",
        "title": "정보 전달형",
        "suitable_for": "지식이나 정보를 설명하는 교육적 영상",
        "phases": ["topic_intro", "key_point_1", "key_point_2", "summary"],
        "source_role_preference": "clarity",
        "selection_hint": "Edit Value(Context) 점수 높은 조각 우선",
        "anti_monotony_rule": "핵심 포인트 간 전개 속도 일정 유지"
    }
}
