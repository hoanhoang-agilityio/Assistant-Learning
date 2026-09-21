const quote = (files) => files.map((f) => JSON.stringify(f)).join(" ");

/** ESLint (with the package's own config), then Prettier. */
const lintAndFormat = (pkg) => (files) => [
  `pnpm --filter ${pkg} exec eslint --fix --max-warnings 0 ${quote(files)}`,
  `prettier --write ${quote(files)}`,
];

/** @type {import("lint-staged").Configuration} */
export default {
  "apps/web/**/*.{js,jsx,mjs,cjs,ts,tsx}": lintAndFormat("web"),
  "apps/web/**/*.{json,css,md}": "prettier --write",

  "packages/shared/**/*.{js,jsx,mjs,cjs,ts,tsx}": lintAndFormat("@repo/shared"),
  // eslint-config and typescript-config have no ESLint config of their own.
  "packages/{eslint-config,typescript-config}/**/*.{js,mjs,cjs,json,md}":
    "prettier --write",
  "packages/shared/**/*.{json,md}": "prettier --write",
};
