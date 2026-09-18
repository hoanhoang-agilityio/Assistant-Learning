/** @type {import("lint-staged").Configuration} */
export default {
  "apps/web/**/*.{js,jsx,mjs,cjs,ts,tsx}": (files) => [
    `pnpm --filter web exec eslint --fix --max-warnings 0 ${files.map((f) => JSON.stringify(f)).join(" ")}`,
    `prettier --write ${files.map((f) => JSON.stringify(f)).join(" ")}`,
  ],
  "apps/web/**/*.{json,css,md}": "prettier --write",
};
