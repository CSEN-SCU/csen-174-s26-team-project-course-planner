import type { CourseWithRelations } from "../services/courseService.js";

export type PriorityMode = "balanced" | "quality" | "easy";

export function scoreCourse(course: CourseWithRelations, mode: PriorityMode) {
  const ratings = course.sections.map((section) => section.professorRating).filter(Boolean);
  const avgQuality = ratings.length ? ratings.reduce((sum, rating) => sum + (rating?.qualityScore ?? 0), 0) / ratings.length : 3.5;
  const avgDifficulty = ratings.length ? ratings.reduce((sum, rating) => sum + (rating?.difficultyScore ?? 0), 0) / ratings.length : 3;
  const quality = avgQuality / 5;
  const ease = 1 - avgDifficulty / 5;
  if (mode === "quality") return quality * 0.75 + ease * 0.25;
  if (mode === "easy") return quality * 0.25 + ease * 0.75;
  return quality * 0.5 + ease * 0.5;
}
