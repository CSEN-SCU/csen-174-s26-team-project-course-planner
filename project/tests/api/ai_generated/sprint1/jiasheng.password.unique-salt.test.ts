import { describe, expect, test } from "vitest";

// AI-generated (TDD skill loaded): password hashing uses unique salts.
describe("auth/password hashing", () => {
  // As a student, two accounts with the same password still get different stored hashes so attackers can’t detect password reuse.
  test("produces different hashes for the same password via unique salts", async () => {
    // Arrange
    const password = "same-password";
    const { hashPassword } = (await import("../../../../course_planner/bridges/api/auth/password.js")) as unknown as {
      hashPassword: (pw: string) => string;
    };

    // Action
    const a = hashPassword(password);
    const b = hashPassword(password);

    // Assert
    expect(a).not.toBe(b);
    expect(a).toMatch(/^scrypt\$/);
    expect(b).toMatch(/^scrypt\$/);
  });
});

