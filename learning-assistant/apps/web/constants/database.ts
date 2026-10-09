/** What an API route answers while the database cannot serve requests. */
export const DATABASE_UNAVAILABLE_STATUS = 503;
export const DATABASE_UNAVAILABLE_ERROR =
  "The service is temporarily unavailable. Try again shortly.";

/** Seconds a client should wait before trying again, sent as `Retry-After`. */
export const RETRY_AFTER_HEADER = "Retry-After";
export const DATABASE_RETRY_AFTER_SECONDS = "30";
