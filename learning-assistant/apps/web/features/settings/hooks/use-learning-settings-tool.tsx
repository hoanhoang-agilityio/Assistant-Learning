import { useFrontendTool } from "@copilotkit/react-core/v2";
import {
  LEARNING_AGENT_ID,
  SET_LEARNING_SETTINGS_TOOL,
} from "@repo/shared/constants/agents";
import { SetLearningSettingsParamsSchema } from "@repo/shared/schemas";

import { DisplayToolCard } from "@/components/common/DisplayToolCard";
import {
  LEARNING_SETTINGS_TOOL_COPY,
  SET_LEARNING_SETTINGS_TOOL_DESCRIPTION,
} from "@/constants/settings";
import {
  useSettingsActions,
  useSettingsStore,
} from "@/features/settings/hooks/use-settings-store";
import { describeLearningSettings } from "@/features/settings/utils/settings";

/**
 * Lets the Supervisor change the question count and the learning level. The
 * result is read from the store after the change, so it reports the clamped
 * count. Called once from the app shell.
 */
export const useLearningSettingsTool = () => {
  const { setQuestionCount, setLearningLevel } = useSettingsActions();

  useFrontendTool(
    {
      name: SET_LEARNING_SETTINGS_TOOL,
      agentId: LEARNING_AGENT_ID,
      description: SET_LEARNING_SETTINGS_TOOL_DESCRIPTION,
      parameters: SetLearningSettingsParamsSchema,
      handler: async ({ questionCount, learningLevel }) => {
        if (questionCount !== undefined) {
          setQuestionCount(questionCount);
        }
        if (learningLevel) {
          setLearningLevel(learningLevel);
        }

        return describeLearningSettings(useSettingsStore.getState().settings);
      },
      render: ({ status, args }) => (
        <DisplayToolCard
          status={status}
          copy={LEARNING_SETTINGS_TOOL_COPY}
          detail={[
            args.questionCount && `${args.questionCount} questions`,
            args.learningLevel,
          ]
            .filter(Boolean)
            .join(" · ")}
        />
      ),
    },
    [setQuestionCount, setLearningLevel],
  );
};
