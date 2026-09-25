import { POPUP_SIZE } from "@/constants/layout";
import { useDisplay } from "@/hooks/use-display";
import { useIsPopupOpen, useLayoutActions } from "@/hooks/use-layout-store";

/**
 * Whether the popup chat is on screen and expanded, and its width: the
 * default, or less when the page is narrower so it keeps a gutter on both
 * sides. Outside popup mode it stays mounted but hidden and closed.
 */
export const useChatPopup = () => {
  const isPopupOpen = useIsPopupOpen();
  const { width, chat } = useDisplay();
  const { setPopupOpen } = useLayoutActions();
  const isVisible = chat === "popup";

  return {
    isVisible,
    isOpen: isVisible && isPopupOpen,
    width: Math.min(POPUP_SIZE.width, width - POPUP_SIZE.gutter * 2),
    handleOpenChange: setPopupOpen,
  };
};
