import { HOME_ROUTE } from "@repo/shared/constants/routes";
import {
  ArrowLeft,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { type ChangeEvent, useId } from "react";

import {
  API_KEY_FIELD,
  API_KEY_PREFIX,
  OPENAI_KEYS_URL,
} from "@/features/api-key/constants/api-key";

export interface ApiKeyFormViewProps {
  apiKey: string;
  error: string | null;
  hasSavedKey: boolean;
  isPending: boolean;
  isKeyVisible: boolean;
  formAction: (formData: FormData) => void;
  onApiKeyChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onToggleKeyVisibility: () => void;
  onForgetKey: () => void;
}

/** Card where the user enters their OpenAI API key before using the assistant. */
export const ApiKeyFormView = ({
  apiKey,
  error,
  hasSavedKey,
  isPending,
  isKeyVisible,
  formAction,
  onApiKeyChange,
  onToggleKeyVisibility,
  onForgetKey,
}: ApiKeyFormViewProps) => {
  const inputId = useId();
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;

  return (
    <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-xl dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-linear-to-tr from-indigo-500 to-purple-600 text-white shadow-md shadow-indigo-500/20">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-lg leading-tight font-bold tracking-tight">
            Learning Assistant
          </h1>
          <p className="text-xs text-slate-400">
            Connect your OpenAI account to start
          </p>
        </div>
      </div>

      <form action={formAction} className="space-y-4">
        <div>
          <label
            htmlFor={inputId}
            className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-200"
          >
            <KeyRound className="h-4 w-4 text-indigo-500" /> OpenAI API key
          </label>
          <div className="relative">
            <input
              id={inputId}
              name={API_KEY_FIELD}
              type={isKeyVisible ? "text" : "password"}
              value={apiKey}
              onChange={onApiKeyChange}
              placeholder={`${API_KEY_PREFIX}…`}
              autoComplete="off"
              spellCheck={false}
              required
              disabled={isPending}
              aria-invalid={error !== null}
              aria-describedby={error ? errorId : hintId}
              className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pr-10 pl-3 font-mono text-sm transition-all outline-none focus:border-indigo-500 disabled:opacity-60 aria-invalid:border-red-400 dark:border-slate-700 dark:bg-slate-900"
            />
            <button
              type="button"
              onClick={onToggleKeyVisibility}
              aria-label={isKeyVisible ? "Hide key" : "Show key"}
              className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              {isKeyVisible ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          </div>
          {error ? (
            <p
              id={errorId}
              role="alert"
              className="mt-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-700 dark:text-red-300"
            >
              {error}
            </p>
          ) : (
            <p id={hintId} className="mt-2 text-xs text-slate-400">
              The key is checked with OpenAI, then kept encrypted in this tab
              only and cleared when you close it. Create one at{" "}
              <a
                href={OPENAI_KEYS_URL}
                target="_blank"
                rel="noreferrer"
                className="text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400"
              >
                platform.openai.com
              </a>
              .
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={isPending}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          {isPending ? "Checking key…" : "Save and continue"}
        </button>
      </form>

      {hasSavedKey && (
        <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4 text-xs dark:border-slate-700">
          <Link
            href={HOME_ROUTE}
            className="flex items-center gap-1 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Keep the saved key
          </Link>
          <button
            type="button"
            onClick={onForgetKey}
            className="text-red-600 hover:underline dark:text-red-400"
          >
            Forget saved key
          </button>
        </div>
      )}
    </div>
  );
};
