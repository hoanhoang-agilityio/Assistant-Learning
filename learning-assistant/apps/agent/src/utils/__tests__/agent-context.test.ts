import { describe, expect, it } from "vitest";

import { dropA2UIContext } from "../agent-context";

/** An entry the app adds itself. */
const APP_CONTEXT_DESCRIPTION = "The layout on screen right now.";

/** The descriptions CopilotKit 1.72's A2UI support sends, verbatim. */
const A2UI_DESCRIPTIONS = [
  "A2UI catalog capabilities: available catalog IDs and custom component definitions the client can render.",
  "A2UI Component Schema — available components for generating UI surfaces. Use these component names and properties when creating A2UI operations.",
  "A2UI generation guidelines — protocol rules, tool arguments, path rules, data model format, and form/two-way-binding instructions.",
  "A2UI design guidelines — visual design rules, component hierarchy tips, and action handler patterns.",
];

describe("dropA2UIContext", () => {
  it("drops CopilotKit's A2UI entries and keeps the app's own", () => {
    const display = { description: APP_CONTEXT_DESCRIPTION, value: "{}" };
    const context = [
      display,
      ...A2UI_DESCRIPTIONS.map((description) => ({ description, value: "…" })),
    ];

    expect(dropA2UIContext(context)).toEqual([display]);
  });
});
