import { DRAFT_INTERVAL_MS } from "../constants/agents";

/**
 * Calls `fn` at most once per `intervalMs`, dropping the calls in between.
 * Each draft holds everything so far, so a dropped one loses nothing the
 * next one (or the result) does not bring.
 */
export const throttleDrafts = <T>(
  fn: (value: T) => void,
  now: () => number = Date.now,
): ((value: T) => void) => {
  let sentAt = -Infinity;
  return (value) => {
    const time = now();
    if (time - sentAt >= DRAFT_INTERVAL_MS) {
      sentAt = time;
      fn(value);
    }
  };
};
