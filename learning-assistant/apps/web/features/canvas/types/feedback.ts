import type { PropsOf, RendererProps } from "@copilotkit/a2ui-renderer";

import type { FEEDBACK_COMPONENT_DEFINITIONS } from "@/features/canvas/constants/feedback-catalog";

export type FeedbackComponentName = keyof typeof FEEDBACK_COMPONENT_DEFINITIONS;

/** What the A2UI renderer passes to a Feedback catalog component. */
export type FeedbackComponentProps<K extends FeedbackComponentName> =
  RendererProps<PropsOf<typeof FEEDBACK_COMPONENT_DEFINITIONS, K>>;

/** The reflection form's draft before it is saved. */
export interface ReflectionDraft {
  /** 0 until a star is picked. */
  rating: number;
  text: string;
}
