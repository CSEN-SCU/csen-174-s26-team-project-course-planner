import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL(".", import.meta.url));

export default {
  root: projectRoot,
  resolve: {
    dedupe: ["vitest"],
    alias: {
      vitest: fileURLToPath(new URL("./course_planner/node_modules/vitest", import.meta.url)),
      react: fileURLToPath(new URL("./course_planner/node_modules/react", import.meta.url)),
      "react/jsx-runtime": fileURLToPath(new URL("./course_planner/node_modules/react/jsx-runtime.js", import.meta.url)),
      "react-dom": fileURLToPath(new URL("./course_planner/node_modules/react-dom", import.meta.url)),
      "@testing-library/react": fileURLToPath(new URL("./course_planner/node_modules/@testing-library/react", import.meta.url))
    }
  },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["course_planner/tests/**/*.test.ts", "course_planner/tests/**/*.test.tsx"],
    setupFiles: ["course_planner/tests/vitest.setup.ts"]
  }
};
