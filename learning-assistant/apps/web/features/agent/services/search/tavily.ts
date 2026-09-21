import { z } from "zod";

import {
  SEARCH_RESULT_MAX_CHARS,
  TAVILY_MAX_RESULTS,
  TAVILY_SEARCH_URL,
} from "@/features/agent/constants/agents";
import type { SearchResult } from "@/features/agent/types/agents";

const TavilyResponseSchema = z.object({
  results: z.array(
    z.object({
      title: z.string(),
      url: z.string(),
      content: z.string(),
    }),
  ),
});

/**
 * Searches the web with Tavily. Throws on a network, HTTP or response-shape
 * error; the caller decides whether to fall back.
 */
export const searchTavily = async (
  query: string,
  apiKey: string,
  signal?: AbortSignal,
): Promise<SearchResult[]> => {
  const response = await fetch(TAVILY_SEARCH_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      query,
      max_results: TAVILY_MAX_RESULTS,
      search_depth: "basic",
    }),
    signal,
  });
  if (!response.ok) {
    throw new Error(`Tavily search failed with HTTP ${response.status}.`);
  }

  const { results } = TavilyResponseSchema.parse(await response.json());
  return results
    .filter(({ title, url }) => title.length > 0 && url.length > 0)
    .map(({ title, url, content }) => ({
      title,
      url,
      content: content.slice(0, SEARCH_RESULT_MAX_CHARS),
    }));
};
