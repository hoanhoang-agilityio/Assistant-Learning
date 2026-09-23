import { POPUP_SIZE } from "@/constants/layout";
import { useDisplay } from "@/hooks/use-display";
import { useIsPopupOpen, useLayoutActions } from "@/hooks/use-layout-store";

/**
 * Whether the popup chat is expanded, and its width: the default, or less
 * when the page is narrower so it keeps a gutter on both sides.
 */
export const useChatPopup = () => {
  const isOpen = useIsPopupOpen();
  const { width } = useDisplay();
  const { setPopupOpen } = useLayoutActions();

  return {
    isOpen,
    width: Math.min(POPUP_SIZE.width, width - POPUP_SIZE.gutter * 2),
    handleOpenChange: setPopupOpen,
  };
};
