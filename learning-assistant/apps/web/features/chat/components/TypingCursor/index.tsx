import { BotAvatar } from "@/features/chat/components/BotAvatar";

/** Typing indicator shown while the assistant is working. */
export const TypingCursor = () => (
  <div className="flex items-center gap-3 pt-4 text-xs text-slate-400">
    <BotAvatar />
    <div className="flex items-center gap-1 rounded-2xl rounded-bl-none bg-slate-100 px-4 py-3 dark:bg-slate-800">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-400" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-400 [animation-delay:0.2s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-400 [animation-delay:0.4s]" />
    </div>
  </div>
);
