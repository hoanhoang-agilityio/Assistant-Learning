import { useSyncExternalStore } from "react";

import { FALLBACK_WINDOW_WIDTH } from "@/constants/layout";

const subscribe = (onChange: () => void) => {
  window.addEventListener("resize", onChange);
  return () => window.removeEventListener("resize", onChange);
};

const getSnapshot = () => window.innerWidth;

const getServerSnapshot = () => FALLBACK_WINDOW_WIDTH;

/** The window's inner width in px; updates on resize. */
export const useWindowWidth = () =>
  useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
