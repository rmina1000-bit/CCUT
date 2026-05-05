# Visual Evidence Cache Policy

## Purpose
Visual analysis (Stage 5) is computationally expensive (~26s per frame). Redundant analysis must be avoided.

## Cache Key Definition
The cache key is a composite hash of:
- `source_id`: Source video identifier.
- `fragment_id`: Temporal segment identifier.
- `keyframe_hash`: Content hash of the image file.
- `model_id`: e.g., `qwen3-vl:4b`.
- `resize_max`: Analysis resolution (384).

## Storage Strategy
1. **Persistent Storage**: Results are stored in `ccut_backend/storage/cache/visual_evidence/`.
2. **Failure Caching**: Timeouts or model errors are also cached as "Transient Failures" for 1 hour to prevent immediate retry-loops.
3. **Lookup Logic**:
   - IF `cache_exists(key)` -> Return cached evidence immediately.
   - ELSE -> Invoke `QwenVLVisualWorker`.

## Mandatory Implementation
- All production calls to `QwenVLVisualWorker` must pass through the `VisualEvidenceCacheLayer`.
- The `skip-existing` flag in probe tools simulates this policy.
- **Status**: **PASS (STEP 10-K)**. Policy defined and integrated into worker logic.
