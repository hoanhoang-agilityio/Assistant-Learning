import { useDisplay } from "@/hooks/use-display";
import { useLayout, useLayoutActions } from "@/hooks/use-layout-store";

/**
 * The docked chat's width and whether it is on screen, and handlers to hide
 * it, open it again and pop it out.
 */
export const useChatLayout = () => {
  const { chatWidth } = useLayout();
  const { chat } = useDisplay();
  const { setChatMode } = useLayoutActions();

  return {
    chatWidth,
    isDocked: chat === "docked",
    handleHide: () => setChatMode("hidden"),
    handleOpen: () => setChatMode("docked"),
    handlePopOut: () => setChatMode("popup"),
  };
};
