"use client";

import { ResumeBannerView } from "@/features/conversations/components/ResumeBannerView";
import { useResumeBanner } from "@/features/conversations/hooks/use-resume-banner";

/** Says where a reopened conversation was left off. Hidden when there is nothing to say. */
export const ResumeBanner = () => {
  const { message, handleDismiss } = useResumeBanner();

  if (!message) {
    return null;
  }

  return <ResumeBannerView message={message} onDismiss={handleDismiss} />;
};
