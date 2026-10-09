import { isDatabaseUnavailableError } from "@repo/db/errors";

import {
  DATABASE_RETRY_AFTER_SECONDS,
  DATABASE_UNAVAILABLE_ERROR,
  DATABASE_UNAVAILABLE_STATUS,
  RETRY_AFTER_HEADER,
} from "@/constants/database";

export const createDatabaseUnavailableResponse = (): Response =>
  Response.json(
    { error: DATABASE_UNAVAILABLE_ERROR },
    {
      status: DATABASE_UNAVAILABLE_STATUS,
      headers: { [RETRY_AFTER_HEADER]: DATABASE_RETRY_AFTER_SECONDS },
    },
  );

/**
 * Runs a route handler and answers 503 when it fails because the database
 * is down or not migrated, so the client can tell an outage from a bug.
 * Any other error is thrown on.
 */
export const catchDatabaseErrors = async (
  run: () => Promise<Response>,
): Promise<Response> => {
  try {
    return await run();
  } catch (error) {
    if (!isDatabaseUnavailableError(error)) {
      throw error;
    }
    console.error("[database] Unavailable", error);
    return createDatabaseUnavailableResponse();
  }
};
