import type { CSSProperties } from "react";

/** A run of text in one colour and style, as shiki tokenizes a line. */
export interface CodeToken {
  content: string;
  /** Hex colour from the theme; unset means the panel's text colour. */
  color?: string;
  /** shiki's `FontStyle` bit flags: 1 italic, 2 bold, 4 underline, 8 strike. */
  fontStyle?: number;
}

/** One line of a code block, with its 1-based number. */
export interface CodeLine {
  number: number;
  /** The line's text in tokens; a single plain token until highlighted. */
  tokens: CodeToken[];
  isHighlighted: boolean;
}

/** Unix line endings and no trailing newline, so every line is a real one. */
export const normalizeCode = (code: string): string =>
  code.replace(/\r\n?/g, "\n").replace(/\n$/, "");

/**
 * The code split into numbered lines. With `tokenLines` from the
 * highlighter (one list per line of the same normalized code) each line
 * is coloured; otherwise, or if the counts differ, it stays plain.
 * Highlight numbers outside the code are ignored.
 */
export const toCodeLines = (
  code: string,
  highlightLines: readonly number[],
  tokenLines: CodeToken[][] | null = null,
): CodeLine[] => {
  const highlighted = new Set(highlightLines);
  const texts = normalizeCode(code).split("\n");
  const tokens = tokenLines?.length === texts.length ? tokenLines : null;
  return texts.map((text, index) => ({
    number: index + 1,
    tokens: tokens?.[index] ?? [{ content: text }],
    isHighlighted: highlighted.has(index + 1),
  }));
};

const FONT_STYLE = { italic: 1, bold: 2, underline: 4, strikethrough: 8 };

/** The inline style for a token's colour and font style. */
export const toTokenStyle = ({
  color,
  fontStyle = 0,
}: CodeToken): CSSProperties | undefined => {
  if (!color && fontStyle <= 0) {
    return undefined;
  }
  const has = (flag: number) => fontStyle > 0 && (fontStyle & flag) !== 0;
  const decorations = [
    has(FONT_STYLE.underline) && "underline",
    has(FONT_STYLE.strikethrough) && "line-through",
  ].filter(Boolean);
  return {
    color,
    fontStyle: has(FONT_STYLE.italic) ? "italic" : undefined,
    fontWeight: has(FONT_STYLE.bold) ? 600 : undefined,
    textDecorationLine:
      decorations.length > 0 ? decorations.join(" ") : undefined,
  };
};
