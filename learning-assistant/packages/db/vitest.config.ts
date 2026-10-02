import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
    exclude: ["**/node_modules/**", "**/.next/**", "**/dist/**"],
    passWithNoTests: true,
    // Each test migrates a fresh PGlite database; under turbo's parallel load
    // that alone has passed the 10 s hook default.
    hookTimeout: 30_000,
    testTimeout: 15_000,
  },
});
