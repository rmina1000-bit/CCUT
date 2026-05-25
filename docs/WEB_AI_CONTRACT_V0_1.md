# Web AI Contract v0.1

## 역할 정의
Web AI는 편집 주체가 아니라 **Proposal 보강자 / QA 보조자**다.

## 데이터 전송 범위

### Web AI에 보내는 것 (의미 데이터)
- source_id
- fragment_id
- start_time
- end_time
- duration
- summary
- role
- edit_value
- confidence
- evidence_refs
- user_intent
- proposal_context
- past_selection_pattern 요약값

### Web AI에 보내지 않는 것 (개인정보 및 대용량 리소스)
- 원본 영상
- 프레임 이미지
- 오디오 파일
- 전체 대본 원문
- 로컬 절대경로
- 개인정보
- API secret

## 계약 구조 예시 (JSON)
```json
{
  "contract_version": "web_ai_contract_v0.1",
  "source_id": "SRC_xxx",
  "task": "proposal_reasoning",
  "user_intent": {
    "tone": "fast",
    "target_length": 60,
    "must_keep": [],
    "avoid": []
  },
  "fragments": [
    {
      "fragment_id": "SF_xxx",
      "start_time": 0.0,
      "end_time": 12.5,
      "summary": "opening hook",
      "role": "hook",
      "edit_value": 0.82,
      "confidence": 0.9,
      "evidence_refs": ["EB_xxx"]
    }
  ],
  "constraints": {
    "no_video": true,
    "no_audio": true,
    "no_frames": true,
    "local_decision_authority": true
  }
}
```

---

## 영상 생성 AI 계약 v0.1 (신규 — 2026-05-26)

> 상세: `docs/EXTERNAL_AI_VIDEO_API_ROADMAP.md`

### 역할 정의
외부 영상 생성 AI는 **부족한 클립을 채우는 보조 생성자**다.
편집 주체는 CCUT이며, 생성 클립은 일반 소스와 동일하게 취급한다.

### 전송 허용 데이터 (영상 생성용)
- 텍스트 프롬프트 (장면 설명, 분위기, 카메라 방향)
- 참조 스틸 프레임 jpg (최대 3장, FFmpeg으로 추출)
- 생성 길이 (초, 최대 8초)

### 전송 금지 데이터
- 원본 영상 파일
- 원본 오디오
- 사용자 개인정보

### 계약 구조 예시 (Runway Gen-4.5)
```json
{
  "contract_version": "video_gen_contract_v0.1",
  "provider": "runway_gen4.5",
  "task": "b_roll_generation",
  "prompt": "닭이 풀밭을 뛰어다니는 장면, 낮 조명, 핸드헬드, 4초",
  "duration_sec": 4,
  "reference_frames": ["frame_001.jpg"],
  "constraints": {
    "no_original_video": true,
    "max_duration_sec": 8,
    "user_consent_required": true,
    "cost_preview_required": true
  }
}
```

### 비용 고지 원칙
- API 호출 전 반드시 예상 비용 표시
- 사용자 확인 후 실행
- 프로젝트당 최대 60초 한도
