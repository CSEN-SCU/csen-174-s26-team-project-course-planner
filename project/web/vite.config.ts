import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Use relative asset paths so the app works when hosted
  // under a subpath (e.g. GitHub Pages) as well as at domain root.
  base: "./",
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
