import type { PriorityMode } from "../types/domain";
import { cn } from "../lib/ui";

export type PlannerTab = "build" | "calendar" | "ai";

export function PlannerNav({
  activeTab,
  onTabChange,
  priorityMode,
  onPriorityModeChange
}: {
  activeTab: PlannerTab;
  onTabChange: (tab: PlannerTab) => void;
  priorityMode: PriorityMode;
  onPriorityModeChange: (next: PriorityMode) => void;
}) {
  return (
    <div className="glass rounded-2xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          {(["build", "calendar", "ai"] as PlannerTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => onTabChange(tab)}
              className={cn(
                "rounded-lg px-4 py-2 text-sm font-semibold capitalize",
                activeTab === tab ? "bg-sky-300 text-slate-900" : "bg-slate-900/50 text-slate-200"
              )}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-slate-300">Priority mode:</span>
          <select
            value={priorityMode}
            onChange={(event) => onPriorityModeChange(event.target.value as PriorityMode)}
            className="rounded-lg border border-slate-500 bg-slate-900 px-2 py-1 text-slate-100"
          >
            <option value="balanced">Balanced</option>
            <option value="quality">Quality-first</option>
            <option value="easy">Easier workload</option>
          </select>
        </div>
      </div>
    </div>
  );
}

