import React, { useState } from "react";
import { Fragment, formatDuration } from "@/data/fragmentData";
import { Clock, Play } from "lucide-react";

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

  widthScale?: number;
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

  widthScale = 0.7,
}) => {
  const [hasImageError, setHasImageError] = useState(false);
  const seconds = fragment.duration / 30;
  const cardWidth = `${Math.max(70, Math.min(350, seconds * 20 * widthScale))}px`;
  const hookWidth = `${(fragment.intelligence?.hook_score || 0.5) * 100}%`;

  return (
    <div
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      className={`relative group cursor-pointer overflow-hidden border flex-shrink-0 fragment-tile
        transition-all duration-200 bg-[hsl(228_10%_13%)]
        ${isSelected
          ? "border-primary shadow-[0_0_0_1px_rgba(96,165,250,0.28),0_10px_24px_rgba(0,0,0,0.28)]"
          : isHighlighted
            ? "border-primary/40 shadow-[0_0_0_1px_rgba(96,165,250,0.12)]"
            : "border-border/20 hover:border-primary/20"
        }`}
      style={{ width: cardWidth, height: "100px" }}
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
        <div className="relative">
          <div className="absolute inset-0 bg-white/10 blur-xl rounded-full scale-150 opacity-20" />
          <Play size={20} className="text-white/40 fill-white/10" />
        </div>
      </div>

      {!hasImageError && (
        <img
          draggable={false}
          src={
            fragment.thumbnail?.thumbnail_url ||
            "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
          }
          alt={fragment.fragment_id}
          className="absolute inset-0 w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity duration-200 z-[1]"
          onError={(e) => {
            // [STEP 10-I.5.27-E6-R1] Suppress SF_*.jpg failed requests
            setHasImageError(true);
          }}
        />
      )}

      {videoPath && (hasImageError || !fragment.thumbnail?.thumbnail_url) && (
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

      <div className="absolute inset-0 z-10 p-3 flex flex-col justify-between">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <span className="block text-[10px] font-black text-white/75 tracking-tight truncate">
              {fragment.display_id ?? fragment.fragment_id}
            </span>
          </div>


        </div>

        <div className="flex items-end justify-between gap-2">
          <div className="flex items-center gap-1.5 text-white/82">
            <Clock size={10} className="text-primary/90" />
            <span className="text-[11px] font-bold">{formatDuration(fragment.duration)}</span>
          </div>

          <div
            className="w-6 h-6 rounded-lg bg-primary/18 border border-primary/20
              flex items-center justify-center opacity-0 group-hover:opacity-100
              transition-all duration-200 translate-y-1 group-hover:translate-y-0"
          >
            <Play size={10} className="text-primary fill-primary" />
          </div>
        </div>
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