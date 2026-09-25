"use client";

import { CopilotPopup } from "@copilotkit/react-core/v2";

import { CHAT_VIEW_PROPS } from "@/features/chat/constants/chat-view";

export interface ChatPopupViewProps {
  /** Popup mode is on. Otherwise the popup stays mounted but hidden. */
  isVisible: boolean;
  isOpen: boolean;
  /** Popup width in px. */
  width: number;
  onOpenChange: (isOpen: boolean) => void;
}

/**
 * The chat as a floating popup with its own toggle button. It shows the same
 * conversation as the docked panel, since both read the same agent. Hidden
 * with `display: none`, which also hides its fixed-position parts.
 */
export const ChatPopupView = ({
  isVisible,
  isOpen,
  width,
  onOpenChange,
}: ChatPopupViewProps) => (
  <div className={isVisible ? "contents" : "hidden"}>
    <CopilotPopup
      {...CHAT_VIEW_PROPS}
      open={isOpen}
      onOpenChange={onOpenChange}
      width={width}
      clickOutsideToClose={false}
    />
  </div>
);
