import type { ReactNode } from "react";

export interface MemorySectionProps {
  title: string;
  hint: string;
  children: ReactNode;
}

/** One part of the Memory panel, under a rule: profile, concepts or topics. */
export const MemorySection = ({
  title,
  hint,
  children,
}: MemorySectionProps) => (
  <section className="border-t border-slate-100 pt-5 dark:border-slate-700">
    <h2 className="text-sm font-semibold">{title}</h2>
    <p className="mt-0.5 mb-2 text-xs text-slate-400">{hint}</p>
    {children}
  </section>
);
