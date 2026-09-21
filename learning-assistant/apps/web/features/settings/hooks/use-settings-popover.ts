import { type Provider, ProviderSchema } from "@repo/shared/schemas";
import { useEffect, useRef, useState } from "react";

import {
  useSettings,
  useSettingsActions,
} from "@/features/settings/hooks/use-settings-store";
import { getModels, supportsReasoning } from "@/utils/models";

/**
 * Open state of the settings popover (closes on outside click and Escape),
 * the current settings, and handlers that write them to the store.
 */
export const useSettingsPopover = (availableProviders: readonly Provider[]) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const settings = useSettings();
  const {
    setProvider,
    setModel,
    setReasoningEffort,
    setQuestionCount,
    setLearningLevel,
    setTheme,
  } = useSettingsActions();

  useEffect(() => {
    if (!isOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const handleProviderChange = (value: string) => {
    const parsed = ProviderSchema.safeParse(value);
    if (parsed.success) setProvider(parsed.data);
  };

  return {
    isOpen,
    containerRef,
    settings,
    models: getModels(settings.provider),
    hasProviders: availableProviders.length > 0,
    canReason: supportsReasoning(settings.provider, settings.model),
    handleToggle: () => setIsOpen((open) => !open),
    handleClose: () => setIsOpen(false),
    handleProviderChange,
    handleModelChange: setModel,
    handleReasoningEffortChange: setReasoningEffort,
    handleQuestionCountChange: setQuestionCount,
    handleLearningLevelChange: setLearningLevel,
    handleThemeChange: setTheme,
  };
};
