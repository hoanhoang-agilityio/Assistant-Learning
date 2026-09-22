import type { ProviderErrorKind } from "@/features/agent/types/errors";

/** Where the server reads provider keys from, as the student sees it. */
export const ENV_FILE_PATH = "apps/web/.env";

/**
 * How each kind of provider failure is recognised: HTTP status codes from the
 * AI SDK's `APICallError`, and patterns in the message for errors without one
 * (or wrapped in a `RetryError`). Checked in this order.
 */
export const PROVIDER_ERROR_MATCHERS: readonly {
  kind: ProviderErrorKind;
  statusCodes: readonly number[];
  pattern: RegExp;
}[] = [
  {
    kind: "auth",
    statusCodes: [401, 403],
    pattern:
      /api key|api_key|x-api-key|unauthori[sz]ed|authentication|permission denied/i,
  },
  {
    kind: "rateLimit",
    statusCodes: [429],
    pattern: /rate limit|quota|too many requests|resource.?exhausted/i,
  },
  {
    kind: "model",
    statusCodes: [404],
    pattern: /model.*(not found|does not exist|not supported)|unknown model/i,
  },
  {
    kind: "overloaded",
    statusCodes: [500, 502, 503, 529],
    pattern: /overloaded|service unavailable|internal server error/i,
  },
  {
    kind: "network",
    statusCodes: [],
    pattern:
      /fetch failed|cannot connect|econnrefused|econnreset|enotfound|etimedout|network/i,
  },
];

/** The opening of the chat message a failed run leaves. */
export const RUN_ERROR_INTRO = "Sorry, that did not work.";
