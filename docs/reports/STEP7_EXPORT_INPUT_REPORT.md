# STEP 7 Export Input 생성 보고서

## 1. 개요
최종 선정된 Proposal 데이터를 기반으로 렌더링 엔진에 투입할 정규화된 데이터셋인 **Export Input**을 생성하는 엔진 및 API를 구현하였습니다.

## 2. 주요 구현 내용

### 2-1. 데이터 모델 및 영구 저장소
- **ExportInputTable 추가**: `export_id`, `source_id`, `proposal_id`, `mode`, `clips`, `total_duration`, `status` 필드를 포함하는 테이블 구축.
- **BAMSManager 연동**: Export Input의 Upsert 저장 및 조회를 위한 CRUD 메서드 구현.

### 2-2. Export Engine (Proposal -> Input 변환)
- **클립 정규화**: Proposal의 `sequence`에 포함된 Semantic Fragments를 순회하며 `fragment_id`, `start`, `end`, `duration`, `order`를 포함하는 `clips` 배열을 생성.
- **Duration 계산**: 조각들의 길이를 합산하여 `total_duration` 산출.
- **보안 준수**: API 외부 응답에서 로컬 파일 시스템의 절대경로를 철저히 배제.

### 2-3. API 엔드포인트
- **POST `/export-input/{proposal_id}`**: 특정 제안을 기반으로 렌더링 입력 데이터 생성.
- **GET `/export-input/{source_id}`**: 소스별 생성된 모든 입력 데이터 조회.
- **GET `/export-input/by-proposal/{proposal_id}`**: 제안별 입력 데이터 조회.

## 3. 검증 결과 (SRC_3BD89C3B)

| 항목 | 결과 | 비고 |
| :--- | :--- | :--- |
| **Export Input 생성** | 정상 완료 | `EXP_EF8DFC_SRC_3BD89C3B` 생성 확인 |
| **Clips 정밀도** | `start: 0.0, end: 30.0` | Semantic Fragment와 정합성 일치 |
| **Total Duration** | 30.0s | 합산 로직 검증 완료 |
| **Status** | `EXPORT_INPUT_READY` | 초기 상태값 확인 |
| **절대경로 노출** | 없음 | 보안 규격 준수 확인 |

## 4. 규격 및 금지사항 준수 확인
- **영상 파일 생성 없음**: 렌더링 직전의 JSON 시퀀스 데이터만 생성함.
- **FFmpeg 미사용**: 실제 미디어 처리는 다음 단계(Render)로 위임.
- **데이터 무결성**: Proposal 및 Semantic Fragment 데이터를 수정하지 않고 읽기 전용으로 활용함.

## 5. 최종 판정: PASS ✅
제안 구성안에서 렌더링 엔진 장착용 입력 데이터로의 전환이 규격에 맞게 완결되었습니다.

---
**보고서 생성 일시**: 2026-04-27 00:25
**파일 경로**: D:\CCUT1.0.4\docs\reports\STEP7_EXPORT_INPUT_REPORT.md
