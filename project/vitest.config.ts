import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL(".", import.meta.url));

export default {
  root: projectRoot,
  resolve: {
    alias: {
      react: fileURLToPath(new URL("./web/node_modules/react", import.meta.url)),
      "react/jsx-runtime": fileURLToPath(new URL("./web/node_modules/react/jsx-runtime.js", import.meta.url)),
      "react-dom": fileURLToPath(new URL("./web/node_modules/react-dom", import.meta.url)),
      "@testing-library/react": fileURLToPath(new URL("./web/node_modules/@testing-library/react", import.meta.url))
    }
  },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    setupFiles: ["web/src/test/setup.ts"]
  }
};
