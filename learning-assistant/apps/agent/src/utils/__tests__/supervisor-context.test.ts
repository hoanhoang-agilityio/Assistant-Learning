import { DEFAULT_SETTINGS } from "@repo/shared/constants/settings";
import { initialLearningState } from "@repo/shared/schemas";
import { describe, expect, it } from "vitest";

import { APP_CONTEXT_HEADING, APP_STATE_HEADING } from "../../constants/graph";
import { toSupervisorState } from "../../services/supervisor-state";
import { formatSupervisorContext } from "../supervisor-context";

const STATE = toSupervisorState(
  { ...initialLearningState, topic: "Closures" },
  DEFAULT_SETTINGS,
);

describe("formatSupervisorContext", () => {
  it("lists the app context, then the state as JSON", () => {
    const text = formatSupervisorContext(STATE, [
      { description: "The display", value: '{"theme":"dark"}' },
    ]);

    expect(text).toContain(`${APP_CONTEXT_HEADING}\n`);
    expect(text).toContain('The display:\n{"theme":"dark"}');
    expect(text).toContain('"topic": "Closures"');
    expect(text.indexOf(APP_CONTEXT_HEADING)).toBeLessThan(
      text.indexOf(APP_STATE_HEADING),
    );
  });

  it("leaves the app context out when there is none", () => {
    const text = formatSupervisorContext(STATE, []);

    expect(text).not.toContain(APP_CONTEXT_HEADING);
    expect(text.startsWith(APP_STATE_HEADING)).toBe(true);
  });
});
