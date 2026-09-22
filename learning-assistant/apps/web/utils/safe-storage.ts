import type { StateStorage } from "zustand/middleware";

/**
 * Web Storage that never throws. Storage can be missing (server render) or
 * blocked (private mode, disabled site data); values then live in memory
 * for the session.
 */
const createSafeStorage = (getStorage: () => Storage): StateStorage => ({
  getItem: (name) => {
    try {
      return getStorage().getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    try {
      getStorage().setItem(name, value);
    } catch {
      // Keep the in-memory value.
    }
  },
  removeItem: (name) => {
    try {
      getStorage().removeItem(name);
    } catch {
      // Nothing to remove.
    }
  },
});

export const safeLocalStorage = createSafeStorage(() => window.localStorage);

/** Cleared when the tab closes. */
export const safeSessionStorage = createSafeStorage(
  () => window.sessionStorage,
);
