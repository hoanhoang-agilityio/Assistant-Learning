import babelParser from "@babel/eslint-parser";
import { fileURLToPath } from "node:url";
import js from "@eslint/js";
import eslintConfigPrettier from "eslint-config-prettier";
import turboPlugin from "eslint-plugin-turbo";
import onlyWarn from "eslint-plugin-only-warn";

/**
 * A shared ESLint configuration for the repository.
 *
 * @type {import("eslint").Linter.Config[]}
 * */
export const config = [
  // ESLint only matches *.js/*.mjs/*.cjs by default; opt TypeScript files in.
  { files: ["**/*.{js,jsx,mjs,cjs,ts,tsx}"] },
  js.configs.recommended,
  eslintConfigPrettier,
  {
    languageOptions: {
      parser: babelParser,
      parserOptions: {
        requireConfigFile: false,
        babelOptions: {
          // Resolve the preset here: Babel resolves bare names from the linted
          // file's package, which may not depend on the preset.
          presets: [
            fileURLToPath(import.meta.resolve("@babel/preset-typescript")),
          ],
          // Babel's extension-based JSX detection doesn't reach ESLint; force it for .tsx.
          overrides: [{ test: /\.tsx$/, parserOpts: { plugins: ["jsx"] } }],
        },
      },
    },
    plugins: {
      turbo: turboPlugin,
    },
    rules: {
      "turbo/no-undeclared-env-vars": "warn",
    },
  },
  {
    // Core rules that can't see TypeScript types and misfire on them; tsc covers
    // these (mirrors typescript-eslint's eslint-recommended overrides).
    files: ["**/*.{ts,tsx}"],
    rules: {
      "no-undef": "off",
      "no-redeclare": "off",
      "no-dupe-args": "off",
      "no-dupe-class-members": "off",
      "no-unused-vars": "off",
    },
  },
  {
    plugins: {
      onlyWarn,
    },
  },
  {
    ignores: ["dist/**"],
  },
];
