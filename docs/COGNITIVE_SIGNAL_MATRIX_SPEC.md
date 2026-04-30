# Cognitive Signal Matrix Specification (V1.0)

## 1. Overview
Cognitive Signal Matrix(CSM)는 CCUT의 핵심 분석 아키텍처로, 영상을 시간축(Row)과 다차원 인지 신호(Column)의 매트릭스로 분해하여 정밀한 의미 조각(Semantic Fragment)을 추출하는 구조입니다.

## 2. 핵심 정의
- **Row (시간축)**: 영상을 일정 시간/프레임 단위로 쪼갠 구간.
- **Column (인지 신호)**: 분석 대상이 되는 독립적인 신호 종류 (Speech, Scene, Motion 등).
- **Cell (작업 유닛)**: 특정 시간 구간(Row)에서 특정 신호(Column)를 추출하는 최소 분석 단위. 가상 조각 공장(Virtual Fragment Factory)의 작업방(Logical Room)에 매핑됩니다.
- **Output (의미 조각)**: 여러 Cell의 신호 값을 통합 분석하여 도출된 편집 가능한 조각.

## 3. Row Size 가이드라인
| 유형 | 크기 | 설명 | 비고 |
|------|------|------|------|
| **Standard** | 2s | 정밀도와 속도의 최적 균형점 | **기본 권장** |
| **Light** | 5s | 무료/경량 분석, 빠른 초안 생성용 | 저사양 권장 |
| **Precision** | 1s | 전문가용 정밀 분석, 아카이브용 | 고사양 필요 |

## 4. 데이터 통합 및 조각화 흐름
1. **Cell 생성**: 설정된 Row Size에 따라 모든 유효 Column에 대해 분석 태스크 할당.
2. **신호 축적**: 각 Cell에서 생산된 Evidence 데이터가 Matrix에 적재.
3. **패턴 분석**: 인접한 Row들 간의 신호 변화(Gradient) 및 동시 발생(Co-occurrence) 분석.
4. **조각 경계 결정**: 신호 밀집도 및 변화율이 임계치를 넘는 지점을 의미 조각의 경계로 설정.

## 5. 설계 원칙
- **Scalability**: 새로운 인지 신호(Column)를 추가해도 기존 구조가 깨지지 않아야 함.
- **Parallelism**: 각 Cell은 독립적으로 처리 가능하며, Worker Slot에 따라 병렬 실행됨.
- **Isolation**: 분석 로직은 렌더링 파이프라인과 완전히 분리됨.
