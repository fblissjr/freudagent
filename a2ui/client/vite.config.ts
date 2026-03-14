import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "../static",
    emptyOutDir: true,
    target: "esnext",
  },
  resolve: {
    dedupe: ["lit"],
  },
  server: {
    proxy: {
      "/api": "http://localhost:8080",
      "/action": "http://localhost:8080",
    },
  },
});
