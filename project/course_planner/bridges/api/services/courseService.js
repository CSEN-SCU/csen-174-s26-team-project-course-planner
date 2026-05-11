// Lightweight bridge so `course_planner` tests don't pull API+Prisma deps.
// Tests that need behavior can `vi.mock()` this module.

export async function getEligibleCourseResults() {
  return [];
}

