import { drizzle } from "drizzle-orm/node-postgres";
import type { PgDatabase, PgQueryResultHKT } from "drizzle-orm/pg-core";
import pg from "pg";

import {
  DATABASE_GLOBAL_KEY,
  DATABASE_URL_ENV_KEY,
  MISSING_DATABASE_URL_ERROR,
} from "./constants";
import * as schema from "./schema";

/** The app's database, whichever driver runs it (Postgres, or PGlite in tests). */
export type Database = PgDatabase<PgQueryResultHKT, typeof schema>;

interface Connection {
  pool: pg.Pool;
  db: Database;
}

const globalDatabase = globalThis as typeof globalThis & {
  [DATABASE_GLOBAL_KEY]?: Connection;
};

const connect = (): Connection => {
  const connectionString = process.env[DATABASE_URL_ENV_KEY];
  if (!connectionString) {
    throw new Error(MISSING_DATABASE_URL_ERROR);
  }

  const pool = new pg.Pool({ connectionString });
  return { pool, db: drizzle(pool, { schema }) };
};

/**
 * The process's one connection pool, opened on first use. Kept on
 * `globalThis` so a dev reload of this module does not open another.
 */
const getConnection = (): Connection =>
  (globalDatabase[DATABASE_GLOBAL_KEY] ??= connect());

/** The pool the checkpointer shares with the domain tables. */
export const getPool = (): pg.Pool => getConnection().pool;

export const getDatabase = (): Database => getConnection().db;
