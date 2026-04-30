# Free Version MVP Specification (V1.0)

CCUT 무료버전은 외부 AI 의존 없이 로컬 자원만으로 실용적인 편집 결과물을 만들어낼 수 있는 "조각 기반 편집 보조기"를 지향합니다.

## 1. 무료버전 정의
- **정의**: 사용자의 로컬 환경에서 Cognitive Signal Matrix 분석을 통해 의미 있는 조각(Fragment)을 제안하고, 이를 기반으로 컷 편집을 완성하는 도구.
- **철학**: "무료는 편집한다. 유료는 기억하고 조언한다."

## 2. 무료 핵심 흐름 (End-to-End)
1. 영상 업로드 (Local)
2. 로컬 분석 (Cognitive Signal Matrix)
3. 무료 편집 폼 선택 (Rule-based)
4. Edit Instruction JSON 생성
5. 조각 추천 (A/B 안)
6. 사용자 조각 개입 (살리기/빼기/순서/트림)
7. Video-use 품질규칙 적용 (Word Snap, Pop Guard)
8. 로컬 렌더 (Render Engine)
9. mp4 출력

## 3. 무료 포함 기능 상세
- **입력**: 영상 업로드, 메타데이터 추출.
- **분석**: Cognitive Signal Matrix 기본 분석 (Light 모드).
- **기획**: 무료 편집 폼(8종 항목), Form → Instruction 변환.
- **조각 관리**: 조각 생성/조회, 조각 살리기/빼기, 순서 조정, 트림(짧게 줄이기).
- **추천**: 기본 A/B 추천 초안 생성.
- **품질**: Word Boundary Snap, Render QA, Audio Pop Guard.
- **렌더**: 기본 자막 입히기, 로컬 mp4 출력.

## 4. 기본 분석 정책 (Baseline)
- **추천**: `ccut_matrix_light` (row_size_sec = 2, worker_slots = 8)
- **Fallback**: 저사양 기기인 경우 `video_use_speech_only` 또는 `row_size_sec = 5`로 자동 전환.

## 5. MVP 완료 기준 (Completion Criteria)
1. 영상 업로드 가능 여부.
2. 로컬 분석(Matrix) 정상 작동 여부.
3. 무료 폼 입력 및 유효성 검사.
4. Edit Instruction JSON 정상 생성.
5. 조각 추천 엔진 작동.
6. 사용자가 조각별 살리기/빼기/순서 조작 가능.
7. 로컬 렌더 엔진 구동.
8. Render QA 규칙(말 잘림 등) 자동 검수.
9. 최종 mp4 파일 생성 및 재생 가능성.
10. **외부 AI 연결 없이 위 1~9 과정이 완결(End-to-End)될 것.**
