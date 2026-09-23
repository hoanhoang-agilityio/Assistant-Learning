import { Eye, FileText, Pencil, Sparkles } from "lucide-react";

import type { ToggleOption } from "@/features/canvas/types/canvas";
import type {
  MaterialMode,
  MaterialView,
} from "@/features/canvas/types/material";

/** Pause in typing before an edit is written to the agent's state. */
export const MATERIAL_SAVE_DELAY_MS = 600;

export const MATERIAL_VIEW_OPTIONS: readonly ToggleOption<MaterialView>[] = [
  { id: "original", label: "Original", icon: FileText },
  { id: "simplified", label: "Simplified", icon: Sparkles },
];

export const MATERIAL_MODE_OPTIONS: readonly ToggleOption<MaterialMode>[] = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "edit", label: "Edit", icon: Pencil },
];

/** The stage opens on the rendered material; the student switches to Edit. */
export const DEFAULT_MATERIAL_MODE: MaterialMode = "preview";

/** Chat messages the Simplify buttons send to the assistant. */
export const SIMPLIFY_ALL_MESSAGE = "Simplify my learning material.";
export const SIMPLIFY_SELECTION_INTRO =
  "Simplify only this part of my learning material:";
/** Fences the selected text so the assistant can pass it on exactly. */
export const SELECTION_FENCE = '"""';

export const QUIZ_OUTDATED_TEXT =
  "Your learning material changed, so the old quiz and its results were cleared. Ask for a new quiz when your learning material is ready.";
