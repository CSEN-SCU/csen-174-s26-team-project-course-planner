import request from "supertest";
import { describe, expect, test, vi } from "vitest";
import { createApp } from "../api/src/app.js";

vi.mock("../api/src/services/courseService.js", () => ({
  getEligibleCourseResults: vi.fn(async () => [{ code: "CSE 130", name: "Programming Languages" }])
}));

describe("Jason schedule API integration", () => {
  // As a student, I can request schedule recommendations from one API endpoint and get plan results back.
  test("POST /schedule/recommend returns an array of schedule plans", async () => {
    // Arrange
    vi.stubEnv("GEMINI_API_KEY", "");
    vi.stubEnv("OPENAI_API_KEY", "");
    const app = createApp();
    const payload = {
      priorities: "balanced",
      selectedDesiredCourses: ["CSE 130"],
      constraints: { maxCourses: 3, timeWindow: "morning" }
    };

    // Action
    const response = await request(app).post("/schedule/recommend").send(payload);

    // Assert
    expect(response.status).toBe(200);
    expect(Array.isArray(response.body)).toBe(true);
    expect(response.body[0]).toMatchObject({
      source: "fallback"
    });
  });
});
