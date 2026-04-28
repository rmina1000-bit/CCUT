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
