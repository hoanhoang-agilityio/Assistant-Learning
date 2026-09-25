import type { PropsOf, RendererProps } from "@copilotkit/a2ui-renderer";

import type { BOARD_COMPONENT_DEFINITIONS } from "@/features/canvas/constants/board-catalog";

export type BoardComponentName = keyof typeof BOARD_COMPONENT_DEFINITIONS;

/** What the A2UI renderer passes to a Board catalog component. */
export type BoardComponentProps<K extends BoardComponentName> = RendererProps<
  PropsOf<typeof BOARD_COMPONENT_DEFINITIONS, K>
>;

/** What the canvas shows: the learning stages or the Board. */
export type CanvasView = "stages" | "board";

/** A code block's Copy button: at rest, or briefly after a copy. */
export type CopyStatus = "idle" | "copied" | "failed";
