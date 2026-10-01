import { CONVERSATION_COPY } from "@/features/conversations/constants/conversations";

export interface ConversationLoadErrorProps {
  message: string;
  onRetry: () => void;
}

/** In place of the app when the conversation list cannot be loaded: nothing works without it. */
export const ConversationLoadError = ({
  message,
  onRetry,
}: ConversationLoadErrorProps) => (
  <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4 font-sans text-slate-800 dark:bg-slate-900 dark:text-slate-100">
    <div role="alert" className="space-y-3 text-center text-sm">
      <p>{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700"
      >
        {CONVERSATION_COPY.retry}
      </button>
    </div>
  </main>
);
