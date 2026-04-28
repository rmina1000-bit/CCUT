# Virtual Fragment Factory Simulation v0

## 목적
Virtual Fragment Factory의 논리 구조(Room, Task, Slot, Queue)가 Common Core 데이터 계약과 정합성을 유지하는지 독립적인 시뮬레이션으로 검증한다.

## 범위
- Mock Source 생성
- Logical Room 추상화 및 다수 생성
- Task Queue 및 제한된 Worker Slot 기반 처리 시뮬레이션
- Mock Evidence 생성 및 결과 JSON 저장
- Common Core ID 계약 준수 여부 확인

## 비범위 (Out of Scope)
- 실제 영상 파일 접근 및 분석
- 실제 AI 모델 호출
- 실제 Resource Governor 로직 구현
- 기존 CCUT 파이프라인(Upload -> Render) 연결
- 프론트엔드 UI 연동

## 구조 정의

### Logical Room 구조
- `room_id`: ROOM_SIM_xxxxxx
- `room_type`: frame_slice_room, audio_slice_room 등
- `status`: PENDING, RUNNING, DONE, FAILED
- `tasks`: 해당 Room에 할당된 Task 목록

### Task Queue 구조
- 선입선출(FIFO) 기반의 논리 큐
- `worker_slot_count`에 의해 동시 실행 Task 수 제한 (시뮬레이션상)

### Common Core ID 계약
- `source_id`: SRC_SIM_xxx
- `room_id`: ROOM_SIM_xxx
- `task_id`: TASK_SIM_xxx
- `evidence_id`: EV_SIM_xxx

## 검증 기준
- 모든 Room이 최종적으로 DONE 상태가 되는가?
- 생성된 Evidence가 Source 및 Room과 ID로 올바르게 연결되는가?
- 시뮬레이션 결과가 기존 CCUT 핵심 파일(main.py, render_engine.py 등)에 영향을 주지 않는가?
- 결과 JSON 데이터가 Common Core 스펙을 준수하는가?
