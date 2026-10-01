import type { ConversationSummary } from "@repo/shared/schemas";
import { initialLearningState } from "@repo/shared/schemas";
import { useMemo, useState } from "react";

import { CONVERSATION_COPY } from "@/features/conversations/constants/conversations";
import {
  useActiveConversation,
  useConversationActions,
  useConversations,
  useIsSidebarOpen,
} from "@/features/conversations/hooks/use-conversation-store";
import {
  createConversation,
  deleteConversation,
  updateConversationTitle,
} from "@/features/conversations/services/conversations-client";
import {
  filterConversations,
  pickNextConversation,
  toActiveConversation,
} from "@/features/conversations/utils/conversations";
import { useLearningAgent } from "@/hooks/use-learning-agent";

/**
 * The sidebar's logic: search, switching, "New topic", rename and a delete
 * that asks first. Switching clears the chat and the canvas at once; the
 * chat then reopens the conversation from the server (see
 * `ConversationThread`).
 */
export const useConversationSidebar = () => {
  const conversations = useConversations();
  const active = useActiveConversation();
  const isOpen = useIsSidebarOpen();
  const actions = useConversationActions();
  const { agent } = useLearningAgent();
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const list = useMemo(() => conversations ?? [], [conversations]);
  const visible = useMemo(
    () => filterConversations(list, query),
    [list, query],
  );

  const open = (conversation: ConversationSummary) => {
    if (conversation.id === active?.id) {
      return;
    }
    agent.setMessages([]);
    agent.setState(initialLearningState);
    actions.openConversation(toActiveConversation(conversation));
  };

  /** Runs a server change, showing one message if it fails. */
  const run = async (work: () => Promise<void>) => {
    setIsBusy(true);
    setError(null);
    try {
      await work();
    } catch (workError) {
      console.error("[conversations]", workError);
      setError(CONVERSATION_COPY.actionFailed);
    } finally {
      setIsBusy(false);
    }
  };

  const handleNewTopic = () =>
    run(async () => {
      const created = await createConversation();
      actions.upsertConversation(created);
      open(created);
      setQuery("");
    });

  const handleSelect = (id: string) => {
    const conversation = list.find((item) => item.id === id);
    if (conversation) {
      open(conversation);
    }
  };

  const handleRename = (id: string, title: string) =>
    run(async () => {
      actions.upsertConversation(await updateConversationTitle(id, title));
      setEditingId(null);
    });

  const handleDelete = (id: string) =>
    run(async () => {
      // Move off the conversation before it goes, so the chat never shows
      // a deleted thread.
      if (id === active?.id) {
        const next =
          pickNextConversation(list, id) ?? (await createConversation());
        actions.upsertConversation(next);
        open(next);
      }
      await deleteConversation(id);
      actions.removeConversation(id);
      setDeletingId(null);
    });

  return {
    conversations: visible,
    hasConversations: list.length > 0,
    activeId: active?.id ?? null,
    isOpen,
    isBusy,
    error,
    query,
    editingId,
    deletingId,
    handleQueryChange: setQuery,
    handleNewTopic,
    handleSelect,
    handleStartRename: setEditingId,
    handleCancelRename: () => setEditingId(null),
    handleRename,
    handleRequestDelete: setDeletingId,
    handleCancelDelete: () => setDeletingId(null),
    handleDelete,
    handleToggle: () => actions.setSidebarOpen(!isOpen),
  };
};
