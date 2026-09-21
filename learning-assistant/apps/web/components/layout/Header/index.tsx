"use client";

import type { Provider } from "@repo/shared/schemas";

import { HeaderView } from "@/components/layout/HeaderView";
import { useThemeToggle } from "@/features/settings/hooks/use-theme-toggle";

export interface HeaderProps {
  availableProviders: readonly Provider[];
}

export const Header = ({ availableProviders }: HeaderProps) => {
  const { isDark, handleToggleTheme } = useThemeToggle();

  return (
    <HeaderView
      availableProviders={availableProviders}
      isDark={isDark}
      onToggleTheme={handleToggleTheme}
    />
  );
};
