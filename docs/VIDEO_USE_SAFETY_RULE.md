# Video Use 코드 및 데이터 안전 규칙

## 절대 금지
- video-use 코드 복사 (timeline_view.py, render.py, self_eval.py 등)
- **Narrative Consultation 과정에서 외부 AI에 원본 영상/오디오 직접 전송 금지**
- StoryIntent 확정 전 대규모 렌더링 시작 금지

## 허용
- FFmpeg 표준 명령어 및 개념 참고
- CCUT 독자 구현 및 로컬 분석 데이터 활용
- **StoryIntent, 분석 메타데이터 등 정제된 텍스트 데이터의 외부 AI 어댑터 활용 (사용자 동의 시)**

## Narrative Consultation Layer Safety
- 사용자의 자연어 대화 데이터는 로컬 DB에 우선 저장한다.
- 분석된 조각(Fragment) 정보는 ID와 요약 텍스트로만 취급한다.
