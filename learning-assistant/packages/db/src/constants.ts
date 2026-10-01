/** The Postgres connection string, read on the server only. */
export const DATABASE_URL_ENV_KEY = "DATABASE_URL";

/** Where `drizzle-kit generate` writes migrations and `migrate` reads them. */
export const MIGRATIONS_FOLDER = "drizzle";

/** Holds the process's pool, database and checkpointer on `globalThis`. */
export const DATABASE_GLOBAL_KEY = "__learningDatabase";
export const CHECKPOINTER_GLOBAL_KEY = "__learningThreadCheckpointer";

export const MISSING_DATABASE_URL_ERROR = `${DATABASE_URL_ENV_KEY} is not set. Add it to apps/web/.env (see .env.example).`;
