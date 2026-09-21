"use client";

import type { Provider } from "@repo/shared/schemas";

import { SettingsPopoverView } from "@/features/settings/components/SettingsPopoverView";
import { useSettingsPopover } from "@/features/settings/hooks/use-settings-popover";

export interface SettingsPopoverProps {
  /** Providers whose API key is set on the server. */
  availableProviders: readonly Provider[];
}

/** The settings popover, wired to the settings store. */
export const SettingsPopover = ({
  availableProviders,
}: SettingsPopoverProps) => {
  const {
    isOpen,
    containerRef,
    settings,
    models,
    hasProviders,
    canReason,
    handleToggle,
    handleClose,
    handleProviderChange,
    handleModelChange,
    handleReasoningEffortChange,
    handleQuestionCountChange,
    handleLearningLevelChange,
    handleThemeChange,
  } = useSettingsPopover(availableProviders);

  return (
    <SettingsPopoverView
      isOpen={isOpen}
      containerRef={containerRef}
      settings={settings}
      availableProviders={availableProviders}
      models={models}
      hasProviders={hasProviders}
      canReason={canReason}
      onToggle={handleToggle}
      onClose={handleClose}
      onProviderChange={handleProviderChange}
      onModelChange={handleModelChange}
      onReasoningEffortChange={handleReasoningEffortChange}
      onQuestionCountChange={handleQuestionCountChange}
      onLearningLevelChange={handleLearningLevelChange}
      onThemeChange={handleThemeChange}
    />
  );
};
