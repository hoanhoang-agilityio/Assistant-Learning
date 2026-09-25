import type { OpenAIErrorKind } from "@/features/agent/types/errors";

/**
 * How each kind of OpenAI failure is recognised: HTTP status codes from the
 * AI SDK's `APICallError`, and patterns in the message for errors without one
 * (or wrapped in a `RetryError`). Checked in this order.
 */
export const OPENAI_ERROR_MATCHERS: readonly {
  kind: OpenAIErrorKind;
  statusCodes: readonly number[];
  pattern: RegExp;
}[] = [
  {
    kind: "auth",
    statusCodes: [401, 403],
    pattern:
      /api key|api_key|unauthori[sz]ed|authentication|permission denied/i,
  },
  {
    kind: "rateLimit",
    statusCodes: [429],
    pattern: /rate limit|quota|too many requests/i,
  },
  {
    kind: "model",
    statusCodes: [404],
    pattern: /model.*(not found|does not exist|not supported)|unknown model/i,
  },
  {
    kind: "overloaded",
    statusCodes: [500, 502, 503],
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

/**
 * The result given to a server tool call that never returned one: the model
 * sent invalid arguments or named a tool that does not exist. It keeps the
 * history valid, since the next request fails if any call has no result.
 */
export const LOST_TOOL_RESULT =
  "This tool call failed before it returned a result (invalid arguments or an unknown tool). Check the tool's arguments and try again.";
