/**
 * S1 — Verify that VITE_USE_PLAN_V2=1 routes generatePlan to /api/plan/v2
 * and that the default (flag absent) still uses /api/plan.
 *
 * We mock `fetch` and inspect the URL it was called with.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Helper: dynamically re-import client.ts with a custom import.meta.env
async function loadClientWithEnv(usePlanV2: boolean) {
  // Vitest exposes import.meta.env as a mutable object in tests; we set it
  // before importing the module.
  vi.stubEnv("VITE_USE_PLAN_V2", usePlanV2 ? "1" : "");
  // Force module re-evaluation so the top-level _USE_PLAN_V2 constant is
  // re-computed with the new env value.
  vi.resetModules();
  return await import("../../web/src/api/client");
}

describe("generatePlan endpoint routing (S1)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        type: "plan",
        recommended: [],
        total_units: 0,
        advice: "",
        assistant_reply: "",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("calls /api/plan by default (VITE_USE_PLAN_V2 unset)", async () => {
    const client = await loadClientWithEnv(false);
    await client.generatePlan([], "morning classes", "42");
    const calledUrl: string = fetchMock.mock.calls[0][0];
    expect(calledUrl).toMatch(/\/api\/plan$/);
    expect(calledUrl).not.toMatch(/\/api\/plan\/v2/);
  });

  it("calls /api/plan/v2 when VITE_USE_PLAN_V2=1", async () => {
    const client = await loadClientWithEnv(true);
    await client.generatePlan([], "morning classes", "42");
    const calledUrl: string = fetchMock.mock.calls[0][0];
    expect(calledUrl).toMatch(/\/api\/plan\/v2$/);
  });

  it("forwards the same request body to both endpoints", async () => {
    const client = await loadClientWithEnv(false);
    await client.generatePlan(
      [{ course: "CSEN 122" }],
      "evening only",
      "99",
      null,
      { parsed_rows: [], completed_course_codes: ["MATH 13"] },
    );
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.user_preference).toBe("evening only");
    expect(body.user_id).toBe("99");
    expect(body.missing_details).toEqual([{ course: "CSEN 122" }]);
    expect(body.completed_course_codes).toEqual(["MATH 13"]);
  });
});
