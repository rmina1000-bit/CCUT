import React from "react";

interface AppDialogProps {
  open: boolean;
  message: React.ReactNode;
  title?: React.ReactNode;
  confirmText?: React.ReactNode;
  cancelText?: React.ReactNode;
  onConfirm: () => void;
  onCancel?: () => void;
}

export const AppDialog: React.FC<AppDialogProps> = ({
  open,
  title = "Notice",
  message,
  confirmText = "OK",
  cancelText,
  onConfirm,
  onCancel,
}) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/55 px-4 backdrop-blur-sm">
      <div className="w-full max-w-[360px] rounded-2xl border border-white/10 bg-[hsl(228_14%_10%)] p-5 shadow-2xl shadow-black/50">
        <div className="text-[14px] font-semibold text-foreground/90">{title}</div>
        <div className="mt-3 whitespace-pre-wrap text-[13px] leading-relaxed text-muted-foreground/90">{message}</div>
        <div className="mt-5 flex justify-end gap-2">
          {cancelText && onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="rounded-xl border border-white/10 px-4 py-2 text-[12px] text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground"
            >
              {cancelText}
            </button>
          )}
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-xl bg-primary/20 px-4 py-2 text-[12px] font-semibold text-primary transition-colors hover:bg-primary/30"
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};
