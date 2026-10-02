import { useEffect, useRef, useState } from "react";

/**
 * The rendered width of the element `ref` points at, kept up to date as it
 * resizes; `fallback` until it has been measured (and on the server).
 */
export const useElementWidth = <T extends Element>(fallback: number) => {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }

    const observer = new ResizeObserver(([entry]) => {
      if (entry && entry.contentRect.width > 0) {
        setWidth(Math.round(entry.contentRect.width));
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return { ref, width };
};
