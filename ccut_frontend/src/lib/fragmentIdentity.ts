/**
 * fragmentIdentity.ts
 * Fragment 식별자 공용 유틸리티
 *
 * 사용처:
 *   - src/components/FragmentMap.tsx (LOCK · via pbeEngine shim)
 *   - src/pages/Index.tsx (직접 또는 via pbeEngine shim)
 *   - src/features/pbe/PrecisionBoundaryEditor.tsx
 *   - src/features/pbe/pbeBoundaryOps.ts
 *
 * 원 출처: 구 src/lib/pbeEngine.ts 에서 PBE 외부에서도 사용되는 공용 유틸만 분리 이관.
 */

import { Fragment } from "@/data/fragmentData";

export function getUid(f: Pick<Fragment, "fragment_uid" | "fragment_id">): string {
    return f.fragment_uid ?? f.fragment_id;
}

export function getDisplayId(f: Pick<Fragment, "display_id" | "fragment_id">): string {
    return f.display_id ?? f.fragment_id;
}

/**
 * [DISPLAY-NAME] source_id → 제목부 레지스트리.
 * 과거 스냅샷(저장된 제안 resolved_aliases·ui_state 편집상태)에서 복원된 조각은
 * display_name이 없다. 백엔드 권위 이름을 소비하는 순간(mapFragments) 제목부를
 * 등록해 두면 displayName()이 렌더 시점에 스스로 치유한다 — 경로별 땜빵 불필요.
 */
const sourceTitleRegistry = new Map<string, string>();
export function registerSourceTitle(sourceId?: string, displayNameOrTitle?: string) {
    if (!sourceId || !displayNameOrTitle) return;
    const title = String(displayNameOrTitle).split(" · ")[0].trim();
    if (title) sourceTitleRegistry.set(sourceId, title);
}

/**
 * [DISPLAY-NAME] 사용자용 조각 주이름 — 단일 진실원 읽기.
 * 백엔드(fragment_show.display_name)가 만든 "원본제목 · m:ss–m:ss"를 그대로 쓴다.
 * 없으면 레지스트리 제목부 + 실제 구간으로 조립(자가치유). 폴백에서도
 * raw ID(SF_/SRC_)는 절대 반환하지 않는다 — 최후엔 시간 구간만 사람 말로.
 */
export function displayName(
    f: Pick<Fragment, "display_name" | "start_frame" | "end_frame"> & { source_id?: string },
): string {
    if (f.display_name) return f.display_name;
    const fmt = (fr?: number) => {
        const s = Math.max(0, Math.round((fr ?? 0) / 30));
        return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    };
    const title = f.source_id ? sourceTitleRegistry.get(f.source_id) : undefined;
    return `${title ?? "조각"} · ${fmt(f.start_frame)}–${fmt(f.end_frame)}`;
}

/**
 * [DISPLAY-NAME] 사용자용 파일(원본) 이름 — 확장자 제거 통일.
 * raw ID(SRC_) 폴백 금지.
 */
export function sourceDisplayName(title?: string | null): string {
    const base = (title || "").trim().replace(/\.[A-Za-z0-9]{2,4}$/, "");
    return base || "이름 없는 영상";
}

/**
 * [DISPLAY-NAME] 분할/트림으로 구간이 바뀐 파생 조각의 이름.
 * 권위 이름의 제목부는 승계하고 시간부만 새 구간으로 다시 쓴다
 * (제목은 프론트가 짓지 않는다 — 명칭 로직은 이 모듈 하나에만 산다).
 */
export function rangeDisplayName(
    baseDisplayName: string | undefined,
    startSec?: number,
    endSec?: number,
): string | undefined {
    if (!baseDisplayName) return undefined;
    const title = String(baseDisplayName).split(" · ")[0];
    const fmt = (v?: number) => {
        const s = Math.max(0, Math.round(v ?? 0));
        return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    };
    return `${title} · ${fmt(startSec)}–${fmt(endSec)}`;
}

let _uidCounter = Date.now();
export function generateUid(): string {
    return `frag_${(_uidCounter++).toString(36)}`;
}

