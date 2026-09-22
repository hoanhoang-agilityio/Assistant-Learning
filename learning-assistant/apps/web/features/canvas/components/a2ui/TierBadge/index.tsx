import type { Tier } from "@repo/shared/schemas";
import { Award } from "lucide-react";

import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import { readText, readTier } from "@/features/canvas/utils/a2ui-props";

const TIER_BADGE_CLASS: Record<Tier, string> = {
  Novice: "from-slate-400 to-slate-500 shadow-slate-500/30",
  Practitioner: "from-indigo-400 to-indigo-600 shadow-indigo-500/30",
  Master: "from-amber-400 to-yellow-500 shadow-amber-500/30",
};

/** The mastery tier: a medal, an eyebrow, the tier name and what it means. */
export const TierBadge = ({ props }: CanvasComponentProps<"TierBadge">) => {
  const tier = readTier(props.tier);
  if (!tier) {
    return null;
  }

  return (
    <div className="text-center">
      <div
        className={`mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-tr text-white shadow-lg ${TIER_BADGE_CLASS[tier]}`}
      >
        <Award className="h-10 w-10" />
      </div>
      <span className="text-xs font-bold tracking-wider text-amber-500 uppercase">
        {readText(props.eyebrow)}
      </span>
      <h2 className="mt-1 text-2xl font-extrabold">{tier}</h2>
      <p className="mx-auto mt-2 max-w-md text-xs text-slate-500 dark:text-slate-400">
        {readText(props.description)}
      </p>
    </div>
  );
};
