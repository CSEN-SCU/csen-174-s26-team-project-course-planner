
Part 2 (Red → Green): We first ran `npm test` in `project/api` and confirmed the Sprint 1 tests were RED. Then we implemented the missing backend security modules `src/auth/session.ts` and `src/auth/password.ts` to satisfy the expected contract for secure sessions (HttpOnly cookie + expiry) and password storage (salted one-way hashing + verification), and re-ran the test suite to verify at least two tests turned GREEN. The remaining RED tests are kept as future-sprint work.

Skill (TDD/testing): We installed the `obra/superpowers` **test-driven-development** skill because it matches our TypeScript + Vitest workflow and enforces a concrete Red→Green→Refactor loop. With the skill loaded, we prompted the AI to generate additional backend tests focused on meaningful security behaviors (session cookie flags and password hashing/verification) and pruned anything redundant. The workflow change was that we wrote each test as a single behavior spec (Arrange/Action/Assert), confirmed it failed for the right reason, and only then implemented the minimal code needed to pass.


