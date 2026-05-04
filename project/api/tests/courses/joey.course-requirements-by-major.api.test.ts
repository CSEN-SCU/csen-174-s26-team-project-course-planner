import { describe, expect, test } from "vitest";
import request from "supertest";
import { createApp } from "../../src/app.js";

// TDD: course requirement backend — list required courses for a major (RED until implemented).

describe("GET /courses/requirements/:major", () => {
  // As a student, I can retrieve the set of courses my major requires so I can plan degree progress.
  test("returns required courses for a given major identifier", async () => {
    // Arrange
    const app = createApp();
    const majorId = "computer-engineering";

    // Action
    const res = await request(app).get(`/courses/requirements/${majorId}`);

    // Assert: contract — 200 with identifiable university core + major staples (ENGR 1, CSEN 174)
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({
      major: majorId,
      requiredCourses: expect.any(Array)
    });
    expect(res.body.requiredCourses.length).toBeGreaterThan(0);
    expect(res.body.requiredCourses).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: expect.stringMatching(/^ENGR\s*1$/i),
          name: expect.stringMatching(/introduction to engineering/i)
        }),
        expect.objectContaining({
          code: "CSEN 174",
          name: expect.stringMatching(/software engineering/i)
        })
      ])
    );
  });
});
