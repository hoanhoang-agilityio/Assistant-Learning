import { NotesResultSchema, type ResearchResult } from "@repo/shared/schemas";

import {
  createNotesPrompt,
  createNotesSystem,
} from "@/features/agent/services/prompts/subagents";
import { generateStructured } from "@/features/agent/services/subagents/generate-structured";
import type { RunSettings } from "@/types/llm";

interface NotesParams {
  research: ResearchResult;
  settings: RunSettings;
  signal?: AbortSignal;
}

/** Notes Agent: markdown study notes from the research. */
export const runMakeNotes = async ({
  research,
  settings,
  signal,
}: NotesParams): Promise<string> => {
  const { markdown } = await generateStructured({
    settings,
    system: createNotesSystem(settings.learningLevel),
    prompt: createNotesPrompt(research),
    schema: NotesResultSchema,
    signal,
  });
  return markdown;
};
