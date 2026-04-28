# Resource Governor Simulation v0

## 목적
Virtual Fragment Factory가 생성한 Task Queue를 Resource Governor가 리소스 상태(CPU, GPU, RAM, Disk) 및 정책(Threshold, Slot Limit)에 따라 어떻게 관리(할당, 지연, 제한)하는지 독립 시뮬레이션으로 검증한다.

## 범위
- `factory_result.json` 데이터 로드
- Resource Policy v0 정의
- Mock Resource 상태(Scenario) 정의 및 적용
- Governor Decision Log 생성
- `governor_result.json` 및 `governor_summary.json` 저장

## 비범위 (Out of Scope)
- 실제 시스템 리소스(psutil 등) 모니터링
- 실제 리소스 제어(Process priority, CGroups 등) 구현
- 기존 CCUT 파이프라인 연동
- 백엔드 main.py 수정

## 구조 정의

### Resource Policy v0
```json
{
  "cpu_high_threshold": 85,
  "gpu_vram_high_threshold": 90,
  "ram_high_threshold": 80,
  "disk_io_high_threshold": 85,
  "default_worker_slot_count": 8,
  "min_worker_slot_count": 2,
  "max_worker_slot_count": 8,
  "throttle_mode": "simulation_only"
}
```

### Mock Resource Scenarios
- **NORMAL**: 모든 리소스가 Threshold 미만. 모든 Task 할당(ASSIGN).
- **PRESSURE**: 일부 리소스가 Threshold 근접. 작업 지연(DELAY) 또는 슬롯 제한 발생 가능.
- **OVERLOAD**: 리소스가 Threshold 초과. 적극적인 제한(THROTTLE/SKIP) 발생.

### Governor Decision 구조
- `decision_id`: GOV_DEC_xxxxxx
- `action`: ASSIGN, DELAY, THROTTLE, REDUCE_SLOT, SKIP_SIMULATION_ONLY
- `reason`: resource_within_policy, cpu_threshold_exceeded 등

## 검증 기준
- 모든 Task에 대해 Governor Decision이 기록되는가?
- OVERLOAD 시나리오에서 DELAY 또는 THROTTLE이 실제로 발생하는가?
- 동시 실행 Task 수가 정책상 `max_worker_slot_count`를 초과하지 않는가?
- 시뮬레이션 결과가 기존 CCUT 핵심 파일에 영향을 주지 않는가?
