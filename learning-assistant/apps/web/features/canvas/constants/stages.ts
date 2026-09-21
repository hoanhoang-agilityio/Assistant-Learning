import type { RunningTask } from "@repo/shared/schemas";
import {
  Award,
  BarChart2,
  BookOpen,
  FileText,
  HelpCircle,
  MessageCircle,
} from "lucide-react";

import type { CanvasStage, StageStep } from "@/features/canvas/types/canvas";

/** The six canvas stages, in flow order. */
export const STAGE_STEPS: readonly StageStep[] = [
  {
    id: "research",
    title: "Research",
    description: "Explore materials & key concepts",
    icon: BookOpen,
    dataKey: "research",
    emptyHint:
      "Ask the assistant to research a topic, e.g. “Research photosynthesis”.",
  },
  {
    id: "notes",
    title: "Notes",
    description: "Synthesize & edit structured insights",
    icon: FileText,
    dataKey: "notes",
    emptyHint:
      "Once research is ready, ask the assistant to turn it into notes.",
  },
  {
    id: "quiz",
    title: "Quiz",
    description: "Test knowledge with dynamic questions",
    icon: HelpCircle,
    dataKey: "quiz",
    emptyHint: "Once your notes are ready, ask the assistant to quiz you.",
  },
  {
    id: "evaluation",
    title: "Evaluation",
    description: "Analyze performance breakdown",
    icon: BarChart2,
    dataKey: "evaluation",
    emptyHint: "Submit the quiz to see how you did on each concept.",
  },
  {
    id: "score",
    title: "Score",
    description: "View mastery tier & badges",
    icon: Award,
    dataKey: "score",
    emptyHint: "Your score and mastery tier appear after you submit the quiz.",
  },
  {
    id: "feedback",
    title: "Feedback",
    description: "Receive personalized AI guidance",
    icon: MessageCircle,
    dataKey: "feedback",
    emptyHint: "Personalised feedback appears after your quiz is evaluated.",
  },
];

/** The stage that shows a skeleton while each subagent task runs. */
export const RUNNING_TASK_STAGE: Record<RunningTask, CanvasStage> = {
  research: "research",
  notes: "notes",
  simplify: "notes",
  quiz: "quiz",
  evaluate: "evaluation",
};

/** The stage the canvas opens on before any work has been done. */
export const FIRST_STAGE: CanvasStage = "research";
