import type { ReactNode } from "react";

export interface CenteredPageProps {
  children: ReactNode;
}

/** A full-screen page with its one card centred: the API key and sign-in pages. */
export const CenteredPage = ({ children }: CenteredPageProps) => (
  <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4 font-sans text-slate-800 dark:bg-slate-900 dark:text-slate-100">
    {children}
  </main>
);
