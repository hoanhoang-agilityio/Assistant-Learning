import {
  MaterialResultSchema,
  type ResearchResult,
} from "@repo/shared/schemas";

import {
  createMaterialPrompt,
  createMaterialSystem,
} from "@/features/agent/services/prompts/subagents";
import { generateStructured } from "@/features/agent/services/subagents/generate-structured";
import type { RunSettings } from "@/types/llm";

interface MaterialParams {
  research: ResearchResult;
  settings: RunSettings;
  signal?: AbortSignal;
  /** Called with the markdown written so far. */
  onDraft?: (markdown: string) => void;
}

/** Material Agent: markdown learning material from the research. */
export const runMakeMaterial = async ({
  research,
  settings,
  signal,
  onDraft,
}: MaterialParams): Promise<string> => {
  const { markdown } = await generateStructured({
    settings,
    system: createMaterialSystem(settings.learningLevel),
    prompt: createMaterialPrompt(research),
    schema: MaterialResultSchema,
    signal,
    onPartial: onDraft ? ({ markdown }) => onDraft(markdown ?? "") : undefined,
  });
  return markdown;
};
