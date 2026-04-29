import { describe, expect, test } from "vitest";

// AI-generated (TDD skill loaded): session cookie respects environment security settings.
describe("auth/session cookie flags", () => {
  // As a student, my session cookie is marked Secure in production so it can’t be sent over insecure connections.
  test("sets secure=true when NODE_ENV=production", async () => {
    // Arrange
    const originalEnv = process.env.NODE_ENV;
    process.env.NODE_ENV = "production";
    const { createSessionCookie } = (await import("../../../src/auth/session.js")) as unknown as {
      createSessionCookie: (input: { studentKey: string }) => { options: { secure?: boolean } };
    };

    // Action
    const cookie = createSessionCookie({ studentKey: "student-1" });

    // Assert
    expect(cookie.options.secure).toBe(true);

    process.env.NODE_ENV = originalEnv;
  });
});

