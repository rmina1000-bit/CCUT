# Free Edit Form Specification (V1.0)

CCUT 무료 사용자가 전문 지식 없이도 편집 방향을 지정할 수 있는 입력 폼의 규격입니다. 본 폼은 외부 AI 없이도 규칙 기반으로 작동하도록 설계되었습니다.

## 1. 폼 항목 정의

### 1.1. 영상 목적 (Purpose)
- 유튜브 본편
- 쇼츠/릴스
- 제품 리뷰
- 강의/설명
- 브이로그
- 인터뷰
- 그냥 보기 좋게 줄이기

### 1.2. 완성 길이 (Target Duration)
- 30초 이내
- 1분 이내
- 3분 정도
- 5분 정도
- 원본의 절반 정도
- CCUT 추천

### 1.3. 편집 스타일 (Pacing & Style)
- 빠르고 강하게 (Fast & Strong)
- 자연스럽게 (Natural)
- 설명을 잘 살리기 (Informative)
- 웃긴 부분 살리기 (Funny)
- 감성 있게 (Atmospheric)
- 깔끔하고 무난하게 (Standard)

### 1.4. 초반 도입 방식 (Opening Strategy)
- 제일 강한 장면 먼저 (Strong Hook)
- 결론 먼저 (Conclusion First)
- 자연스럽게 시작 (Natural Start)
- 웃긴 장면 먼저 (Funny Hook)
- CCUT 추천 (Default)

### 1.5. 줄일 부분 (Reduce Rules) - 다중 선택
- 긴 침묵
- 반복 설명
- 어색한 말
- 준비 과정 (셋업)
- 긴 배경 설명
- 광고처럼 느껴지는 말

### 1.6. 살릴 부분 (Preserve Rules) - 다중 선택
- 웃음/리액션
- 실제 사용 장면
- 중요한 설명
- 감정 표현
- 결론/후기
- 실수/재미있는 장면

### 1.7. 자막 방식 (Subtitle Policy)
- 없음
- 핵심 자막만 (Key only)
- 전체 자막 (Full)
- 쇼츠 스타일 큰 자막 (Big & Bold)

### 1.8. 제안 방식 (Proposal Mode)
- 추천안 1개
- A/B 두 가지 안
- 빠른 초안 (Speed-focused)
- 정밀 초안 (Quality-focused)

## 2. 설계 원칙
- **AI-free Logic**: 외부 LLM 호출 없이, 선택된 항목에 대응하는 고정된 규칙(Rule-based)을 적용합니다.
- **Natural Language Focus**: "L-Cut", "Jump Cut" 등 전문 용어 대신 사용자가 이해하기 쉬운 일상 단어를 사용합니다.
- **Smart Defaults**: 사용자가 고민하지 않도록 "CCUT 추천" 옵션을 기본값으로 제공합니다.
