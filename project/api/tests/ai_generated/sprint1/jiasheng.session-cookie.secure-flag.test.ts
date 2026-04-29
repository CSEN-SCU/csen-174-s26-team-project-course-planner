import { describe, expect, test } from "vitest";

// AI-generated (TDD skill loaded): session cookie respects environment security settings.
describe("auth/session cookie flags", () => {
  // As a student, my session cookie is marked Secure in production so it can’t be sent over insecure connections.
  test("sets secure=true only in production", async () => {
    // Arrange
    const originalEnv = process.env.NODE_ENV;
    const { createSessionCookie } = (await import("../../../src/auth/session.js")) as unknown as {
      createSessionCookie: (input: { studentKey: string }) => { options: { secure?: boolean; httpOnly?: boolean; sameSite?: unknown } };
    };

    try {
      // Action
      process.env.NODE_ENV = "production";
      const prodCookie = createSessionCookie({ studentKey: "student-1" });

      process.env.NODE_ENV = "development";
      const devCookie = createSessionCookie({ studentKey: "student-1" });

      // Assert
      expect(prodCookie.options.secure).toBe(true);
      expect(devCookie.options.secure).toBe(false);
      expect(prodCookie.options.httpOnly).toBe(true);
      expect(prodCookie.options.sameSite).toBe("lax");
    } finally {
      process.env.NODE_ENV = originalEnv;
    }
  });
});

