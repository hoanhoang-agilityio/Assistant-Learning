import { describe, expect, it } from "vitest";

import {
  type CodeLine,
  normalizeCode,
  toCodeLines,
  toTokenStyle,
} from "@/features/canvas/utils/code-block";

const textOf = ({ tokens }: CodeLine) =>
  tokens.map(({ content }) => content).join("");

describe("normalizeCode", () => {
  it("uses Unix line endings and drops one trailing newline", () => {
    expect(normalizeCode("a\r\nb\rc\n")).toBe("a\nb\nc");
  });
});

describe("toCodeLines", () => {
  it("numbers plain lines and marks the highlighted ones", () => {
    expect(toCodeLines("const a = 1;\nconst b = 2;", [2])).toEqual([
      {
        number: 1,
        tokens: [{ content: "const a = 1;" }],
        isHighlighted: false,
      },
      { number: 2, tokens: [{ content: "const b = 2;" }], isHighlighted: true },
    ]);
  });

  it("drops the empty line after a trailing newline and reads CRLF", () => {
    expect(toCodeLines("a\r\nb\n", []).map(textOf)).toEqual(["a", "b"]);
  });

  it("keeps blank lines inside the code and ignores highlights past the end", () => {
    const lines = toCodeLines("a\n\nb", [3, 9]);
    expect(lines.map(textOf)).toEqual(["a", "", "b"]);
    expect(lines.filter(({ isHighlighted }) => isHighlighted)).toHaveLength(1);
  });

  it("uses the highlighter's tokens, one list per line", () => {
    const tokenLines = [
      [
        { content: "let", color: "#f97583" },
        { content: " x", color: "#e1e4e8" },
      ],
      [{ content: "x", color: "#e1e4e8" }],
    ];
    expect(
      toCodeLines("let x\nx", [], tokenLines).map((line) => line.tokens),
    ).toEqual(tokenLines);
  });

  it("stays plain when the token lines do not match the code", () => {
    const lines = toCodeLines("a\nb", [], [[{ content: "a", color: "#fff" }]]);
    expect(lines.map((line) => line.tokens)).toEqual([
      [{ content: "a" }],
      [{ content: "b" }],
    ]);
  });
});

describe("toTokenStyle", () => {
  it("returns nothing for a plain token", () => {
    expect(toTokenStyle({ content: "x" })).toBeUndefined();
    expect(toTokenStyle({ content: "x", fontStyle: -1 })).toBeUndefined();
  });

  it("maps the colour and shiki's font style flags", () => {
    expect(
      toTokenStyle({
        content: "x",
        color: "#79b8ff",
        fontStyle: 1 | 2 | 4 | 8,
      }),
    ).toEqual({
      color: "#79b8ff",
      fontStyle: "italic",
      fontWeight: 600,
      textDecorationLine: "underline line-through",
    });
  });
});
