import { describe, expect, it } from "vitest";

import {
  CANVAS_MIN_WIDTH,
  CHAT_WIDTH,
  DEFAULT_LAYOUT,
} from "@/constants/layout";
import { clampChatWidth, parseLayout } from "@/utils/layout";

describe("clampChatWidth", () => {
  it("keeps a width inside the limits", () => {
    expect(clampChatWidth(450.4)).toBe(450);
  });

  it.each([
    [0, CHAT_WIDTH.min],
    [5000, CHAT_WIDTH.max],
    [Number.NaN, CHAT_WIDTH.default],
  ])("clamps %s to %s", (width, expected) => {
    expect(clampChatWidth(width)).toBe(expected);
  });

  it("leaves room for the canvas", () => {
    expect(clampChatWidth(700, 1000)).toBe(1000 - CANVAS_MIN_WIDTH);
  });

  it("never goes below the minimum on a narrow screen", () => {
    expect(clampChatWidth(700, 500)).toBe(CHAT_WIDTH.min);
  });
});

describe("parseLayout", () => {
  it("returns the defaults for empty input", () => {
    expect(parseLayout(undefined)).toEqual(DEFAULT_LAYOUT);
  });

  it("keeps valid fields and replaces invalid ones", () => {
    expect(parseLayout({ chatWidth: "wide", isChatOpen: false })).toEqual({
      chatWidth: DEFAULT_LAYOUT.chatWidth,
      isChatOpen: false,
    });
  });
});
