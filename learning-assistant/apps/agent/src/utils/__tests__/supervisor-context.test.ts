import { DEFAULT_SETTINGS } from "@repo/shared/constants/settings";
import { initialLearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { APP_CONTEXT_HEADING, APP_STATE_HEADING } from "../../constants/graph";
import { CONVERSATION_SUMMARY_HEADING } from "../../constants/memory";
import { toSupervisorState } from "../../services/supervisor-state";
import { formatSupervisorContext } from "../supervisor-context";

const STATE = toSupervisorState(
  { ...initialLearningState, topic: "Closures" },
  DEFAULT_SETTINGS,
);

const NOTHING_ELSE = {
  state: STATE,
  appContext: [],
  summary: null,
};

describe("formatSupervisorContext", () => {
  it("lists the app context, then the state as JSON", () => {
    const text = formatSupervisorContext({
      ...NOTHING_ELSE,
      appContext: [{ description: "The display", value: '{"theme":"dark"}' }],
    });

    expect(text).toContain(`${APP_CONTEXT_HEADING}\n`);
    expect(text).toContain('The display:\n{"theme":"dark"}');
    expect(text).toContain('"topic": "Closures"');
    expect(text.indexOf(APP_CONTEXT_HEADING)).toBeLessThan(
      text.indexOf(APP_STATE_HEADING),
    );
  });

  it("leaves out every part there is nothing for", () => {
    const text = formatSupervisorContext(NOTHING_ELSE);

    expect(text).not.toContain(APP_CONTEXT_HEADING);
    expect(text).not.toContain(CONVERSATION_SUMMARY_HEADING);
    expect(text.startsWith(APP_STATE_HEADING)).toBe(true);
  });

  it("puts the summary before what changes on every call", () => {
    const text = formatSupervisorContext({
      ...NOTHING_ELSE,
      summary: "The student studied closures.",
    });

    expect(text.indexOf(CONVERSATION_SUMMARY_HEADING)).toBe(0);
    expect(text.indexOf(APP_STATE_HEADING)).toBeGreaterThan(0);
    expect(text).toContain("The student studied closures.");
  });
});
