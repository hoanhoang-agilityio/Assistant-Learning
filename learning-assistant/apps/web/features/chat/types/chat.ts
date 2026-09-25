import type {
  CopilotChatAssistantMessageProps,
  CopilotChatUserMessageProps,
} from "@copilotkit/react-core/v2";
import type { CHAT_CARD_TOOLS } from "@repo/shared/constants/agents";

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

/** The fixed chat cards the Supervisor can pick from (`CHAT_CARD_TOOLS`). */
export type ChatCardKind = keyof typeof CHAT_CARD_TOOLS;