export function recalcDisplayIds(fragments: Fragment[]): Fragment[] {
    const groups = new Map<string, Fragment[]>();

    fragments.forEach(f => {
        const root = f.root_fragment_uid ?? getUid(f);
        if (!groups.has(root)) groups.set(root, []);
        groups.get(root)!.push(f);
    });

    return fragments.map(f => {
        const rootId = f.root_fragment_uid ?? getUid(f);
        const group = (groups.get(rootId) ?? [])
            .filter(g => g.status !== "removed")
            .sort((a, b) => a.start_frame - b.start_frame);

        const baseName = f.fragment_id.replace(/_[LMR]\d*$/, "");

        if (group.length <= 1) {
            return { ...f, display_id: baseName };
        }

        const sFrags = group.filter(g => g.selection_state === "S");
        const nFrags = group.filter(g => g.selection_state === "N");

        let suffix = "";
        if (f.selection_state === "S") {
            const sIdx = sFrags.findIndex(g => getUid(g) === getUid(f));
            if (sFrags.length === 1) suffix = "";
            else if (sIdx === 0) suffix = "_L";
            else suffix = "_R";
        } else {
            const nIdx = nFrags.findIndex(g => getUid(g) === getUid(f));
            suffix = nFrags.length === 1 ? "_M" : `_M${nIdx + 1}`;
        }

        return { ...f, display_id: `${baseName}${suffix}` };
    });
}

export function commitFragments(fragments: Fragment[]): Fragment[] {
    return fragments.map(f => ({
        ...f,
        status: f.status === "candidate" ? "committed" : f.status
    }));
}

/**
 * assignShortDisplayIds
 *
 * source_video("A", "B", "C"...) 별로 조각을 그룹핑하고
 * 각 그룹 내에서 start_frame 오름차순으로 정렬 후
 * display_id를 "A1", "A2", "B1", "B2" 형태로 부여한다.
 *
 * 이 함수는 recalcDisplayIds 이후에 호출하여 최종 display_id를 재부여한다.
 * recalcDisplayIds가 부여한 "_L", "_R", "_M" 접미사는 존재할 경우 유지된다.
 *
 * 규칙:
 *   - source_video가 "A"인 조각 3개 → "A1", "A2", "A3"
 *   - source_video가 "B"인 조각 2개 → "B1", "B2"
 *   - status === "removed" 인 조각은 번호 부여에서 제외 (기존 유지)
 *   - 분할된 조각(_L, _R, _M 접미사)은 기준 인덱스 기반으로 "A1_L", "A1_R" 형태로 재조합
 *
 * fragment_id · fragment_uid · root_fragment_uid 는 절대 수정하지 않는다.
 * display_id 필드 하나만 재계산한다.
 *
 * @param fragments 입력 Fragment 배열
 * @returns display_id가 재부여된 새 Fragment 배열 (원본 불변)
 */
export function assignShortDisplayIds(fragments: Fragment[]): Fragment[] {
    // 1단계: source_video 별 그룹핑
    const groups = new Map<string, Fragment[]>();
    fragments.forEach(f => {
        if (f.status === "removed") return;
        const src = f.source_video || "";
        if (!groups.has(src)) groups.set(src, []);
        groups.get(src)!.push(f);
    });

    // 2단계: 각 그룹 내 root_fragment_uid 단위로 유일 인덱스 산출
    //         (같은 root에서 파생된 _L, _R, _M 은 하나의 인덱스를 공유)
    const rootIndexBySource = new Map<string, Map<string, number>>();
    groups.forEach((srcFrags, src) => {
        // root_fragment_uid 별 최소 start_frame 으로 정렬
        const rootMinFrame = new Map<string, number>();
        srcFrags.forEach(f => {
            const root = f.root_fragment_uid ?? getUid(f);
            const cur = rootMinFrame.get(root);
            if (cur === undefined || f.start_frame < cur) {
                rootMinFrame.set(root, f.start_frame);
            }
        });

        const sortedRoots = Array.from(rootMinFrame.entries())
            .sort((a, b) => a[1] - b[1])
            .map(([root]) => root);

        const rootToIdx = new Map<string, number>();
        sortedRoots.forEach((root, idx) => rootToIdx.set(root, idx + 1));
        rootIndexBySource.set(src, rootToIdx);
    });

    // 3단계: 각 조각에 "SourceLabel + Index" 형태로 display_id 부여
    //         기존 display_id에 _L/_R/_M 접미사가 있으면 유지
    return fragments.map(f => {
        if (f.status === "removed") return f;

        const src = f.source_video || "";
        const root = f.root_fragment_uid ?? getUid(f);
        const rootToIdx = rootIndexBySource.get(src);
        if (!rootToIdx) return f;

        const idx = rootToIdx.get(root);
        if (idx === undefined) return f;

        // 기존 display_id에서 _L/_R/_M 접미사 추출
        const prevDisplay = f.display_id ?? "";
        const suffixMatch = prevDisplay.match(/(_[LMR]\d*)$/);
        const suffix = suffixMatch ? suffixMatch[1] : "";

        return { ...f, display_id: `${src}${idx}${suffix}` };
    });
}

