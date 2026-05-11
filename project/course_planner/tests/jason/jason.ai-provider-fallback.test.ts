import { describe, expect, test } from "vitest";
import { getAiProvider } from "../../bridges/api/ai/scheduleAi";

describe("Jason AI provider fallback", () => {
  test("returns fallback when GEMINI_API_KEY is missing", () => {
    // Arrange
    const env = {} as NodeJS.ProcessEnv;

    // Action
    const provider = getAiProvider(env);

    // Assert
    expect(provider).toBe("fallback");
  });
});

