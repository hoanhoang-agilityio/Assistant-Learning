import type { ConversationSummary } from "@repo/shared/schemas";
import { initialLearningState } from "@repo/shared/schemas";
import { useEffect, useMemo, useState } from "react";

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
import { useDisplay } from "@/hooks/use-display";
import { useLearningAgent } from "@/hooks/use-learning-agent";
import { useRetakeRequestActions } from "@/hooks/use-retake-request-store";

/**
 * The sidebar's logic: search, switching, "New topic", rename and a delete
 * that asks first. Switching clears the chat and the canvas at once; the
 * chat then reopens the conversation from the server (see
 * `ConversationThread`).
 *
 * On a compact screen the list is a drawer over the canvas: closed until
 * opened, and closed again once a conversation is picked. The saved open
 * state is the wide layout's only.
 */
export const useConversationSidebar = () => {
  const conversations = useConversations();
  const active = useActiveConversation();
  const isSavedOpen = useIsSidebarOpen();
  const { isCompact } = useDisplay();
  const actions = useConversationActions();
  const { agent } = useLearningAgent();
  const { clearRetake } = useRetakeRequestActions();
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const isOpen = isCompact ? isDrawerOpen : isSavedOpen;
  const isDrawerShown = isCompact && isDrawerOpen;

  // Escape closes the drawer, unless it is cancelling a rename.
  useEffect(() => {
    if (!isDrawerShown || editingId !== null) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsDrawerOpen(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isDrawerShown, editingId]);

  const list = useMemo(() => conversations ?? [], [conversations]);
  const visible = useMemo(
    () => filterConversations(list, query),
    [list, query],
  );

  const open = (conversation: ConversationSummary) => {
    setIsDrawerOpen(false);
    if (conversation.id === active?.id) {
      return;
    }
    agent.setMessages([]);
    agent.setState(initialLearningState);
    clearRetake();
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

  const handleToggle = () => {
    if (isCompact) {
      setIsDrawerOpen(!isOpen);
    } else {
      actions.setSidebarOpen(!isOpen);
    }
  };

  return {
    conversations: visible,
    hasConversations: list.length > 0,
    activeId: active?.id ?? null,
    isOpen,
    isDrawer: isCompact,
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
    handleToggle,
    handleCloseDrawer: () => setIsDrawerOpen(false),
  };
};
