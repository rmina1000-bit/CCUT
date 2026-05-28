# 비주얼 및 모션 에비던스 보강 스펙 (Visual & Motion Evidence Specification)

본 문서는 CCUT 로컬 시스템의 비주얼 객체 추적, 인물 얼굴 인식 및 프레임간 모션 분석 메타데이터 스펙을 정의합니다.

---

## 1. 현재 로컬 데이터베이스 신호의 한계

로컬 DB(`ccut_app.db`)를 정밀 감사한 결과, 비주얼 및 모션 분석 신호의 결핍이 다음과 같이 확인되었습니다:
- **비주얼 에비던스 전무**: DB 내에 객체 감지 로그(YOLO 결과)나 얼굴 인식 결과 등 비주얼 인물 감지 데이터가 전혀 존재하지 않습니다.
- **모션 점수 소실 (Collapse)**: `evidence_board` 테이블의 `motion_score` 컬럼 값이 모든 영상에 대해 일괄 `0.0000`으로 기록되어 있어, 광학 흐름(Optical Flow) 연산 값이 실상 누락되었습니다.
- **자막/음성 전사 데이터 부족**: Whisper ASR 실행 결과, 28개 등록 영상 중 24개 영상이 침묵 또는 무음 판정을 받아 전사 텍스트가 `0`개로 저장되어 있습니다.
- **Scenery(풍경) 분류 한계**: 현재 Scenery 점수는 `1.0 - speech_score - motion_score` 방식을 통해 역산 추정하는 수준에 불과하여, 실제 정적인 풍경 컷을 정확하게 가려내지 못합니다.

---

## 2. 보강 설계 대상 메타데이터 스키마

사용자 의도를 미세 조각 단위로 정밀 추적하기 위해, 수집 단계에서 적재해야 할 메타데이터 스펙을 정의합니다:

### A. 비주얼 객체 메타데이터 (`visual_objects`)
화면 내 객체의 종류와 좌표를 추출하여 인물 외 B-Roll 등을 필터링하기 위한 필드입니다.
- `class`: 감지된 객체 명칭 (예: car, dog, tree).
- `confidence`: 인식 신뢰도 확률 값.
- `box`: 화면 내 상대 좌표 `[x_min, y_min, x_max, y_max]`.

### B. 인물 및 얼굴 감지 정보 (`human_presence` & `face_presence`)
화면 내 사람의 노출도 및 얼굴 포커스 가중치를 계산합니다.
- `human_detected`: 인물 존재 여부 (True/False).
- `human_count`: 감지된 인물 수.
- `human_ratio`: 화면 전체 면적 대비 인물이 차지하는 면적 비율.
- `face_detected`: 얼굴 검출 여부.
- `faces`: 얼굴 영역 좌표, 신뢰도 및 표정 정보 리스트.

### C. 모션 및 하이라이트 지표 (`motion_intensity` & `audio_peak_db` & `scenery_score`)
- `motion_intensity`: 프레임 간 화소 변위량(광학 흐름 벡터 크기)의 평균치.
- `audio_peak_db`: 데시벨(dB) RMS peak 지점 탐지로 임팩트 오디오 검출.
- `scenery_score`: 자연, 실외, 빌딩 등 풍경 장면 검출에 대한 CNN 확률값.
- `highlight_signal`: 모션 및 오디오 크기를 복합 연산한 하이라이트 신뢰 지수.

---

## 3. 데이터 통합 파이프라인 흐름

로컬 영상 적재 시 분석 파이프라인은 다음과 같이 설계됩니다:

```
  에비던스 보드 (Evidence Board - 분석 워커가 프레임 단위 메타데이터 기록)
  → 의미 조각 (Semantic Fragment - 20초 단위로 요약하여 UI 표시)
  → 마이크로 캔디데이트 (Micro Candidate - 2~6초 세부 컷 분할 및 캐싱)
  → 비주얼/음성/모션 개별 점수 보강 (캐싱된 메타데이터 기준 실시간 채점)
  → 제안 생성 (Proposal - ProposalEngine이 사용자 가중치를 조합해 클립 선택)
```

---

## 4. 개발 범위 경고

> [!WARNING]
> - 백엔드 내에 실제 YOLOv8, FaceNet 얼굴 검출기, 광학 흐름 연산기 및 오디오 RMS Peak 탐지기를 구현하는 일은 본 단계의 **범위 외(HOLD)**입니다.
> - 본 문서와 스크립트는 시뮬레이션 및 아키텍처 설계를 검증하기 위한 것이며, 실제 본체 코드와 DB 스키마는 수정되지 않습니다.
