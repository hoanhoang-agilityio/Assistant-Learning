import { useEffect, useState } from "react";

/** Whole seconds since mount, ticking while `isRunning`. */
export const useElapsedSeconds = (isRunning: boolean) => {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!isRunning) {
      return;
    }
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, [isRunning]);

  return seconds;
};
