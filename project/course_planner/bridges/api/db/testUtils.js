import { prisma } from "./client.js";

export async function resetDatabase() {
  await prisma.$transaction([
    prisma.courseRequirementTag.deleteMany(),
    prisma.professorRating.deleteMany(),
    prisma.section.deleteMany(),
    prisma.course.deleteMany(),
    prisma.requirementTag.deleteMany(),
    prisma.completedCourse.deleteMany(),
    prisma.planItem.deleteMany(),
    prisma.plan.deleteMany()
  ]);
}

