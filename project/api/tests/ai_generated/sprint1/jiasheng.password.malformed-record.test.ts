import { describe, expect, test } from "vitest";

// AI-generated (TDD skill loaded): malformed stored password records are rejected safely.
describe("auth/password verification", () => {
  // As a student, login fails safely if the stored password record is corrupted, instead of crashing the server.
  test("returns false for malformed stored password strings", async () => {
    // Arrange
    const { verifyPassword } = (await import("../../../src/auth/password.js")) as unknown as {
      verifyPassword: (pw: string, stored: string) => boolean;
    };

    // Action
    const result1 = verifyPassword("pw", "not-a-real-format");
    const result2 = verifyPassword("pw", "bcrypt$saltonly");

    // Assert
    expect(result1).toBe(false);
    expect(result2).toBe(false);
  });
});

