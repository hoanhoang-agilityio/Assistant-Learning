/** Copy for the canvas tabs and the Board. */
export const BOARD_COPY = {
  stagesTab: "Learning path",
  boardTab: "Board",
  title: "Board",
  description: "Views the assistant made for you, newest first",
  newBadge: "New",
  writing: "Writing…",
  emptyTitle: "Nothing on the Board yet",
  emptyHint:
    'Ask the assistant to put something on the canvas, e.g. "make a cheat sheet on closures with code examples".',
} as const;

/** DOM ids linking each canvas tab to its panel. */
export const CANVAS_VIEW_IDS = {
  stages: { tab: "canvas-tab-stages", panel: "canvas-panel-stages" },
  board: { tab: "canvas-tab-board", panel: "canvas-panel-board" },
} as const;

/** Copy for the Board's code blocks. */
export const CODE_BLOCK_COPY = {
  idle: "Copy",
  copied: "Copied",
  failed: "Copy failed",
  copyLabel: "Copy code",
} as const;

/** How long a code block shows "Copied" or "Copy failed", in ms. */
export const COPIED_RESET_MS = 2000;

/**
 * The shiki theme for code blocks. The panel is always dark, so one dark
 * theme is enough; its background is not used.
 */
export const CODE_THEME = "github-dark";
