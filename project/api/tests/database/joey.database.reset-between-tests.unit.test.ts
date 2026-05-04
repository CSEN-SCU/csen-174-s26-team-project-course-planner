import { describe, expect, test, vi } from "vitest";

// AI-generated (TDD skill loaded): database reset utility uses Prisma safely.
const deleteManyCalls: unknown[] = [];
const prismaMock = {
  course: { deleteMany: vi.fn(async (...args: unknown[]) => void deleteManyCalls.push(["course", ...args])) },
  section: { deleteMany: vi.fn(async (...args: unknown[]) => void deleteManyCalls.push(["section", ...args])) },
  professorRating: { deleteMany: vi.fn(async (...args: unknown[]) => void deleteManyCalls.push(["professorRating", ...args])) },
  requirementTag: { deleteMany: vi.fn(async (...args: unknown[]) => void deleteManyCalls.push(["requirementTag", ...args])) },
  courseRequirementTag: { deleteMany: vi.fn(async (...args: unknown[]) => void deleteManyCalls.push(["courseRequirementTag", ...args])) },
  completedCourse: { deleteMany: vi.fn(async (...args: unknown[]) => void deleteManyCalls.push(["completedCourse", ...args])) },
  planItem: { deleteMany: vi.fn(async (...args: unknown[]) => void deleteManyCalls.push(["planItem", ...args])) },
  plan: { deleteMany: vi.fn(async (...args: unknown[]) => void deleteManyCalls.push(["plan", ...args])) },
  $transaction: vi.fn(async (ops: Array<Promise<unknown>>) => Promise.all(ops))
};

vi.mock("../../../src/db/client.js", () => ({ prisma: prismaMock }));

describe("db/test utilities (unit)", () => {
  // As a developer, I can reset the database through Prisma without touching a real DB in unit tests.
  test("resetDatabase deletes data in a single transaction", async () => {
    // Arrange

    // Action
    // @ts-expect-error - test-only module is resolved at runtime by Vitest
    const { resetDatabase } = (await import("../../../src/db/testUtils.js")) as unknown as {
      resetDatabase: () => Promise<void>;
    };
    await resetDatabase();

    // Assert: runs deletes inside $transaction (ordering inside ops not important here)
    expect(prismaMock.$transaction).toHaveBeenCalledTimes(1);
    expect(prismaMock.courseRequirementTag.deleteMany).toHaveBeenCalled();
    expect(prismaMock.professorRating.deleteMany).toHaveBeenCalled();
    expect(prismaMock.section.deleteMany).toHaveBeenCalled();
    expect(prismaMock.course.deleteMany).toHaveBeenCalled();
    expect(prismaMock.requirementTag.deleteMany).toHaveBeenCalled();
    expect(prismaMock.completedCourse.deleteMany).toHaveBeenCalled();
    expect(prismaMock.planItem.deleteMany).toHaveBeenCalled();
    expect(prismaMock.plan.deleteMany).toHaveBeenCalled();
  });
});

