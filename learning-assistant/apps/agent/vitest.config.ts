import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
    exclude: ["**/node_modules/**", "**/.next/**", "**/dist/**"],
    passWithNoTests: true,
    // Route-level tests run the whole graph through the runtime handler: a
    // few seconds alone, more under turbo's parallel load.
    testTimeout: 15_000,
  },
});
