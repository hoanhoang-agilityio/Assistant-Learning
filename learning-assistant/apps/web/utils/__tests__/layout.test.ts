import { describe, expect, it } from "vitest";

import {
  CANVAS_MIN_WIDTH,
  CHAT_WIDTH,
  DEFAULT_LAYOUT,
} from "@/constants/layout";
import { clampChatWidth, parseLayout, resolveDisplay } from "@/utils/layout";

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
    expect(
      parseLayout({ chatWidth: "wide", chatMode: "popup", viewMode: "tv" }),
    ).toEqual({
      chatWidth: DEFAULT_LAYOUT.chatWidth,
      chatMode: "popup",
      viewMode: DEFAULT_LAYOUT.viewMode,
    });
  });

  it("keeps a collapsed chat saved before chat modes existed", () => {
    expect(parseLayout({ isChatOpen: false }).chatMode).toBe("hidden");
  });
});

describe("resolveDisplay", () => {
  it("docks the chat on a wide window", () => {
    expect(resolveDisplay(DEFAULT_LAYOUT, 1440)).toEqual({
      frameWidth: null,
      width: 1440,
      isCompact: false,
      chat: "docked",
    });
  });

  it("shows a docked chat as a popup on a narrow window", () => {
    expect(resolveDisplay(DEFAULT_LAYOUT, 600).chat).toBe("popup");
  });

  it("frames a previewed device layout on a wider window", () => {
    expect(
      resolveDisplay({ ...DEFAULT_LAYOUT, viewMode: "mobile" }, 1440),
    ).toMatchObject({ frameWidth: 390, isCompact: true, chat: "popup" });
  });

  it("does not frame a device layout wider than the window", () => {
    expect(
      resolveDisplay({ ...DEFAULT_LAYOUT, viewMode: "tablet" }, 500),
    ).toMatchObject({ frameWidth: null, width: 500 });
  });

  it("keeps the chat docked in the desktop view", () => {
    expect(
      resolveDisplay({ ...DEFAULT_LAYOUT, viewMode: "desktop" }, 600).chat,
    ).toBe("docked");
  });

  it("keeps a hidden chat hidden", () => {
    expect(
      resolveDisplay({ ...DEFAULT_LAYOUT, chatMode: "hidden" }, 600).chat,
    ).toBe("hidden");
  });
});
