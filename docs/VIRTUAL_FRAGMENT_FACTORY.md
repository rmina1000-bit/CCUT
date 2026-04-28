# Virtual Fragment Factory

## 정의
큰 영상을 수천 개 논리 Room으로 나누어 신호·의미 재료를 생산하는 구조.

## 핵심 메커니즘
실제 프로세스를 수천 개 띄우는 것이 아니라, **논리 Room + 제한된 worker slot + queue + Resource Governor 정책**으로 운영한다.

## Room 예시
- audio_slice_room
- frame_slice_room
- keyframe_room
- rms_room
- motion_room
- scene_room
- transcript_room
- pattern_room
- boundary_room
- semantic_room
- proposal_material_room

## 구현 가이드라인 (STEP 10+)
- 현재 구현 대상 아님.
- STEP 10에서는 문서/시뮬레이션 후보까지만 확정.
- Resource Governor 본구현 금지.
- Render / ExportInput / UI 파이프라인 영향 금지.
