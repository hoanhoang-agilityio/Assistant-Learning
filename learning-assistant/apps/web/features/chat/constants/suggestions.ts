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
      message:
        "Do the whole flow on black holes: research, learning material and a quiz.",
    },
  ],
  research: [
    {
      title: "Make learning material",
      message: "Turn the research into learning material.",
    },
    {
      title: "Explain the key insight",
      message: "Explain the key insight in simpler words.",
    },
  ],
  material: [
    {
      title: "Simplify my learning material",
      message: "Simplify my learning material.",
    },
    { title: "Quiz me", message: "Quiz me on my learning material." },
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
