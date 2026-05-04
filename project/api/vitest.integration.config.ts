import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["./tests/integration/**/*.test.ts"],
    environment: "node",
    pool: "threads",
    fileParallelism: false
  }
});

