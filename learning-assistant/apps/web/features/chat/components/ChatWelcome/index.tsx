"use client";

import type { CopilotChatView } from "@copilotkit/react-core/v2";
import type { ComponentProps } from "react";

import { BotAvatar } from "@/features/chat/components/BotAvatar";
import {
  ASSISTANT_BUBBLE_CLASS,
  WELCOME_TEXT,
} from "@/features/chat/constants/chat";

export type ChatWelcomeProps = ComponentProps<
  typeof CopilotChatView.WelcomeScreen
>;

/** Empty chat: a greeting bubble at the top, suggestions and input at the bottom. */
export const ChatWelcome = ({ input, suggestionView }: ChatWelcomeProps) => (
  <div className="flex h-full min-h-0 flex-col">
    <div className="flex-1 overflow-y-auto p-4">
      <div className="flex justify-start gap-3">
        <BotAvatar />
        <div
          className={`${ASSISTANT_BUBBLE_CLASS} max-w-[82%] text-xs leading-relaxed whitespace-pre-wrap`}
        >
          {WELCOME_TEXT}
        </div>
      </div>
    </div>
    {suggestionView}
    {input}
  </div>
);
