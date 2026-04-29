import type { AiRecommendation, CourseResult, PriorityMode } from "../types/domain";
import { CourseDetails } from "../components/CourseDetails";
import { CourseTable } from "../components/CourseTable";
import { PlannerNav, type PlannerTab } from "../components/PlannerNav";
import { CalendarTab, type WeeklyBlock } from "../components/CalendarTab";
import { AiTab } from "../components/AiTab";

export function PlannerScreen({
  activeTab,
  onTabChange,
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
  onAiRecommend,
  onAiComplete
}: {
  activeTab: PlannerTab;
  onTabChange: (tab: PlannerTab) => void;
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
  onAiRecommend: () => void;
  onAiComplete: () => void;
}) {
  return (
    <section className="grid gap-4">
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

      {activeTab === "ai" && <AiTab plans={aiResults} onRecommend={onAiRecommend} onComplete={onAiComplete} />}
    </section>
  );
}

