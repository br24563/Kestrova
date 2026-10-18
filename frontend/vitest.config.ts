import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["node_modules", "dist"],
    // Component tests render React into a DOM.
    environmentMatchGlobs: [["src/**/*.test.tsx", "jsdom"]],
  },
});
