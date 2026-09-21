import { Eye, FileText, Pencil, Sparkles } from "lucide-react";

import type { ToggleOption } from "@/features/canvas/types/canvas";
import type { NotesMode, NotesView } from "@/features/canvas/types/notes";

/** Pause in typing before an edit is written to the agent's state. */
export const NOTES_SAVE_DELAY_MS = 600;

export const NOTES_VIEW_OPTIONS: readonly ToggleOption<NotesView>[] = [
  { id: "original", label: "Original", icon: FileText },
  { id: "simplified", label: "Simplified", icon: Sparkles },
];

export const NOTES_MODE_OPTIONS: readonly ToggleOption<NotesMode>[] = [
  { id: "edit", label: "Edit", icon: Pencil },
  { id: "preview", label: "Preview", icon: Eye },
];

/** Chat messages the Simplify buttons send to the assistant. */
export const SIMPLIFY_ALL_MESSAGE = "Simplify my notes.";
export const SIMPLIFY_SELECTION_INTRO = "Simplify only this part of my notes:";
/** Fences the selected text so the assistant can pass it on exactly. */
export const SELECTION_FENCE = '"""';

export const QUIZ_OUTDATED_TEXT =
  "Your notes changed, so the old quiz and its results were cleared. Ask for a new quiz when your notes are ready.";
