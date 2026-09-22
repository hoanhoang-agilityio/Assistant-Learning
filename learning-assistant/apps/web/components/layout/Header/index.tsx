"use client";

import { HeaderView } from "@/components/layout/HeaderView";
import { useThemeToggle } from "@/features/settings/hooks/use-theme-toggle";

export const Header = () => {
  const { isDark, handleToggleTheme } = useThemeToggle();

  return <HeaderView isDark={isDark} onToggleTheme={handleToggleTheme} />;
};
