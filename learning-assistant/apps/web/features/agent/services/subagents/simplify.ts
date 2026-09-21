import { NotesResultSchema, type Settings } from "@repo/shared/schemas";

import {
  createSimplifyAllPrompt,
  createSimplifySelectionPrompt,
  createSimplifySystem,
} from "@/features/agent/services/prompts/subagents";
import { generateStructured } from "@/features/agent/services/subagents/generate-structured";

interface SimplifyParams {
  /** The notes in the view the student is looking at. */
  notes: string;
  /** Rewrite only this part of `notes`; the whole set when omitted. */
  selection?: string;
  settings: Settings;
  signal?: AbortSignal;
}

/**
 * Notes Agent (simplify): student-friendly markdown for the whole set of
 * notes, or for the selection only (the rewritten selection is returned).
 */
export const runSimplify = async ({
  notes,
  selection,
  settings,
  signal,
}: SimplifyParams): Promise<string> => {
  const { markdown } = await generateStructured({
    settings,
    system: createSimplifySystem(settings.learningLevel),
    prompt:
      selection === undefined
        ? createSimplifyAllPrompt(notes)
        : createSimplifySelectionPrompt(selection, notes),
    schema: NotesResultSchema,
    signal,
  });
  return markdown;
};
