import { MaterialResultSchema } from "@repo/shared/schemas";

import type { RunSettings } from "../../types/llm";
import {
  createSimplifyAllPrompt,
  createSimplifySelectionPrompt,
  createSimplifySystem,
} from "../prompts/subagents";
import { generateStructured } from "./generate-structured";

interface SimplifyParams {
  /** The learning material in the view the student is looking at. */
  material: string;
  /** Rewrite only this part of `material`; the whole set when omitted. */
  selection?: string;
  settings: RunSettings;
  signal?: AbortSignal;
  /** Called with the rewrite written so far. */
  onDraft?: (markdown: string) => void;
}

/**
 * Material Agent (simplify): student-friendly markdown for the whole
 * learning material, or for the selection only (the rewritten selection is returned).
 */
export const runSimplify = async ({
  material,
  selection,
  settings,
  signal,
  onDraft,
}: SimplifyParams): Promise<string> => {
  const { markdown } = await generateStructured({
    settings,
    system: createSimplifySystem(settings.learningLevel),
    prompt:
      selection === undefined
        ? createSimplifyAllPrompt(material)
        : createSimplifySelectionPrompt(selection, material),
    schema: MaterialResultSchema,
    signal,
    onPartial: onDraft ? ({ markdown }) => onDraft(markdown ?? "") : undefined,
  });
  return markdown;
};
