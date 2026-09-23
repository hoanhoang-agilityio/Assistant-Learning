"use client";

import { SettingsPopoverView } from "@/features/settings/components/SettingsPopoverView";
import { useSettingsPopover } from "@/features/settings/hooks/use-settings-popover";

/** The settings popover, wired to the settings store. */
export const SettingsPopover = () => {
  const {
    isOpen,
    containerRef,
    settings,
    chatMode,
    viewMode,
    handleToggle,
    handleClose,
    handleQuestionCountChange,
    handleLearningLevelChange,
    handleThemeChange,
    handleChatModeChange,
    handleViewModeChange,
  } = useSettingsPopover();

  return (
    <SettingsPopoverView
      isOpen={isOpen}
      containerRef={containerRef}
      settings={settings}
      chatMode={chatMode}
      viewMode={viewMode}
      onToggle={handleToggle}
      onClose={handleClose}
      onQuestionCountChange={handleQuestionCountChange}
      onLearningLevelChange={handleLearningLevelChange}
      onThemeChange={handleThemeChange}
      onChatModeChange={handleChatModeChange}
      onViewModeChange={handleViewModeChange}
    />
  );
};
