import { useSyncExternalStore } from "react";

import { DARK_SCHEME_QUERY } from "@/constants/settings";

const subscribe = (onChange: () => void) => {
  const query = window.matchMedia(DARK_SCHEME_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
};

const getSnapshot = () => window.matchMedia(DARK_SCHEME_QUERY).matches;

const getServerSnapshot = () => false;

/** Whether the device prefers a dark theme; updates when the OS switches. */
export const usePrefersDark = () =>
  useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
