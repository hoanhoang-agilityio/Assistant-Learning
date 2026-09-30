import { DEFAULT_SETTINGS } from "@repo/shared/constants/settings";
import { describe, expect, it } from "vitest";

import { readAppContext, readRunSettings } from "../run-context";

describe("readRunSettings", () => {
  it("keeps valid settings", () => {
    const settings = {
      questionCount: 12,
      learningLevel: "advanced",
      theme: "dark",
    };

    expect(readRunSettings(settings)).toEqual(settings);
  });

  it.each([undefined, null, "advanced", { questionCount: 99 }])(
    "falls back to the defaults for %j",
    (raw) => {
      expect(readRunSettings(raw)).toEqual(DEFAULT_SETTINGS);
    },
  );
});

describe("readAppContext", () => {
  it("keeps the app's entries and drops CopilotKit's A2UI ones", () => {
    const display = { description: "The display", value: '{"theme":"dark"}' };

    expect(
      readAppContext([
        display,
        { description: "A2UI design guidelines — visual rules", value: "…" },
      ]),
    ).toEqual([display]);
  });

  it.each([undefined, null, "text", { description: "x" }, [{ value: 1 }]])(
    "treats %j as no context",
    (raw) => {
      expect(readAppContext(raw)).toEqual([]);
    },
  );
});
