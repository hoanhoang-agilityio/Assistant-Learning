import { fixupConfigRules } from "@eslint/compat";
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

import { config as baseConfig } from "@repo/eslint-config/base";

export default defineConfig([
  ...baseConfig,
  // eslint-plugin-react/import/jsx-a11y still call context APIs removed in
  // ESLint 10 (e.g. context.getFilename); fixupConfigRules shims them back in.
  ...fixupConfigRules([...nextVitals, ...nextTs]),
  // Locate the Next app from this file, not the cwd (editors may lint from the repo root).
  { settings: { next: { rootDir: import.meta.dirname } } },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);
