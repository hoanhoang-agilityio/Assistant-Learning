import { useEffect, useRef, useState } from "react";

import {
  useSettings,
  useSettingsActions,
} from "@/features/settings/hooks/use-settings-store";

/**
 * Open state of the settings popover (closes on outside click and Escape),
 * the current settings, and handlers that write them to the store.
 */
export const useSettingsPopover = () => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const settings = useSettings();
  const { setQuestionCount, setLearningLevel, setTheme } = useSettingsActions();

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  return {
    isOpen,
    containerRef,
    settings,
    handleToggle: () => setIsOpen((open) => !open),
    handleClose: () => setIsOpen(false),
    handleQuestionCountChange: setQuestionCount,
    handleLearningLevelChange: setLearningLevel,
    handleThemeChange: setTheme,
  };
};
