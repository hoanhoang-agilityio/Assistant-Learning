import {
  AIMessage,
  type BaseMessage,
  ToolMessage,
} from "@langchain/core/messages";

import { UNANSWERED_TOOL_RESULT } from "../constants/errors";

const UNANSWERED_RESULT_CONTENT = JSON.stringify({
  ok: false,
  error: UNANSWERED_TOOL_RESULT,
});

/**
 * The history with a result after every tool call that has none. Stop ends
 * a run with its tool call unanswered, and so does a card the student never
 * answered; OpenAI rejects a history like that. Each result goes right after
 * the message that made the call.
 */
export const answerOpenToolCalls = (messages: BaseMessage[]): BaseMessage[] => {
  const answered = new Set(
    messages.flatMap((message) =>
      ToolMessage.isInstance(message) ? [message.tool_call_id] : [],
    ),
  );

  return messages.flatMap((message): BaseMessage[] => {
    if (!AIMessage.isInstance(message)) {
      return [message];
    }
    const open = (message.tool_calls ?? []).flatMap(({ id, name }) =>
      id !== undefined && !answered.has(id)
        ? [
            new ToolMessage({
              name,
              tool_call_id: id,
              content: UNANSWERED_RESULT_CONTENT,
            }),
          ]
        : [],
    );
    return [message, ...open];
  });
};

/** Whether a tool's result says it worked: not `{ ok: false }`. */
export const isToolSuccess = (message: BaseMessage): boolean => {
  try {
    const result: unknown = JSON.parse(message.text);
    return !(
      typeof result === "object" &&
      result !== null &&
      "ok" in result &&
      result.ok === false
    );
  } catch {
    return true;
  }
};
