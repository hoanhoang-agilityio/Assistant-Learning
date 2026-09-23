import { useHumanInTheLoop } from "@copilotkit/react-core/v2";
import {
  CONFIRM_NEW_TOPIC_TOOL,
  LEARNING_AGENT_ID,
} from "@repo/shared/constants/agents";
import { ConfirmNewTopicParamsSchema } from "@repo/shared/schemas";

import { NewTopicCard } from "@/features/chat/components/NewTopicCard";
import { NEW_TOPIC_TOOL_DESCRIPTION } from "@/features/chat/constants/new-topic";

/**
 * The human-in-the-loop confirmation before a new topic replaces the current
 * work. Offered to the Supervisor only while learning material or a quiz exists
 * (`isAvailable`); the renderer stays registered either way, so a card
 * already in the chat keeps rendering. Called once from the app shell.
 */
export const useNewTopicTool = (isAvailable: boolean) => {
  useHumanInTheLoop(
    {
      name: CONFIRM_NEW_TOPIC_TOOL,
      agentId: LEARNING_AGENT_ID,
      description: NEW_TOPIC_TOOL_DESCRIPTION,
      parameters: ConfirmNewTopicParamsSchema,
      available: isAvailable,
      render: ({ args, status, respond, result }) => (
        <NewTopicCard
          topic={args.topic}
          status={status}
          respond={respond}
          result={result}
        />
      ),
    },
    [isAvailable],
  );
};
