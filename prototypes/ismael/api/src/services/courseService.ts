import type { Prisma } from "@prisma/client";
import { prisma } from "../db/client.js";
import { scoreCourse, type PriorityMode } from "../utils/priority.js";
import { isEligible } from "../utils/prereqs.js";
import { formatRange } from "../utils/time.js";

export type CourseWithRelations = Prisma.CourseGetPayload<{
  include: {
    sections: {
      include: {
        professorRating: true;
      };
    };
    requirementLinks: {
      include: {
        requirementTag: true;
      };
    };
  };
}>;

interface CourseFilterInput {
  completedCourses?: string[];
  filters?: {
    types?: string[];
    divisions?: string[];
    requirements?: string[];
    timeWindow?: string;
  };
  mode?: PriorityMode;
}

export async function getEligibleCourseResults(input: CourseFilterInput) {
  const completedCourses = input.completedCourses ?? [
    "COEN 19",
    "CTW 1",
    "CTW 2",
    "MATH 11",
    "MATH 12",
    "MATH 13",
    "CHEM 11",
    "PHYS 31",
    "PHYS 32",
    "COEN 10",
    "COEN 11",
    "COEN 12",
    "ENGR 1"
  ];
  const mode = input.mode ?? "balanced";
  const completedSet = new Set(completedCourses.map((code) => code.toUpperCase()));
  const courses = await prisma.course.findMany({
    include: {
      sections: { include: { professorRating: true } },
      requirementLinks: { include: { requirementTag: true } }
    }
  });

  return courses
    .filter((course) => isEligible(completedCourses, ((course.prerequisiteCodes as string[] | null) ?? [])))
    .filter((course) => !completedSet.has(course.code.toUpperCase()))
    .filter((course) => (input.filters?.types?.length ? input.filters.types.includes(course.type) : true))
    .filter((course) => (input.filters?.divisions?.length ? input.filters.divisions.includes(course.division) : true))
    .filter((course) => {
      if (!input.filters?.requirements?.length) return true;
      const tagNames = course.requirementLinks.map((link) => link.requirementTag.name.toLowerCase());
      return input.filters.requirements.every((requirement) => tagNames.some((tag) => tag.includes(requirement.toLowerCase())));
    })
    .filter((course) => {
      if (!input.filters?.timeWindow) return true;
      return course.timeWindow.toLowerCase().includes(input.filters.timeWindow.toLowerCase());
    })
    .map((course) => {
      const ratings = course.sections.map((section) => section.professorRating).filter(Boolean);
      const quality = ratings.length ? ratings.reduce((sum, rating) => sum + (rating?.qualityScore ?? 0), 0) / ratings.length : 0;
      const avgDifficulty = ratings.length ? ratings.reduce((sum, rating) => sum + (rating?.difficultyScore ?? 0), 0) / ratings.length : 0;
      return {
        id: course.id,
        code: course.code,
        name: course.name,
        type: course.type,
        division: course.division,
        avgDifficulty: Number(avgDifficulty.toFixed(1)),
        difficulty: Number(avgDifficulty.toFixed(1)),
        quality: Number(quality.toFixed(1)),
        timeWindow: course.timeWindow,
        requirementTags: course.requirementLinks.map((link) => link.requirementTag.name),
        fitScore: Math.round(scoreCourse(course, mode) * 100),
        sections: course.sections.map((section) => ({
          id: section.id,
          sectionCode: section.sectionCode,
          instructor: section.instructor,
          days: section.days,
          time: formatRange(section.startTime, section.endTime),
          quality: section.professorRating?.qualityScore ?? quality,
          difficulty: section.professorRating?.difficultyScore ?? avgDifficulty,
          seatsAvailable: section.seatsAvailable ?? null
        }))
      };
    })
    .sort((a, b) => b.fitScore - a.fitScore);
}
