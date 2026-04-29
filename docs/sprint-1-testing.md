
Part 2 
jiasheng huang: (Red → Green): We first ran `npm test` in `project/api` and confirmed the Sprint 1 tests were RED. Then we implemented the missing backend security modules `src/auth/session.ts` and `src/auth/password.ts` to satisfy the expected contract for secure sessions (HttpOnly cookie + expiry) and password storage (salted one-way hashing + verification), and re-ran the test suite to verify at least two tests turned GREEN. The remaining RED tests are kept as future-sprint work.

Skill (TDD/testing): We installed the `obra/superpowers` **test-driven-development** skill because it matches our TypeScript + Vitest workflow and enforces a concrete Red→Green→Refactor loop. With the skill loaded, we prompted the AI to generate additional backend tests focused on meaningful security behaviors (session cookie flags and password hashing/verification) and pruned anything redundant. The workflow change was that we wrote each test as a single behavior spec (Arrange/Action/Assert), confirmed it failed for the right reason, and only then implemented the minimal code needed to pass.

Part 4 (AI critique): We picked two AI-generated tests from `project/api/tests/ai_generated/sprint1/`.

1) `jiasheng.session-cookie.secure-flag.test.ts`
This test mostly expresses a real user need (session cookies should be safe in production), not just an implementation detail, but the original version was too narrow because it only asserted the production case. It should not break under refactors as long as the observable cookie flags remain the same; however, it could become brittle if we change internal representation of cookie options without changing what the browser receives. The missing input was the non-production environment case (development/test) and a basic assertion that the cookie remains HttpOnly + SameSite=Lax, which are security requirements users implicitly rely on.

2) `jiasheng.password.unique-salt.test.ts`
This test expresses a user/security need (stored passwords should not reveal reuse across accounts) rather than “what the code happens to do,” because unique salts are a domain requirement for password storage. It should survive refactors that keep the same hashing semantics, but it could break if we switch to a different algorithm/encoding even when behavior is still secure (e.g., argon2 instead of scrypt) because it asserts the `scrypt$` prefix. The missing input is a domain-specific check that the stored record has the expected number of parts (scheme/salt/hash) and that verification still succeeds for the correct password and fails for incorrect passwords across multiple stored hashes.

Before/after diff (improved AI-generated test):

```diff
diff --git a/project/api/tests/ai_generated/sprint1/jiasheng.session-cookie.secure-flag.test.ts b/project/api/tests/ai_generated/sprint1/jiasheng.session-cookie.secure-flag.test.ts
index 89a7c2a..f1d3a21 100644
--- a/project/api/tests/ai_generated/sprint1/jiasheng.session-cookie.secure-flag.test.ts
+++ b/project/api/tests/ai_generated/sprint1/jiasheng.session-cookie.secure-flag.test.ts
@@ -3,20 +3,32 @@ import { describe, expect, test } from "vitest";
 // AI-generated (TDD skill loaded): session cookie respects environment security settings.
 describe("auth/session cookie flags", () => {
   // As a student, my session cookie is marked Secure in production so it can’t be sent over insecure connections.
-  test("sets secure=true when NODE_ENV=production", async () => {
+  test("sets secure=true only in production", async () => {
     // Arrange
     const originalEnv = process.env.NODE_ENV;
-    process.env.NODE_ENV = "production";
     const { createSessionCookie } = (await import("../../../src/auth/session.js")) as unknown as {
-      createSessionCookie: (input: { studentKey: string }) => { options: { secure?: boolean } };
+      createSessionCookie: (input: { studentKey: string }) => { options: { secure?: boolean; httpOnly?: boolean; sameSite?: unknown } };
     };
 
-    // Action
-    const cookie = createSessionCookie({ studentKey: "student-1" });
-
-    // Assert
-    expect(cookie.options.secure).toBe(true);
-
-    process.env.NODE_ENV = originalEnv;
+    try {
+      // Action
+      process.env.NODE_ENV = "production";
+      const prodCookie = createSessionCookie({ studentKey: "student-1" });
+
+      process.env.NODE_ENV = "development";
+      const devCookie = createSessionCookie({ studentKey: "student-1" });
+
+      // Assert
+      expect(prodCookie.options.secure).toBe(true);
+      expect(devCookie.options.secure).toBe(false);
+      expect(prodCookie.options.httpOnly).toBe(true);
+      expect(prodCookie.options.sameSite).toBe("lax");
+    } finally {
+      process.env.NODE_ENV = originalEnv;
+    }
   });
 });
```


