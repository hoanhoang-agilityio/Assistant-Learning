import { PanelLeftOpen, Plus } from "lucide-react";

import {
  CONVERSATION_COPY,
  CONVERSATION_ICON_BUTTON_CLASS,
  CONVERSATION_SIDEBAR_ID,
} from "@/features/conversations/constants/conversations";

export interface ConversationRailViewProps {
  isBusy: boolean;
  /** The list is open over the canvas, as a drawer. */
  isExpanded: boolean;
  onToggle: () => void;
  onNewTopic: () => void;
}

/** The collapsed conversation list: a slim rail with the toggle and "New topic". */
export const ConversationRailView = ({
  isBusy,
  isExpanded,
  onToggle,
  onNewTopic,
}: ConversationRailViewProps) => (
  <nav
    aria-label={CONVERSATION_COPY.heading}
    className="flex w-11 shrink-0 flex-col items-center gap-2 border-r border-slate-200 bg-slate-50 py-3 dark:border-slate-800 dark:bg-slate-900"
  >
    <button
      type="button"
      onClick={onToggle}
      aria-label={CONVERSATION_COPY.expand}
      aria-controls={CONVERSATION_SIDEBAR_ID}
      aria-expanded={isExpanded}
      title={CONVERSATION_COPY.expand}
      className={CONVERSATION_ICON_BUTTON_CLASS}
    >
      <PanelLeftOpen className="h-4 w-4" />
    </button>
    <button
      type="button"
      onClick={onNewTopic}
      disabled={isBusy}
      aria-label={CONVERSATION_COPY.newTopic}
      title={CONVERSATION_COPY.newTopic}
      className={CONVERSATION_ICON_BUTTON_CLASS}
    >
      <Plus className="h-4 w-4" />
    </button>
  </nav>
);
