import { useLayout, useLayoutActions } from "@/hooks/use-layout-store";

/** The chat panel's width and open state, and a handler to toggle it. */
export const useChatLayout = () => {
  const { chatWidth, isChatOpen } = useLayout();
  const { toggleChat } = useLayoutActions();

  return { chatWidth, isChatOpen, handleToggleChat: toggleChat };
};
