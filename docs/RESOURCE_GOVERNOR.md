# RESOURCE GOVERNOR v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 정의
로컬 자원(CPU/GPU/RAM/Disk)을 적극 활용하되 과부하를 방지하는 스케줄러다.

## 정책
| 조건 | 조치 |
|---|---|
| CPU 85% 이상 | Whisper Worker 감소 |
| GPU VRAM 90% 이상 | Batch size 50% 축소 |
| RAM 80% 이상 | L1 Cache eviction |
| Disk I/O 병목 | Queue throttle |
| UI latency 500ms 이상 | Background worker 우선순위 하향 |
| 장시간 작업 60초 이상 | Partial 결과 우선 표시 |

## Worker 우선순위
1. Proxy Generator / Segment Partitioner
2. Whisper / Audio Worker
3. Scene / Motion / Keyframe Worker
4. Semantic Worker(Qwen)
5. Cache Writer / Fingerprint Generator

## GPU 사용
- NVIDIA: NVENC
- AMD: AMF
- Intel: QSV
- GPU 불가 시 CPU fallback
- Qwen/VLM은 GPU 우선, GPU 불가 시 rule-based fallback 또는 Worker skip

## PASS
- 사용률 로그 존재
- worker 수 조절 가능
- batch size 조절 가능
- 과부하 시 앱이 멈추지 않음
