"use client";

import { ConversationSidebarView } from "@/features/conversations/components/ConversationSidebarView";
import { useConversationSidebar } from "@/features/conversations/hooks/use-conversation-sidebar";

/** The conversation list next to the chat: search, switch, new topic, rename, delete. */
export const ConversationSidebar = () => {
  const sidebar = useConversationSidebar();

  return (
    <ConversationSidebarView
      conversations={sidebar.conversations}
      hasConversations={sidebar.hasConversations}
      activeId={sidebar.activeId}
      isOpen={sidebar.isOpen}
      isDrawer={sidebar.isDrawer}
      isBusy={sidebar.isBusy}
      error={sidebar.error}
      query={sidebar.query}
      editingId={sidebar.editingId}
      deletingId={sidebar.deletingId}
      onQueryChange={sidebar.handleQueryChange}
      onNewTopic={sidebar.handleNewTopic}
      onSelect={sidebar.handleSelect}
      onStartRename={sidebar.handleStartRename}
      onRename={sidebar.handleRename}
      onCancelRename={sidebar.handleCancelRename}
      onRequestDelete={sidebar.handleRequestDelete}
      onDelete={sidebar.handleDelete}
      onCancelDelete={sidebar.handleCancelDelete}
      onToggle={sidebar.handleToggle}
      onCloseDrawer={sidebar.handleCloseDrawer}
    />
  );
};
