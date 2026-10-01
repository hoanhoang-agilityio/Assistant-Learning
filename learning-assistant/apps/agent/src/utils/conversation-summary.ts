import {
  AIMessage,
  type BaseMessage,
  ToolMessage,
} from "@langchain/core/messages";

import { A2UI_ACTION_TOOL } from "../constants/graph";
import {
  CHARS_PER_TOKEN,
  SUMMARY_ITEM_MAX_CHARS,
  TRUNCATION_MARK,
} from "../constants/memory";

interface SummaryLimits {
  /** Fold only once the messages after the summary pass this many tokens. */
  triggerTokens: number;
  /** Turns that always stay verbatim. */
  keepTurns: number;
}

/** What to fold into the summary after a turn. */
export interface SummaryPlan {
  /** The messages to fold, oldest first. */
  fold: BaseMessage[];
  /** The id of the last of them: the new `summarizedUpTo`. */
  upTo: string;
}

const truncate = (text: string, maxChars: number): string =>
  text.length > maxChars
    ? `${text.slice(0, maxChars).trimEnd()}${TRUNCATION_MARK}`
    : text;

const toToolCalls = (message: BaseMessage) =>
  AIMessage.isInstance(message) ? (message.tool_calls ?? []) : [];

/**
 * The messages the summary does not cover yet: those after `summarizedUpTo`.
 * All of them before the first summary, or when that message is not in the
 * thread: the Supervisor then rereads some of what the summary says rather
 * than miss anything.
 */
export const findUnsummarized = (
  messages: BaseMessage[],
  summarizedUpTo: string | null,
): BaseMessage[] => {
  const index = summarizedUpTo
    ? messages.findIndex(({ id }) => id === summarizedUpTo)
    : -1;
  return index === -1 ? messages : messages.slice(index + 1);
};

/** About how many tokens the messages take: their text and tool call arguments. */
export const estimateTokens = (messages: BaseMessage[]): number =>
  Math.ceil(
    messages.reduce(
      (chars, message) =>
        chars +
        message.text.length +
        toToolCalls(message).reduce(
          (sum, { args }) => sum + JSON.stringify(args).length,
          0,
        ),
      0,
    ) / CHARS_PER_TOKEN,
  );

/** Whether cutting before `index` would leave a tool call before it and its result after. */
const splitsToolCall = (messages: BaseMessage[], index: number): boolean => {
  const before = new Set(
    messages
      .slice(0, index)
      .flatMap((message) => toToolCalls(message).map(({ id }) => id)),
  );
  return messages
    .slice(index)
    .some(
      (message) =>
        ToolMessage.isInstance(message) && before.has(message.tool_call_id),
    );
};

/**
 * Where to cut the messages: everything before the returned index is
 * folded. A cut is always at the start of a turn (a student's message),
 * leaves the last `keepTurns` turns whole, and never separates a tool call
 * from its result. 0 when there is no such place.
 */
export const findSummaryCut = (
  messages: BaseMessage[],
  keepTurns: number,
): number => {
  const turnStarts = messages.flatMap((message, index) =>
    message.type === "human" ? [index] : [],
  );
  // The start of the oldest turn kept is the latest place to cut.
  const cuts = turnStarts
    .slice(0, Math.max(0, turnStarts.length - keepTurns + 1))
    .reverse();
  return cuts.find((cut) => cut > 0 && !splitsToolCall(messages, cut)) ?? 0;
};

/**
 * What to fold into the summary, or `null` while the messages after it are
 * within budget or no turn can be folded yet. Planning again right after a
 * fold finds nothing new to fold, so rerunning it changes nothing.
 */
export const planSummary = (
  messages: BaseMessage[],
  summarizedUpTo: string | null,
  { triggerTokens, keepTurns }: SummaryLimits,
): SummaryPlan | null => {
  const pending = findUnsummarized(messages, summarizedUpTo);
  if (estimateTokens(pending) <= triggerTokens) {
    return null;
  }

  const cut = findSummaryCut(pending, keepTurns);
  const upTo = pending[cut - 1]?.id;
  return cut > 0 && upTo ? { fold: pending.slice(0, cut), upTo } : null;
};

/**
 * The messages as the summariser reads them: who said what, which tools
 * were used, and the start of each result. A surface action (the quiz
 * Submit, with its answers) is left out, should one be in the thread.
 */
export const formatTranscript = (messages: BaseMessage[]): string => {
  const actionCallIds = new Set(
    messages.flatMap((message) =>
      toToolCalls(message)
        .filter(({ name }) => name === A2UI_ACTION_TOOL)
        .map(({ id }) => id),
    ),
  );

  return messages
    .flatMap((message): string[] => {
      if (message.type === "human") {
        return [`Student: ${truncate(message.text, SUMMARY_ITEM_MAX_CHARS)}`];
      }
      if (ToolMessage.isInstance(message)) {
        return actionCallIds.has(message.tool_call_id)
          ? []
          : [
              `Result of ${message.name ?? "a tool"}: ${truncate(message.text, SUMMARY_ITEM_MAX_CHARS)}`,
            ];
      }
      if (!AIMessage.isInstance(message)) {
        return [];
      }
      return [
        ...(message.text
          ? [`Assistant: ${truncate(message.text, SUMMARY_ITEM_MAX_CHARS)}`]
          : []),
        ...toToolCalls(message)
          .filter(({ name }) => name !== A2UI_ACTION_TOOL)
          .map(
            ({ name, args }) =>
              `Assistant used ${name}: ${truncate(JSON.stringify(args), SUMMARY_ITEM_MAX_CHARS)}`,
          ),
      ];
    })
    .join("\n");
};
