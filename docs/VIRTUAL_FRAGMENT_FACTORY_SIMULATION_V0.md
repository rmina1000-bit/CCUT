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

## 구조 정의 (STEP 10-C 보정 완료)

### 1. source 계약
```json
{
  "source_id": "SRC_SIM_001",
  "duration_sec": 600,
  "segment_unit_sec": 2,
  "source_type": "mock_video",
  "status": "READY"
}
```

### 2. room 계약
```json
{
  "room_id": "ROOM_SIM_000001",
  "source_id": "SRC_SIM_001",
  "room_type": "frame_slice_room",
  "time_range": {
    "start_sec": 0,
    "end_sec": 2
  },
  "status": "READY"
}
```

### 3. task 계약
```json
{
  "task_id": "TASK_SIM_000001",
  "room_id": "ROOM_SIM_000001",
  "source_id": "SRC_SIM_001",
  "task_type": "extract_mock_frame_signal",
  "assigned_worker_slot": "WORKER_SLOT_01",
  "status": "DONE"
}
```

### 4. worker_slot 계약
```json
{
  "worker_slot_id": "WORKER_SLOT_01",
  "slot_index": 1,
  "worker_type": "mock_worker",
  "status": "IDLE",
  "processed_task_count": 38
}
```

### 5. evidence 계약
```json
{
  "evidence_id": "EV_SIM_000001",
  "source_id": "SRC_SIM_001",
  "room_id": "ROOM_SIM_000001",
  "task_id": "TASK_SIM_000001",
  "evidence_type": "mock_keyframe_signal",
  "time_range": {
    "start_sec": 0,
    "end_sec": 2
  },
  "value": {
    "score": 0.72
  },
  "status": "READY"
}
```

### 6. summary 계약 (검증 필드)
- `contract_check`: PASS/FAIL
- `source_room_link_check`: PASS/FAIL
- `room_task_link_check`: PASS/FAIL
- `task_evidence_link_check`: PASS/FAIL
- `worker_task_link_check`: PASS/FAIL
- `time_range_check`: PASS/FAIL

## 검증 기준
- 모든 Room이 최종적으로 DONE 상태가 되는가?
- 생성된 Evidence가 Source 및 Room과 ID로 올바르게 연결되는가?
- 시뮬레이션 결과가 기존 CCUT 핵심 파일(main.py, render_engine.py 등)에 영향을 주지 않는가?
- 결과 JSON 데이터가 Common Core 스펙을 준수하는가?
