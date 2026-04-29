import type { AiChatMessage, AiRecommendation, CourseResult, PriorityMode } from "../types/domain";
import { CourseDetails } from "../components/CourseDetails";
import { CourseTable } from "../components/CourseTable";
import { PlannerNav, type PlannerTab } from "../components/PlannerNav";
import { CalendarTab, type WeeklyBlock } from "../components/CalendarTab";
import { AiTab } from "../components/AiTab";

export function PlannerScreen({
  activeTab,
  onTabChange,
  onBackToFilters,
  priorityMode,
  onPriorityModeChange,
  courses,
  onRefreshCourses,
  selectedCourse,
  onSelectCourse,
  selectedSectionId,
  onSelectSection,
  onAddToSchedule,
  weeklyBlocks,
  onExportIcs,
  onExportGoogle,
  aiResults,
  aiChatMessages,
  aiLabel,
  aiEnabled,
  onAiSendMessage,
  onAiAcceptPlan
}: {
  activeTab: PlannerTab;
  onTabChange: (tab: PlannerTab) => void;
  onBackToFilters: () => void;
  priorityMode: PriorityMode;
  onPriorityModeChange: (mode: PriorityMode) => void;
  courses: CourseResult[];
  onRefreshCourses: () => void;
  selectedCourse: CourseResult | null;
  onSelectCourse: (course: CourseResult) => void;
  selectedSectionId: string;
  onSelectSection: (id: string) => void;
  onAddToSchedule: () => void;
  weeklyBlocks: WeeklyBlock[];
  onExportIcs: () => void;
  onExportGoogle: () => void;
  aiResults: AiRecommendation[];
  aiChatMessages: AiChatMessage[];
  aiLabel: string;
  aiEnabled: boolean;
  onAiSendMessage: (message: string) => void;
  onAiAcceptPlan: (planId: string) => void;
}) {
  return (
    <section className="grid gap-4">
      <div>
        <button
          onClick={onBackToFilters}
          className="rounded-lg border border-slate-500 px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-sky-300"
        >
          Back to transcript filters
        </button>
      </div>
      <PlannerNav
        activeTab={activeTab}
        onTabChange={onTabChange}
        priorityMode={priorityMode}
        onPriorityModeChange={onPriorityModeChange}
      />

      {activeTab === "build" && (
        <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
          <CourseTable courses={courses} onSelect={onSelectCourse} onRefresh={onRefreshCourses} />
          <CourseDetails
            selectedCourse={selectedCourse}
            selectedSectionId={selectedSectionId}
            onSelectSection={onSelectSection}
            onAdd={onAddToSchedule}
          />
        </div>
      )}

      {activeTab === "calendar" && (
        <CalendarTab weeklyBlocks={weeklyBlocks} onExportIcs={onExportIcs} onExportGoogle={onExportGoogle} />
      )}

      {activeTab === "ai" && (
        <AiTab
          plans={aiResults}
          chatMessages={aiChatMessages}
          aiLabel={aiLabel}
          aiEnabled={aiEnabled}
          onSendMessage={onAiSendMessage}
          onAcceptPlan={onAiAcceptPlan}
        />
      )}
    </section>
  );
}

