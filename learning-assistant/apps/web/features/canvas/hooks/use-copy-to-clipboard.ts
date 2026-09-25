import { useEffect, useState } from "react";

import { COPIED_RESET_MS } from "@/features/canvas/constants/board";
import type { CopyStatus } from "@/features/canvas/types/board";

/**
 * Copies text and reports the outcome for a moment. A browser can refuse
 * the clipboard (no permission, insecure page); that shows as `failed`
 * rather than a click that seems to do nothing.
 */
export const useCopyToClipboard = (text: string) => {
  const [status, setStatus] = useState<CopyStatus>("idle");

  useEffect(() => {
    if (status === "idle") {
      return;
    }
    const timer = setTimeout(() => setStatus("idle"), COPIED_RESET_MS);
    return () => clearTimeout(timer);
  }, [status]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
  };

  return { status, handleCopy };
};
