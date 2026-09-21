export interface StageErrorProps {
  message: string;
}

/** A failed subagent run. Retry arrives with the error-handling pass (M6.3). */
export const StageError = ({ message }: StageErrorProps) => (
  <div
    role="alert"
    className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-xs text-rose-700 dark:text-rose-300"
  >
    <strong className="font-semibold">Something went wrong:</strong> {message}
  </div>
);
