export type PlannerNavProps = {
  activeTab: string;
  onTabChange: (tab: string) => void;
  priorityMode: string;
  onPriorityModeChange: (mode: string) => void;
};

const TABS = ["build", "plan"] as const;

export function PlannerNav({
  activeTab,
  onTabChange,
  priorityMode,
  onPriorityModeChange
}: PlannerNavProps) {
  return (
    <nav aria-label="Planner">
      <div aria-label="Planner sections">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            aria-current={tab === activeTab ? "page" : undefined}
            onClick={() => onTabChange(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
      <label>
        Priority
        <select
          value={priorityMode}
          onChange={(e) => onPriorityModeChange(e.target.value)}
          aria-label="Scheduling priority"
        >
          <option value="balanced">balanced</option>
          <option value="speed">speed</option>
        </select>
      </label>
    </nav>
  );
}
