export type PriorityMode = "balanced" | "quality" | "easy";
export type CourseType = "core" | "major" | "elective";
export type Division = "upper" | "lower";

export interface TranscriptSummary {
  studentName: string;
  major: string;
  completedCourses: string[];
  remainingRequirements: string[];
  unitsCompleted: number;
}

export interface SectionOption {
  id: string;
  instructor: string;
  time: string;
  days: string;
  quality: number;
  difficulty: number;
}

export interface CourseResult {
  id: string;
  code: string;
  name: string;
  type: CourseType;
  division: Division;
  avgDifficulty: number;
  quality: number;
  timeWindow: string;
  requirementTags: string[];
  fitScore: number;
  sections: SectionOption[];
}

export interface Filters {
  types: CourseType[];
  divisions: Division[];
  requirements: string[];
  timeWindow: string;
}

export interface ScheduledItem {
  courseId: string;
  courseCode: string;
  courseName: string;
  sectionId: string;
  instructor: string;
  days: string;
  time: string;
  conflictWith?: string;
}

export interface AiRecommendation {
  id: string;
  title: string;
  rationale: string;
  items: ScheduledItem[];
}
