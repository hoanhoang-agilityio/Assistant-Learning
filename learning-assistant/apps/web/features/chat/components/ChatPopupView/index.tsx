"use client";

import { CopilotPopup } from "@copilotkit/react-core/v2";

import { CHAT_VIEW_PROPS } from "@/features/chat/constants/chat-view";

export interface ChatPopupViewProps {
  isOpen: boolean;
  /** Popup width in px. */
  width: number;
  onOpenChange: (isOpen: boolean) => void;
}

/**
 * The chat as a floating popup with its own toggle button. It shows the same
 * conversation as the docked panel, since both read the same agent.
 */
export const ChatPopupView = ({
  isOpen,
  width,
  onOpenChange,
}: ChatPopupViewProps) => (
  <CopilotPopup
    {...CHAT_VIEW_PROPS}
    open={isOpen}
    onOpenChange={onOpenChange}
    width={width}
    clickOutsideToClose={false}
  />
);
