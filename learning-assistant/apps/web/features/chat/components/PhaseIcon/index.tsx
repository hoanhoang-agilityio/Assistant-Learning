import { AlertCircle, CheckCircle2, CircleSlash, Loader2 } from "lucide-react";

import type { ToolPhase } from "@/features/chat/types/chat";

export interface PhaseIconProps {
  phase: ToolPhase;
}

/** The icon for a tool progress card's phase. */
export const PhaseIcon = ({ phase }: PhaseIconProps) => {
  switch (phase) {
    case "running":
      return <Loader2 className="h-4 w-4 shrink-0 animate-spin" />;
    case "done":
      return <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />;
    case "failed":
      return <AlertCircle className="h-4 w-4 shrink-0 text-rose-500" />;
    case "stopped":
      return <CircleSlash className="h-4 w-4 shrink-0" />;
  }
};
