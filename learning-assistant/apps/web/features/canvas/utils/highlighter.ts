import type { BundledLanguage, Highlighter } from "shiki";

import { CODE_THEME } from "@/features/canvas/constants/board";
import type { CodeToken } from "@/features/canvas/utils/code-block";

let highlighter: Promise<Highlighter> | null = null;

/**
 * One shiki highlighter for the app, made on first use. shiki is imported
 * here, not at the top, so it stays out of the page bundle until a code
 * block is drawn. The JavaScript regex engine avoids loading WebAssembly.
 */
const getHighlighter = (): Promise<Highlighter> => {
  highlighter ??= import("shiki")
    .then(({ createHighlighter, createJavaScriptRegexEngine }) =>
      createHighlighter({
        themes: [CODE_THEME],
        langs: [],
        engine: createJavaScriptRegexEngine(),
      }),
    )
    .catch((error: unknown) => {
      // Let the next code block try again instead of caching the failure.
      highlighter = null;
      throw error;
    });
  return highlighter;
};

/**
 * The code's tokens, one list per line, or `null` for a language shiki does
 * not know (the block then stays plain). Each grammar loads the first time
 * its language is used. `code` should already be normalized, so the lines
 * match `toCodeLines`.
 */
export const highlightCode = async (
  code: string,
  language: string,
): Promise<CodeToken[][] | null> => {
  const lang = language.trim().toLowerCase();
  const { bundledLanguages } = await import("shiki");
  if (!Object.hasOwn(bundledLanguages, lang)) {
    return null;
  }
  const instance = await getHighlighter();
  await instance.loadLanguage(lang as BundledLanguage);
  const { tokens } = instance.codeToTokens(code, {
    lang: lang as BundledLanguage,
    theme: CODE_THEME,
  });
  return tokens.map((line) =>
    line.map(({ content, color, fontStyle }) => ({
      content,
      color,
      fontStyle,
    })),
  );
};
