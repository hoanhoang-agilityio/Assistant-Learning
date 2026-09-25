import {
  type ResearchDraft,
  type ResearchResult,
  ResearchResultSchema,
} from "@repo/shared/schemas";

import { TAVILY_ENV_KEY } from "@/features/agent/constants/agents";
import {
  createResearchPrompt,
  createResearchSystem,
} from "@/features/agent/services/prompts/subagents";
import { searchTavily } from "@/features/agent/services/search/tavily";
import { generateStructured } from "@/features/agent/services/subagents/generate-structured";
import type { SearchResult } from "@/features/agent/types/agents";
import { toResearchDraft } from "@/features/agent/utils/drafts";
import type { Env } from "@/types/env";
import type { RunSettings } from "@/types/llm";

/**
 * The model writes the reading only. Sources come from the search results in
 * code, so a cited URL is always one that was actually retrieved.
 */
const ResearchReadingSchema = ResearchResultSchema.omit({ sources: true });

interface ResearchParams {
  topic: string;
  settings: RunSettings;
  env: Env;
  signal?: AbortSignal;
  /** Called with the research written so far. */
  onDraft?: (draft: ResearchDraft) => void;
}

/** Web results when `TAVILY_API_KEY` is set; none when it is missing or fails. */
const findSources = async (
  topic: string,
  env: Env,
  signal?: AbortSignal,
): Promise<SearchResult[]> => {
  const apiKey = env[TAVILY_ENV_KEY];
  if (!apiKey) {
    return [];
  }
  try {
    return await searchTavily(topic, apiKey, signal);
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    console.warn("[research] Web search failed; using model knowledge.", error);
    return [];
  }
};

/** Research Agent: a short reading on the topic, pitched at the student's level. */
export const runResearch = async ({
  topic,
  settings,
  env,
  signal,
  onDraft,
}: ResearchParams): Promise<ResearchResult> => {
  const results = await findSources(topic, env, signal);
  const sources = results.map(({ title, url }) => ({ title, url }));
  const reading = await generateStructured({
    settings,
    system: createResearchSystem(settings.learningLevel),
    prompt: createResearchPrompt(topic, results),
    schema: ResearchReadingSchema,
    signal,
    onPartial: onDraft
      ? (partial) => onDraft(toResearchDraft(partial, sources))
      : undefined,
  });
  return { ...reading, sources };
};
