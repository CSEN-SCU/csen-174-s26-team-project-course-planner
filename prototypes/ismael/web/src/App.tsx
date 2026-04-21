import { useMemo, useState } from "react";
import {
  completeSchedule,
  exportIcs,
  getEligibleCourses,
  parseTranscript,
  recommendSchedule
} from "./services/api";
import type {
  AiRecommendation,
  CourseResult,
  Filters,
  PriorityMode,
  ScheduledItem,
  TranscriptSummary
} from "./types/domain";
import { AppHeader } from "./components/AppHeader";
import { AlertBar } from "./components/AlertBar";
import { IntroScreen } from "./screens/IntroScreen";
import { TranscriptScreen } from "./screens/TranscriptScreen";
import { PlannerScreen } from "./screens/PlannerScreen";
import type { PlannerTab } from "./components/PlannerNav";
import type { WeeklyBlock } from "./components/CalendarTab";

type Stage = "intro" | "upload" | "planner";

const initialFilters: Filters = {
  types: [],
  divisions: [],
  requirements: [],
  timeWindow: ""
};

function hasConflict(a: ScheduledItem, b: ScheduledItem) {
  return a.days === b.days && a.time === b.time;
}

export default function App() {
  const [stage, setStage] = useState<Stage>("intro");
  const [activeTab, setActiveTab] = useState<PlannerTab>("build");
  const [summary, setSummary] = useState<TranscriptSummary | null>(null);
  const [courses, setCourses] = useState<CourseResult[]>([]);
  const [selectedCourse, setSelectedCourse] = useState<CourseResult | null>(null);
  const [selectedSectionId, setSelectedSectionId] = useState<string>("");
  const [schedule, setSchedule] = useState<ScheduledItem[]>([]);
  const [priorityMode, setPriorityMode] = useState<PriorityMode>("balanced");
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [aiResults, setAiResults] = useState<AiRecommendation[]>([]);
  const [uploadName, setUploadName] = useState("");
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedSection = selectedCourse?.sections.find((section) => section.id === selectedSectionId);

  const weeklyBlocks: WeeklyBlock[] = useMemo(() => {
    return schedule.map((item) => ({
      ...item,
      isConflict: schedule.some((other) => other.courseId !== item.courseId && hasConflict(item, other))
    }));
  }, [schedule]);

  const updateFilterArray = (key: "types" | "divisions" | "requirements", value: string) => {
    setFilters((prev) => {
      const current = prev[key] as string[];
      const exists = current.includes(value);
      return {
        ...prev,
        [key]: exists ? current.filter((v) => v !== value) : [...current, value]
      };
    });
  };

  const loadSummary = async (payload: { fileName?: string; transcriptText?: string }) => {
    setLoading("Parsing transcript...");
    setError(null);
    try {
      const parsed = await parseTranscript(payload);
      setSummary(parsed);
      setStage("upload");
    } catch {
      setError("We could not parse the transcript. Try sample mode.");
    } finally {
      setLoading(null);
    }
  };

  const loadCourses = async () => {
    setLoading("Finding eligible courses...");
    setError(null);
    try {
      const results = await getEligibleCourses(filters, priorityMode, summary?.completedCourses ?? []);
      setCourses(results);
      setStage("planner");
      setActiveTab("build");
    } catch {
      setError("Unable to load course results.");
    } finally {
      setLoading(null);
    }
  };

  const addSelectionToSchedule = () => {
    if (!selectedCourse || !selectedSection) return;
    const next: ScheduledItem = {
      courseId: selectedCourse.id,
      courseCode: selectedCourse.code,
      courseName: selectedCourse.name,
      sectionId: selectedSection.id,
      instructor: selectedSection.instructor,
      days: selectedSection.days,
      time: selectedSection.time
    };
    const conflict = schedule.find((existing) => hasConflict(existing, next));
    if (conflict) {
      next.conflictWith = `${conflict.courseCode} ${conflict.time}`;
    }
    setSchedule((prev) => [...prev, next]);
    setSelectedCourse(null);
    setSelectedSectionId("");
  };

  const handleAiRecommend = async () => {
    setLoading("Asking AI for recommendations...");
    setError(null);
    try {
      const plans = await recommendSchedule({
        selectedDesiredCourses: courses.slice(0, 3).map((course) => course.code),
        priorities: priorityMode,
        remainingRequirements: summary?.remainingRequirements ?? [],
        existingSchedule: schedule
      });
      setAiResults(plans);
      setActiveTab("ai");
    } catch {
      setError("AI recommendation failed.");
    } finally {
      setLoading(null);
    }
  };

  const handleAiComplete = async () => {
    setLoading("Completing your draft with AI...");
    setError(null);
    try {
      const plans = await completeSchedule({
        selectedDesiredCourses: courses.slice(0, 3).map((course) => course.code),
        priorities: priorityMode,
        remainingRequirements: summary?.remainingRequirements ?? [],
        existingSchedule: schedule
      });
      setAiResults(plans);
      setActiveTab("ai");
    } catch {
      setError("AI completion failed.");
    } finally {
      setLoading(null);
    }
  };

  const resetDemo = () => {
    setStage("intro");
    setActiveTab("build");
    setSummary(null);
    setCourses([]);
    setSelectedCourse(null);
    setSelectedSectionId("");
    setSchedule([]);
    setPriorityMode("balanced");
    setFilters(initialFilters);
    setAiResults([]);
    setUploadName("");
    setLoading(null);
    setError(null);
  };

  return (
    <main className="min-h-screen px-6 py-8 md:px-10">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <AppHeader onResetDemo={resetDemo} showReset={stage !== "intro" || schedule.length > 0 || aiResults.length > 0} />

        {loading && <AlertBar kind="loading" message={loading} />}
        {error && <AlertBar kind="error" message={error} />}

        {stage === "intro" && (
          <IntroScreen
            uploadName={uploadName}
            onUploadNameChange={setUploadName}
            onTrySample={() =>
              loadSummary({
                fileName: "sample-transcript.pdf",
                transcriptText: "Sample transcript for SCU undergrad with CSE 30, CSE 101, MATH 11, CTW 1, CTW 2 completed."
              })
            }
            onParseUpload={() => loadSummary({ fileName: uploadName || "uploaded-transcript.pdf" })}
          />
        )}

        {stage === "upload" && summary && (
          <TranscriptScreen
            summary={summary}
            filters={filters}
            onToggleType={(type) => updateFilterArray("types", type)}
            onToggleDivision={(division) => updateFilterArray("divisions", division)}
            onToggleRequirement={(req) => updateFilterArray("requirements", req)}
            onTimeWindowChange={(next) => setFilters((prev) => ({ ...prev, timeWindow: next }))}
            onContinue={loadCourses}
          />
        )}

        {stage === "planner" && (
          <PlannerScreen
            activeTab={activeTab}
            onTabChange={setActiveTab}
            priorityMode={priorityMode}
            onPriorityModeChange={setPriorityMode}
            courses={courses}
            onRefreshCourses={loadCourses}
            selectedCourse={selectedCourse}
            onSelectCourse={setSelectedCourse}
            selectedSectionId={selectedSectionId}
            onSelectSection={setSelectedSectionId}
            onAddToSchedule={addSelectionToSchedule}
            weeklyBlocks={weeklyBlocks}
            onExportIcs={async () => {
              try {
                setLoading("Preparing calendar export...");
                setError(null);
                await exportIcs(schedule);
              } catch {
                setError("Could not export ICS file.");
              } finally {
                setLoading(null);
              }
            }}
            onExportGoogle={async () => {
              try {
                setLoading("Preparing Google Calendar export...");
                setError(null);
                await exportIcs(schedule);
              } catch {
                setError("Could not prepare export for Google Calendar.");
              } finally {
                setLoading(null);
              }
            }}
            aiResults={aiResults}
            onAiRecommend={handleAiRecommend}
            onAiComplete={handleAiComplete}
          />
        )}
      </div>
    </main>
  );
}
