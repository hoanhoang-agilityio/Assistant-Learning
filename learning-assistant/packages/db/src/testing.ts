import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { drizzle } from "drizzle-orm/pglite";
import { migrate } from "drizzle-orm/pglite/migrator";

import type { Database } from "./client";
import { MIGRATIONS_FOLDER } from "./constants";
import * as schema from "./schema";

/**
 * A fresh in-memory Postgres (PGlite) with every migration applied, for
 * tests. Each call is its own empty database.
 */
export const createTestDatabase = async (): Promise<Database> => {
  const db = drizzle(new PGlite(), { schema });
  await migrate(db, {
    migrationsFolder: fileURLToPath(
      new URL(`../${MIGRATIONS_FOLDER}`, import.meta.url),
    ),
  });
  return db;
};
