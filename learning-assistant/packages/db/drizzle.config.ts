import { defineConfig } from "drizzle-kit";

import { DATABASE_URL_ENV_KEY, MIGRATIONS_FOLDER } from "./src/constants";

/** The web app's env file, where `DATABASE_URL` lives. */
const WEB_ENV_FILE = "../../apps/web/.env";

try {
  process.loadEnvFile(WEB_ENV_FILE);
} catch {
  // Use the environment as it is.
}

export default defineConfig({
  dialect: "postgresql",
  schema: "./src/schema.ts",
  out: `./${MIGRATIONS_FOLDER}`,
  dbCredentials: { url: process.env[DATABASE_URL_ENV_KEY] ?? "" },
});
