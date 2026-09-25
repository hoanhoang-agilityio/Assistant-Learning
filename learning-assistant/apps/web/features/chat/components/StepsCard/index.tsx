import type { StepsParams } from "@repo/shared/schemas";
import { ListOrdered } from "lucide-react";

import { ChatCard } from "@/features/chat/components/ChatCard";

/** Optional props, and partial steps, while the arguments stream. */
export interface StepsCardProps {
  title?: string;
  steps?: Partial<StepsParams["steps"][number]>[];
}

/** An ordered process, drawn by `showSteps`. */
export const StepsCard = ({ title, steps = [] }: StepsCardProps) => (
  <ChatCard kind="steps" icon={ListOrdered} title={title}>
    {steps.length > 0 && (
      <ol className="mt-2 space-y-2">
        {steps.map((step, index) => (
          <li key={index} className="flex gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
              {index + 1}
            </span>
            <span className="min-w-0">
              <span className="block font-semibold">{step.title}</span>
              <span className="block text-slate-600 dark:text-slate-300">
                {step.detail}
              </span>
            </span>
          </li>
        ))}
      </ol>
    )}
  </ChatCard>
);
