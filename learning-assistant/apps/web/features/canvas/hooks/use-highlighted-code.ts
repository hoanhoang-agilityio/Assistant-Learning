import { useEffect, useState } from "react";

import type { CodeToken } from "@/features/canvas/utils/code-block";
import { highlightCode } from "@/features/canvas/utils/highlighter";

interface Highlighted {
  /** The code and language these tokens are for. */
  key: string;
  tokens: CodeToken[][];
}

/**
 * The code's syntax tokens once shiki has them; `null` until then, for an
 * unknown language, or if highlighting fails, so the block shows plain text
 * rather than nothing. Tokens for older code are never shown.
 */
export const useHighlightedCode = (code: string, language: string) => {
  const [highlighted, setHighlighted] = useState<Highlighted | null>(null);
  const key = `${language}\n${code}`;

  useEffect(() => {
    let isCurrent = true;
    highlightCode(code, language)
      .then((tokens) => {
        if (isCurrent && tokens) {
          setHighlighted({ key, tokens });
        }
      })
      .catch(() => {
        // Plain text is a fine fallback; nothing to report.
      });
    return () => {
      isCurrent = false;
    };
  }, [code, language, key]);

  return highlighted?.key === key ? highlighted.tokens : null;
};
