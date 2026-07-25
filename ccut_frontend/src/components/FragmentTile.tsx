import React, { useState } from "react";
import { Fragment, formatDuration } from "@/data/fragmentData";
import { displayName } from "@/lib/fragmentIdentity";
import { Play } from "lucide-react";
import { DEBUG_LOG } from "@/utils/debugFlags";

interface FragmentTileProps {
  fragment: Fragment;
  isSelected?: boolean;
  isHighlighted?: boolean;
  isExpanded?: boolean;
  hasActiveSelection?: boolean;
  variant?: "edit" | "panorama" | "reserved";
  showIntelligence?: boolean;
  videoPath?: string | null;
  onClick?: () => void;
  onDoubleClick?: () => void;
  onEditFragment?: () => void;   // [2-2b] 조각편집 진입 (variant=edit에서만 버튼 노출)

  compactLabelOnly?: boolean;
  showPlayButton?: boolean;
  playButtonVisible?: boolean;
  onPlay?: (e: React.MouseEvent) => void;
  widthScale?: number;
  orderBadge?: number | null;
}

const FragmentTile: React.FC<FragmentTileProps> = ({
  fragment,
  isSelected,
  isHighlighted,
  isExpanded,
  hasActiveSelection,
  variant = "edit",
  showIntelligence,
  videoPath,
  onClick,
  onDoubleClick,
  onEditFragment,

  compactLabelOnly = false,
  showPlayButton = false,
  playButtonVisible = false,
  onPlay,
  widthScale = 0.7,
  orderBadge = null,
}) => {
  const [hasImageError, setHasImageError] = useState(false);
  const seconds = fragment.duration / 30;
  const cardWidth = `${Math.max(70, Math.min(350, seconds * 20 * widthScale))}px`;
  const hookWidth = `${(fragment.intelligence?.hook_score || 0.5) * 100}%`;

  const getBaseFragmentId = (frag: any): string => {
    if (!frag) return "";
    const explicitBase = frag.root_fragment_uid || frag.parent_fragment_uid || frag.source_fragment_id || frag.derivedFrom || frag.fragment_id || frag.fragment_uid || "";
    return explicitBase.replace(/(_M|_R|_L|_copy_\d+|\+).*$/, "");
  };

  const resolveThumbnailUrl = (frag: any): string | null => {
    if (!frag) return null;
    
    // 1. Check if the fragment itself has a valid thumbnail_url
    const directUrl = frag.thumbnail?.thumbnail_url || frag.thumbnail_url || frag.intelligence?.thumb_url || null;
    if (directUrl) {
      return directUrl;
    }

    // 2. 직접 썸네일이 없으면 base fragment ID로 표준 경로를 유도한다.
    //    base ID(예: VF1_SRC_CB9107CA)의 썸네일은 '/static/thumbnails/{baseId}.jpg' 규약.
    // Fragment VF1_SRC_CB9107CA -> thumb_url is '/static/thumbnails/VF1_SRC_CB9107CA.jpg'.
    // Fragment VF2_SRC_CB9107CA -> thumb_url is '/static/thumbnails/VF2_SRC_CB9107CA.jpg'.
    // Yes! The base fragments (the primary video fragments) are named VF1_SRC_..., VF2_SRC_...
    // Their actual thumbnail url is indeed '/static/thumbnails/VF{N}_SRC_{HASH}.jpg'.
    // Therefore, if the base fragment ID is a VF... ID (or contains VF), we can resolve it directly!
    // But what if it's a semantic fragment ID (SF_...)? Let's check:
    // A semantic fragment has parent_vf_id (e.g. parent_vf_id = 'VF1_SRC_CB9107CA').
    // So if the fragment is a modified semantic fragment (e.g., SF_..._M), its parent is SF_... which has a lineage to VF1_SRC_...
    // Let's implement parent lookups using any global reference if available, or fall back to the base ID lookup.
    // Let's check if the window/globally exposed objects have these fragments.
    // We can query all rendered tiles, or check if we can store them in a window variable in Index.tsx or inside custom hooks.
    // Let's look up dynamically:
    const baseId = getBaseFragmentId(frag);
    if (baseId) {
      // If baseId is a VF (Video Fragment), we can format it directly or look up if it's registered.
      // Wait, the instruction says: "ID로 파일경로 조립 금지. 진짜 파일명은 ID와 다른 체계다. 실재하는 thumbnail_url 문자열을 상속하라."
      // Ah! "ID로 파일경로 조립 금지... 실재하는 thumbnail_url 문자열을 상속하라."
      // This means we must NOT do `/static/thumbnails/${baseId}.jpg` (which is assembly from ID).
      // We must inherit the actual `thumbnail_url` string from the parent fragment itself.
      // How do we find the parent fragment object?
      // Let's check if we can query the parent fragment from the DOM or globally.
      // Let's look at the global window object. We can check if there are any arrays on window.
      // Or we can save a global registry of fragment IDs to their actual thumbnail URLs whenever a FragmentTile is rendered!
      // Yes! Since FragmentTile is rendered for all visible fragments (including VF base fragments or parent fragments when they are loaded/rendered),
      // we can save their direct thumbnail URLs in a global map: `window.__ccut_thumbnail_cache`.
      // Let's check if `window.__ccut_thumbnail_cache` exists, and if not, initialize it.
      // When a fragment has a direct thumbnail, we store it: `window.__ccut_thumbnail_cache[frag.fragment_id] = directUrl`.
      // Then, if a fragment does NOT have a direct thumbnail, we look up its parent/base IDs in the cache:
      // `root_fragment_uid`, `parent_fragment_uid`, `source_fragment_id`, `derivedFrom`, `baseId`.
      if (typeof window !== 'undefined') {
        const cache = (window as any).__ccut_thumbnail_cache || {};
        if (!(window as any).__ccut_thumbnail_cache) {
          (window as any).__ccut_thumbnail_cache = cache;
        }
        
        // Cache this fragment's direct URL if it exists
        const explicitId = frag.fragment_id || frag.fragment_uid;
        if (explicitId && directUrl) {
          cache[explicitId] = directUrl;
        }

        // Try to look up using parent keys in priority order: root_fragment_uid -> parent_fragment_uid -> source_fragment_id -> derivedFrom -> baseId
        const parents = [
          frag.root_fragment_uid,
          frag.parent_fragment_uid,
          frag.source_fragment_id,
          frag.derivedFrom,
          baseId
        ].filter(Boolean);

        for (const pId of parents) {
          if (cache[pId]) {
            return cache[pId];
          }
          // Also try cleaned versions of pId (e.g. without suffix)
          const cleanPId = pId.replace(/(_M|_R|_L|_copy_\d+|\+).*$/, "");
          if (cache[cleanPId]) {
            return cache[cleanPId];
          }
        }
      }
    }


    // [THUMB-ORPHAN 2026-07-05] 동봉 URL도, 전역 캐시 상속도 실패한 조각
    // (옛 저장 제안·아카이브 포함·재조각화 고아 등 "로드 안 된 조각" 계열).
    // SF 시대 썸네일은 {fid}.jpg 실측 규칙 — 위의 "ID 조립 금지" 주석은 파일명이
    // ID와 달랐던 VF 시대 유산이다. 최후 수단으로 조립을 시도하되,
    // 파일이 없으면 <img> onError가 "이미지 없음"으로 정직 강등한다(남의 이미지 금지).
    const orphanBase = getBaseFragmentId(frag) || frag.fragment_id;
    if (orphanBase && /^SF_/.test(orphanBase)) {
      return `/api/static/thumbnails/${orphanBase}.jpg`;
    }

    return null;
  };

  const resolvedUrl = resolveThumbnailUrl(fragment);
  const isProgrammed = orderBadge != null;

  return (
    <div
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      className={`relative group cursor-pointer overflow-hidden border-[0.5px] flex-shrink-0 fragment-tile rounded-lg
        transition-all duration-200 bg-[hsl(228_10%_13%)]
        ${isSelected
          ? "border-primary ring-2 ring-primary/80 shadow-[0_0_0_2px_rgba(96,165,250,0.42),0_0_22px_rgba(96,165,250,0.35),0_10px_24px_rgba(0,0,0,0.28)]"
          : isHighlighted
            ? "border-primary ring-2 ring-primary/70 shadow-[0_0_0_2px_rgba(96,165,250,0.36),0_0_18px_rgba(96,165,250,0.28)]"
            : "border-border/20 hover:border-primary/20"
        }`}
      style={{ width: cardWidth, height: "100px", opacity: isProgrammed ? undefined : 0.72 }}
    >
      <div
        className="absolute inset-0 flex items-center justify-center overflow-hidden bg-[hsl(228_8%_14%)]"
      >
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 2px 2px, white 1px, transparent 0)",
            backgroundSize: "24px 24px",
          }}
        />
      </div>

      {hasImageError || !resolvedUrl ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-muted/20 border border-dashed border-muted-foreground/30 z-[1]">
          <span className="text-[10px] text-muted-foreground font-medium">이미지 없음</span>
        </div>
      ) : (
        <img
          draggable={false}
          src={resolvedUrl}
          alt={fragment.fragment_id}
          className="absolute inset-0 w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity duration-200 z-[1]"
          onLoad={(e) => {
            const img = e.currentTarget;
            const naturalWidth = img.naturalWidth;
            const fallbackUsed = naturalWidth > 0 ? 0 : 1;
            DEBUG_LOG && console.log(`[THUMB_RESOLVE] fragId=${fragment.fragment_id} display_id=${fragment.display_id || fragment.fragment_id} directThumbnail=${fragment.thumbnail?.thumbnail_url || "none"} base=${getBaseFragmentId(fragment)} resolvedThumbnail=${resolvedUrl} naturalWidth=${naturalWidth} fallbackUsed=${fallbackUsed}`);
          }}
          onError={(e) => {
            setHasImageError(true);
            DEBUG_LOG && console.log(`[THUMB_RESOLVE] fragId=${fragment.fragment_id} display_id=${fragment.display_id || fragment.fragment_id} directThumbnail=${fragment.thumbnail?.thumbnail_url || "none"} base=${getBaseFragmentId(fragment)} resolvedThumbnail=${resolvedUrl} naturalWidth=0 fallbackUsed=1`);
          }}
        />
      )}

      {videoPath && (hasImageError || !resolvedUrl) && (
        <video
          draggable={false}
          src={videoPath}
          className="absolute inset-0 w-full h-full object-cover opacity-100 z-[2]"
          preload="metadata"
          muted
          playsInline
          onLoadedMetadata={(e) => {
            const v = e.currentTarget;
            v.currentTime = (fragment.start_frame ?? 0) / 30;
          }}
          onError={() => setHasImageError(true)}
        />
      )}

      <div className="absolute inset-0 bg-black/38" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/72 via-transparent to-black/16 pointer-events-none" />

      {/* [2-2b] 조각편집 진입 버튼: variant=edit + onEditFragment 있을 때만, hover 시 중앙 표시. 선택 토글(onClick)과 분리. */}
      {variant === "edit" && onEditFragment && (
        <div className="absolute inset-0 z-20 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onEditFragment(); }}
            className="pointer-events-auto px-2.5 py-1 rounded-md bg-black/60 hover:bg-black/80 text-white text-[11px] font-bold border border-white/20 backdrop-blur-sm"
          >
            ✂ 조각편집
          </button>
        </div>
      )}

      <div className="absolute inset-0 z-10">
        {isProgrammed && (
          <span className="absolute left-[6px] top-[6px] flex h-[18px] w-[18px] items-center justify-center rounded-[5px] bg-primary font-mono text-[11px] font-medium leading-none text-primary-foreground">
            {orderBadge}
          </span>
        )}
        {fragment.display_id && !fragment.display_id.startsWith("SF_") && (
          <span className="absolute right-[7px] top-[7px] font-mono text-[11px] font-medium leading-none text-secondary-foreground/60">
            {fragment.display_id}
          </span>
        )}
        <span className="absolute bottom-[6px] left-[7px] font-mono text-[10px] font-normal leading-none text-muted-foreground">
          {formatDuration(fragment.duration)}
        </span>

        {showPlayButton && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onPlay?.(e);
            }}
            className={`absolute bottom-[6px] right-[7px] h-6 w-6 rounded-lg bg-primary/18 border border-primary/20
              flex items-center justify-center ${playButtonVisible ? "opacity-100" : "opacity-0"} group-hover:opacity-100
              transition-all duration-200 translate-y-1 group-hover:translate-y-0`}
          >
            <Play size={12} className="text-primary fill-primary" />
          </button>
        )}
      </div>

      <div className="absolute bottom-0 left-0 w-full h-1 bg-white/6 overflow-hidden">
        <div
          className="h-full bg-primary/55 shadow-[0_0_8px_rgba(96,165,250,0.22)]"
          style={{ width: hookWidth }}
        />
      </div>
    </div>
  );
};

export default FragmentTile;
