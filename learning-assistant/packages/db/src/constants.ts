/** The Postgres connection string, read on the server only. */
export const DATABASE_URL_ENV_KEY = "DATABASE_URL";

/** Where `drizzle-kit generate` writes migrations and `migrate` reads them. */
export const MIGRATIONS_FOLDER = "drizzle";

/** Holds the process's pool, database and checkpointer on `globalThis`. */
export const DATABASE_GLOBAL_KEY = "__learningDatabase";
export const CHECKPOINTER_GLOBAL_KEY = "__learningThreadCheckpointer";
export const CHECKPOINTER_SETUP_GLOBAL_KEY =
  "__learningThreadCheckpointerSetup";

export const MISSING_DATABASE_URL_ERROR = `${DATABASE_URL_ENV_KEY} is not set. Add it to apps/web/.env (see .env.example).`;

/** Node network error codes: the database host cannot be reached. */
export const UNREACHABLE_ERROR_CODES = [
  "ENOTFOUND",
  "EAI_AGAIN",
  "ECONNREFUSED",
  "ECONNRESET",
  "ETIMEDOUT",
];

/** The SQLSTATE class of every Postgres connection exception (`08xxx`). */
export const CONNECTION_EXCEPTION_CLASS = "08";

/**
 * Postgres SQLSTATEs that mean the database cannot serve the app yet: no
 * such database, tables or columns missing (not migrated), bad
 * credentials, shutting down, or out of connections.
 */
export const UNAVAILABLE_SQLSTATES = [
  "3D000",
  "42P01",
  "42703",
  "28000",
  "28P01",
  "57P01",
  "57P02",
  "57P03",
  "53300",
];

/** Driver errors that carry no code but mean the connection is gone. */
export const UNAVAILABLE_ERROR_MESSAGES = [
  MISSING_DATABASE_URL_ERROR,
  "Connection terminated unexpectedly",
];

/** How far down an error's `cause` chain to look; Drizzle wraps once. */
export const MAX_ERROR_CAUSE_DEPTH = 5;
