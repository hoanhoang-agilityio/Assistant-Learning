import type { StateStorage } from "zustand/middleware";

/**
 * `localStorage` that never throws. Storage can be missing (server render) or
 * blocked (private mode, disabled site data); settings then live in memory
 * for the session.
 */
export const safeLocalStorage: StateStorage = {
  getItem: (name) => {
    try {
      return window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    try {
      window.localStorage.setItem(name, value);
    } catch {
      // Keep the in-memory value.
    }
  },
  removeItem: (name) => {
    try {
      window.localStorage.removeItem(name);
    } catch {
      // Nothing to remove.
    }
  },
};
