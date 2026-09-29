import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const frontendDir = __dirname;
const srcDir = path.resolve(frontendDir, "src");

export default defineConfig({
  plugins: [react()],
  root: srcDir,
  build: {
    outDir: path.resolve(frontendDir, "dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        bootstrap: path.resolve(srcDir, "bootstrap/index.html"),
        login: path.resolve(srcDir, "login/index.html"),
        admin: path.resolve(srcDir, "admin/index.html"),
        app: path.resolve(srcDir, "app/index.html"),
      },
    },
  },
  server: {
    port: 8193,
    strictPort: true,
    proxy: { "/api": "http://localhost:8184" },
  },
  test: {
    root: frontendDir,
    environment: "jsdom",
    globals: false,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
  },
});
