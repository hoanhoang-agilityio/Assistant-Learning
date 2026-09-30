import { CONFIRM_NEW_TOPIC_TOOL } from "@repo/shared/constants/agents";
import { ToolParamSchemas } from "@repo/shared/schemas";
import {
  getActiveMaterial,
  hasQuizData,
  hasTopicWork,
  readLearningState,
  writeActiveMaterial,
} from "@repo/shared/utils/learning-state";
import { tool } from "langchain";

import {
  TOOL_DESCRIPTIONS,
  TOOL_ERRORS,
  TOPIC_CONFIRMATION_INSTRUCTION,
} from "../../../constants/tools";
import type { SubagentToolDeps } from "../../../types/graph";
import { runMakeMaterial } from "../../subagents/material";
import { runResearch } from "../../subagents/research";
import { runSimplify } from "../../subagents/simplify";
import {
  failStep,
  replyWithoutRunning,
  runSubagentStep,
  type SubagentToolRuntime,
} from "./subagent-step";

/** Research, learning material and simplify. */
export const createMaterialTools = ({ apiKey, env }: SubagentToolDeps) => [
  tool(
    async ({ topic }, runtime: SubagentToolRuntime) => {
      // The model alone cannot be trusted to ask before replacing work. Once
      // the student confirms, the run that follows starts from a cleared
      // state (see `createRunInput`), so this passes.
      if (hasTopicWork(readLearningState(runtime.state))) {
        return replyWithoutRunning("research", runtime, {
          ok: false,
          requires: CONFIRM_NEW_TOPIC_TOOL,
          topic,
          instruction: TOPIC_CONFIRMATION_INSTRUCTION,
        });
      }

      return runSubagentStep("research", runtime, apiKey, async (step) => {
        const research = await runResearch({
          topic,
          settings: step.settings,
          env,
          signal: step.signal,
          onDraft: (draft) =>
            step.reportDraft({ task: "research", research: draft }),
        });
        return {
          ok: true,
          update: { topic, research, quizOutdated: false },
          summary: { topic, title: research.title },
        };
      });
    },
    {
      name: "research",
      description: TOOL_DESCRIPTIONS.research,
      schema: ToolParamSchemas.research,
    },
  ),

  tool(
    (_args, runtime: SubagentToolRuntime) =>
      runSubagentStep("makeMaterial", runtime, apiKey, async (step) => {
        const { research } = step.state;
        if (!research) {
          return failStep(TOOL_ERRORS.noResearch);
        }
        const markdown = await runMakeMaterial({
          research,
          settings: step.settings,
          signal: step.signal,
          onDraft: (draft) =>
            step.reportDraft({ task: "material", markdown: draft }),
        });
        return {
          ok: true,
          update: {
            material: {
              original: markdown,
              simplified: null,
              view: "original",
            },
            quizOutdated: false,
          },
          summary: { characters: markdown.length },
        };
      }),
    {
      name: "makeMaterial",
      description: TOOL_DESCRIPTIONS.makeMaterial,
      schema: ToolParamSchemas.makeMaterial,
    },
  ),

  tool(
    ({ scope, selection }, runtime: SubagentToolRuntime) =>
      runSubagentStep("simplify", runtime, apiKey, async (step) => {
        const { material } = step.state;
        if (!material) {
          return failStep(TOOL_ERRORS.noMaterial);
        }
        const text = getActiveMaterial(material);
        if (scope === "selection" && !selection) {
          return failStep(TOOL_ERRORS.noSelection);
        }
        if (scope === "selection" && selection && !text.includes(selection)) {
          return failStep(TOOL_ERRORS.selectionNotFound);
        }
        const part = scope === "selection" ? selection : undefined;

        // A selection's draft is the whole material with the rewrite so far.
        const toWhole = (markdown: string) =>
          part === undefined ? markdown : text.replace(part, () => markdown);
        const markdown = await runSimplify({
          material: text,
          selection: part,
          settings: step.settings,
          signal: step.signal,
          onDraft: (draft) =>
            step.reportDraft({ task: "simplify", markdown: toWhole(draft) }),
        });

        return {
          ok: true,
          update: {
            material:
              part === undefined
                ? { ...material, simplified: markdown, view: "simplified" }
                : writeActiveMaterial(material, toWhole(markdown)),
            // Simplifying changes the learning material, so an existing quiz
            // is out of date.
            quizOutdated: step.state.quizOutdated || hasQuizData(step.state),
          },
          summary: { scope, characters: markdown.length },
        };
      }),
    {
      name: "simplify",
      description: TOOL_DESCRIPTIONS.simplify,
      schema: ToolParamSchemas.simplify,
    },
  ),
];
