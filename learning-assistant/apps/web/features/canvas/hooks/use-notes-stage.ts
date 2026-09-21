import type { Notes } from "@repo/shared/schemas";
import {
  type SyntheticEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  NOTES_SAVE_DELAY_MS,
  SIMPLIFY_ALL_MESSAGE,
} from "@/features/canvas/constants/notes";
import { useSendMessage } from "@/features/canvas/hooks/use-send-message";
import type { NotesMode, NotesView } from "@/features/canvas/types/notes";
import {
  applyNotesEdit,
  setNotesView,
} from "@/features/canvas/utils/notes-edit";
import { formatSimplifySelectionMessage } from "@/features/canvas/utils/notes-messages";
import { useLearningAgent } from "@/hooks/use-learning-agent";
import { getActiveNotes, readLearningState } from "@/utils/learning-state";

/**
 * The Notes editor. Keystrokes stay in a local draft and are written to the
 * agent's state after a pause (`agent.setState`); the pending edit is flushed
 * first whenever the agent is about to read the notes. Editing is locked
 * while the agent runs, so a server update never races a local edit.
 */
export const useNotesStage = (notes: Notes) => {
  const { agent, isRunning } = useLearningAgent();
  const sendMessage = useSendMessage();
  const [draft, setDraft] = useState<string | null>(null);
  const [mode, setMode] = useState<NotesMode>("edit");
  const [selection, setSelection] = useState("");
  const pendingRef = useRef<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const flush = useCallback(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    const text = pendingRef.current;
    if (text === null) return;
    pendingRef.current = null;

    const current = readLearningState(agent.state);
    const next = applyNotesEdit(current, text);
    if (next !== current) agent.setState(next);
    setDraft(null);
  }, [agent]);

  // Save a pending edit when the stage closes.
  useEffect(() => flush, [flush]);

  const handleChange = (text: string) => {
    setDraft(text);
    pendingRef.current = text;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(flush, NOTES_SAVE_DELAY_MS);
  };

  const handleSelect = (event: SyntheticEvent<HTMLTextAreaElement>) => {
    const { value, selectionStart, selectionEnd } = event.currentTarget;
    setSelection(value.slice(selectionStart, selectionEnd).trim());
  };

  const handleViewChange = (view: NotesView) => {
    flush();
    setSelection("");
    agent.setState(setNotesView(readLearningState(agent.state), view));
  };

  const handleSimplifyAll = () => {
    flush();
    sendMessage(SIMPLIFY_ALL_MESSAGE);
  };

  const handleSimplifySelection = () => {
    if (!selection) return;
    flush();
    sendMessage(formatSimplifySelectionMessage(selection));
    setSelection("");
  };

  const text = draft ?? getActiveNotes(notes);

  return {
    text,
    characterCount: text.length,
    mode,
    view: notes.view,
    hasSimplified: notes.simplified !== null,
    hasSelection: selection.length > 0,
    isSaving: draft !== null,
    isLocked: isRunning,
    handleChange,
    handleSelect,
    handleModeChange: setMode,
    handleViewChange,
    handleSimplifyAll,
    handleSimplifySelection,
  };
};
