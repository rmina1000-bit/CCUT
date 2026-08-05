import React from "react";
import { Loader2, Play } from "lucide-react";

import { STORY_GATE_COPY, soundRoleReasonText } from "@/lib/storyGateCopy";
import {
  SOUND_ROLES,
  type SoundRole,
  type SoundRoleItem,
} from "@/utils/soundRoleClient";

interface SoundRoleControlProps {
  item: SoundRoleItem;
  compact?: boolean;
  saving?: boolean;
  className?: string;
  onChange?: (item: SoundRoleItem, role: SoundRole) => void | Promise<void>;
  onPlay?: () => void;
}

const ROLE_TONE: Record<SoundRole, string> = {
  dialogue: "border-emerald-400/35 text-emerald-200",
  background: "border-amber-400/35 text-amber-200",
  silence: "border-sky-400/35 text-sky-200",
  unknown: "border-border/40 text-muted-foreground",
};

export const SoundRoleControl: React.FC<SoundRoleControlProps> = ({
  item,
  compact = false,
  saving = false,
  className = "",
  onChange,
  onPlay,
}) => {
  const reason = soundRoleReasonText(item, false);
  const compactReason = soundRoleReasonText(item, true);
  const disabled = saving || !item.editable || !onChange;
  const stop = (event: React.SyntheticEvent) => event.stopPropagation();

  return (
    <div
      data-sound-role={item.effective_role}
      data-sound-reason={item.reason}
      data-sound-overridden={item.overridden ? "true" : "false"}
      title={reason}
      className={`${compact
        ? "flex w-[78px] max-w-[calc(100%-8px)] flex-col gap-0.5 rounded bg-black/80 px-1.5 py-1 shadow-sm"
        : "flex min-h-[31px] w-[205px] flex-none items-center gap-2 border-b-[0.5px] border-border/30 px-2"
      } ${className}`}
      onClick={stop}
      onDoubleClick={stop}
      onMouseDown={stop}
      onDragStart={stop}
    >
      <div className={`flex min-w-0 items-center ${compact ? "w-full gap-0.5" : "w-[76px] flex-none"}`}>
        {saving && <Loader2 className="mr-1 h-3 w-3 flex-none animate-spin" aria-hidden="true" />}
        <select
          aria-label={STORY_GATE_COPY.sound.handlingLabel}
          value={item.effective_role}
          disabled={disabled}
          onChange={(event) => {
            event.stopPropagation();
            void onChange?.(item, event.target.value as SoundRole);
          }}
          className={`min-w-0 cursor-pointer border bg-transparent font-semibold outline-none disabled:cursor-default disabled:opacity-70 ${
            compact ? "h-5 flex-1 rounded px-1 text-[10px]" : "h-6 w-full rounded px-1 text-[11px]"
          } ${ROLE_TONE[item.effective_role]}`}
        >
          {SOUND_ROLES.map((role) => (
            <option key={role} value={role} className="bg-background text-foreground">
              {STORY_GATE_COPY.sound.roles[role]}
            </option>
          ))}
        </select>
        {compact && onPlay && (
          <button
            type="button"
            data-image-play="true"
            title={STORY_GATE_COPY.sound.play}
            aria-label={STORY_GATE_COPY.sound.play}
            className="flex h-5 w-5 flex-none items-center justify-center rounded text-white/75 hover:bg-white/10 hover:text-white"
            onClick={(event) => {
              event.stopPropagation();
              onPlay();
            }}
          >
            <Play className="h-3 w-3 fill-current" aria-hidden="true" />
          </button>
        )}
      </div>
      <span className={`${compact
        ? "w-full truncate text-[8px] leading-none text-white/70"
        : "min-w-0 flex-1 truncate text-[10px] leading-tight text-muted-foreground"
      }`}>
        {compact ? compactReason : reason}
      </span>
    </div>
  );
};
