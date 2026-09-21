import type { Stage } from "@repo/shared/schemas";

/** Quick prompts under the chat, chosen by the stage the agent last finished. */
export const STAGE_SUGGESTIONS: Record<
  Stage,
  readonly { title: string; message: string }[]
> = {
  idle: [
    {
      title: "Research photosynthesis",
      message: "Research photosynthesis for me.",
    },
    {
      title: "Learn JavaScript closures",
      message: "Research JavaScript closures for me.",
    },
    {
      title: "Do everything on black holes",
      message: "Do the whole flow on black holes: research, notes and a quiz.",
    },
  ],
  research: [
    { title: "Make notes", message: "Turn the research into notes." },
    {
      title: "Explain the key insight",
      message: "Explain the key insight in simpler words.",
    },
  ],
  notes: [
    { title: "Simplify my notes", message: "Simplify my notes." },
    { title: "Quiz me", message: "Quiz me on my notes." },
  ],
  quiz: [
    { title: "New questions", message: "Give me a new set of questions." },
  ],
  evaluation: [
    {
      title: "Explain my weakest concept",
      message: "Explain my weakest concept again.",
    },
    { title: "New questions", message: "Give me a new set of questions." },
  ],
  score: [
    { title: "What should I review?", message: "What should I review next?" },
  ],
  feedback: [
    { title: "Start a new topic", message: "I want to learn a new topic." },
  ],
};
