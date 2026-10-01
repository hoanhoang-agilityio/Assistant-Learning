import { API_KEY_ROUTE } from "@repo/shared/constants/routes";

import type { OpenAIErrorKind } from "../types/errors";

/**
 * How each kind of OpenAI failure is recognised: HTTP status codes from the
 * OpenAI SDK's `APIError`, and patterns in the message for errors without
 * one. Checked in this order.
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

/** A run was asked for without a saved OpenAI API key. */
export const MISSING_API_KEY_ERROR = `No OpenAI API key is saved. Enter one on the API key page (${API_KEY_ROUTE}).`;

/** The opening of the chat message a failed run leaves. */
export const RUN_ERROR_INTRO = "Sorry, that did not work.";

/**
 * The result the Supervisor reads for a tool call that never got one: the
 * student stopped it, or never answered its card. Nothing is said about
 * trying again, so an unrelated next message does not restart it.
 */
export const UNANSWERED_TOOL_RESULT =
  "This tool call never returned a result: the student stopped it or left it unanswered. Do not repeat it unless they ask for it again.";
