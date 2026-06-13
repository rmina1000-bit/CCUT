/**
 * pbeEngine.ts — Compatibility Shim
 *
 * 이 파일은 과거 호출자들의 import 경로(@/lib/pbeEngine)를 유지하기 위한 re-export shim 이다.
 *
 * 실제 구현 이관처:
 *   - 공용 유틸: @/lib/fragmentIdentity
 *   - PBE 전용 연산: @/features/pbe/pbeBoundaryOps
 *
 * 호출자:
 *   - src/components/FragmentMap.tsx (LOCK · getUid 사용)
 *   - src/pages/Index.tsx (getUid, recalcDisplayIds 사용)
 *   - 기타 기존 코드
 *
 * LOCK 파일을 수정하지 않기 위해 shim 유지.
 * 신규 코드는 이 shim 경유 대신 @/lib/fragmentIdentity 또는
 * @/features/pbe/pbeBoundaryOps 를 직접 import 할 것.
 */

export {
    getUid,
    getDisplayId,
    generateUid,
    recalcDisplayIds,
    commitFragments
} from "./fragmentIdentity";
