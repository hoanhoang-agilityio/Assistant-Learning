import type { PropsOf, RendererProps } from "@copilotkit/a2ui-renderer";

import type { CHAT_COMPONENT_DEFINITIONS } from "@/features/chat/constants/chat-catalog";

export type ChatComponentName = keyof typeof CHAT_COMPONENT_DEFINITIONS;

/** What the A2UI renderer passes to a chat catalog component. */
export type ChatComponentProps<K extends ChatComponentName> = RendererProps<
  PropsOf<typeof CHAT_COMPONENT_DEFINITIONS, K>
>;
