import { WEEKDAY_LABELS, CALENDAR_START_HOUR } from "../types";

export type SlotActionModalProps = {
  open: boolean;
  dayIndex: number;
  startMin: number;
  endMin: number;
  clientX: number;
  clientY: number;
  /** When false, AI slot suggestions are hidden (requires Academic Progress). */
  hasAcademicProgress: boolean;
  onBrowse: () => void;
  onAiSuggest: () => void;
  onClose: () => void;
};

function formatSlotLabel(dayIndex: number, startMin: number, endMin: number): string {
  const base = CALENDAR_START_HOUR * 60;
  const fmt = (off: number) => {
    const total = base + off;
    const h = Math.floor(total / 60);
    const m = total % 60;
    const d = new Date();
    d.setHours(h, m, 0, 0);
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  };
  return `${WEEKDAY_LABELS[dayIndex] ?? "?"} ${fmt(startMin)} – ${fmt(endMin)}`;
}

export function SlotActionModal({
  open,
  dayIndex,
  startMin,
  endMin,
  clientX,
  clientY,
  hasAcademicProgress,
  onBrowse,
  onAiSuggest,
  onClose,
}: SlotActionModalProps) {
  if (!open) return null;

  const left = Math.min(clientX + 8, window.innerWidth - 280);
  const top = Math.min(clientY + 8, window.innerHeight - 200);

  return (
    <>
      <div className="fixed inset-0 z-40" aria-hidden onClick={onClose} />
      <div
        className="fixed z-50 w-64 rounded-lg border border-neutral-200 bg-white p-3 shadow-lg"
        style={{ left, top }}
        role="dialog"
        aria-label="Time slot options"
      >
        <p className="text-xs font-semibold text-[var(--scu-text)]">
          {formatSlotLabel(dayIndex, startMin, endMin)}
        </p>
        <p className="mt-0.5 text-[10px] text-neutral-500">
          {hasAcademicProgress ? "Choose how to fill this time" : "Search the catalog for this time"}
        </p>
        <div className="mt-3 flex flex-col gap-1.5">
          <button
            type="button"
            onClick={onBrowse}
            className="rounded-md bg-[var(--scu-red)] px-3 py-2 text-xs font-semibold text-white hover:bg-[var(--scu-dark-red)]"
          >
            Search courses in this time
          </button>
          {hasAcademicProgress && (
            <button
              type="button"
              onClick={onAiSuggest}
              className="rounded-md border border-neutral-300 px-3 py-2 text-xs font-semibold text-[var(--scu-text)] hover:bg-neutral-50"
            >
              AI suggestions for this slot
            </button>
          )}
        </div>
      </div>
    </>
  );
}
