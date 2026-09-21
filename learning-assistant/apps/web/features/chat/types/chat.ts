import type {
  CopilotChatAssistantMessageProps,
  CopilotChatUserMessageProps,
} from "@copilotkit/react-core/v2";

/** Render function passed as the assistant message slot's `children`. */
export type AssistantMessageLayout = NonNullable<
  CopilotChatAssistantMessageProps["children"]
>;

/** Render function passed as the user message slot's `children`. */
export type UserMessageLayout = NonNullable<
  CopilotChatUserMessageProps["children"]
>;

/** What a tool progress card shows for one subagent tool call. */
export type ToolPhase = "running" | "done" | "failed" | "stopped";

/** The status CopilotKit passes to a tool renderer. */
export type ToolCallStatus = "inProgress" | "executing" | "complete";
