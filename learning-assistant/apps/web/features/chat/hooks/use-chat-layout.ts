import { useLayout, useLayoutActions } from "@/hooks/use-layout-store";

/** The chat panel's width and open state, and a handler to toggle it. */
export const useChatLayout = () => {
  const { chatWidth, chatMode } = useLayout();
  const { setChatMode } = useLayoutActions();
  const isChatOpen = chatMode !== "hidden";

  return {
    chatWidth,
    isChatOpen,
    handleToggleChat: () => setChatMode(isChatOpen ? "hidden" : "docked"),
  };
};
