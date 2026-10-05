import type { ConversationSummary } from "@repo/shared/schemas";
import { PanelLeftClose, Plus, Search } from "lucide-react";

import { ConversationRailView } from "@/features/conversations/components/ConversationRailView";
import { ConversationRowView } from "@/features/conversations/components/ConversationRowView";
import {
  CONVERSATION_COPY,
  CONVERSATION_ICON_BUTTON_CLASS,
  CONVERSATION_SIDEBAR_ID,
} from "@/features/conversations/constants/conversations";

export interface ConversationSidebarViewProps {
  conversations: ConversationSummary[];
  /** Whether the user has any, before the search filters them. */
  hasConversations: boolean;
  activeId: string | null;
  isOpen: boolean;
  /** Compact screen: the open list lies over the canvas instead of beside it. */
  isDrawer: boolean;
  isBusy: boolean;
  error: string | null;
  query: string;
  editingId: string | null;
  deletingId: string | null;
  onQueryChange: (query: string) => void;
  onNewTopic: () => void;
  onSelect: (id: string) => void;
  onStartRename: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onCancelRename: () => void;
  onRequestDelete: (id: string) => void;
  onDelete: (id: string) => void;
  onCancelDelete: () => void;
  onToggle: () => void;
  onCloseDrawer: () => void;
}

/**
 * Collapsible column left of the chat. Collapsed, it keeps a rail with the
 * toggle and "New topic". As a drawer it opens over the canvas, above a
 * backdrop that closes it, with the rail kept beneath so nothing shifts.
 */
export const ConversationSidebarView = ({
  conversations,
  hasConversations,
  activeId,
  isOpen,
  isDrawer,
  isBusy,
  error,
  query,
  editingId,
  deletingId,
  onQueryChange,
  onNewTopic,
  onSelect,
  onStartRename,
  onRename,
  onCancelRename,
  onRequestDelete,
  onDelete,
  onCancelDelete,
  onToggle,
  onCloseDrawer,
}: ConversationSidebarViewProps) => {
  const rail = (
    <ConversationRailView
      isBusy={isBusy}
      isExpanded={isOpen}
      onToggle={onToggle}
      onNewTopic={onNewTopic}
    />
  );

  if (!isOpen) {
    return rail;
  }

  return (
    <>
      {isDrawer && (
        <>
          {rail}
          <button
            type="button"
            tabIndex={-1}
            aria-label={CONVERSATION_COPY.collapse}
            onClick={onCloseDrawer}
            className="absolute inset-0 z-30 bg-slate-900/30 dark:bg-black/50"
          />
        </>
      )}
      <nav
        id={CONVERSATION_SIDEBAR_ID}
        aria-label={CONVERSATION_COPY.heading}
        className={`flex flex-col border-r border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900 ${
          isDrawer
            ? "absolute inset-y-0 left-0 z-40 w-72 max-w-[85%] shadow-2xl"
            : "w-60 shrink-0"
        }`}
      >
        <div className="flex items-center justify-between px-3 pt-3 pb-2">
          <span className="text-xs font-semibold tracking-wider text-slate-500 uppercase dark:text-slate-400">
            {CONVERSATION_COPY.heading}
          </span>
          <button
            type="button"
            onClick={onToggle}
            aria-label={CONVERSATION_COPY.collapse}
            aria-controls={CONVERSATION_SIDEBAR_ID}
            aria-expanded
            title={CONVERSATION_COPY.collapse}
            className={CONVERSATION_ICON_BUTTON_CLASS}
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-2 px-3 pb-2">
          <button
            type="button"
            onClick={onNewTopic}
            disabled={isBusy}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:opacity-60"
          >
            <Plus className="h-3.5 w-3.5" />
            {CONVERSATION_COPY.newTopic}
          </button>
          <label className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1.5 focus-within:ring-2 focus-within:ring-indigo-500/30 dark:border-slate-700 dark:bg-slate-800">
            <Search className="h-3.5 w-3.5 shrink-0 text-slate-400" />
            <input
              type="search"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder={CONVERSATION_COPY.search}
              aria-label={CONVERSATION_COPY.search}
              className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-400"
            />
          </label>
          {error && (
            <p
              role="alert"
              className="text-[11px] text-rose-600 dark:text-rose-400"
            >
              {error}
            </p>
          )}
        </div>

        <ul className="flex-1 space-y-1 overflow-y-auto px-2 pb-3">
          {conversations.map((conversation) => (
            <ConversationRowView
              key={conversation.id}
              conversation={conversation}
              isActive={conversation.id === activeId}
              isEditing={conversation.id === editingId}
              isDeleting={conversation.id === deletingId}
              isBusy={isBusy}
              onSelect={onSelect}
              onStartRename={onStartRename}
              onRename={onRename}
              onCancelRename={onCancelRename}
              onRequestDelete={onRequestDelete}
              onDelete={onDelete}
              onCancelDelete={onCancelDelete}
            />
          ))}
          {hasConversations && conversations.length === 0 && (
            <li className="px-2 py-4 text-center text-[11px] text-slate-400">
              {CONVERSATION_COPY.noMatches}
            </li>
          )}
        </ul>
      </nav>
    </>
  );
};
