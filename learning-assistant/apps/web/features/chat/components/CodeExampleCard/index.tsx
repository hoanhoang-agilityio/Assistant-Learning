import type { CodeExampleParams } from "@repo/shared/schemas";
import { Code2 } from "lucide-react";

import { ChatCard } from "@/features/chat/components/ChatCard";

/** Every prop is optional while the arguments stream. */
export type CodeExampleCardProps = Partial<CodeExampleParams>;

/** A short snippet and what it shows, drawn by `showCodeExample`. */
export const CodeExampleCard = ({
  title,
  language,
  code,
  explanation,
}: CodeExampleCardProps) => (
  <ChatCard kind="codeExample" icon={Code2} title={title}>
    {code && (
      <div className="mt-2 overflow-hidden rounded-lg bg-slate-900 text-slate-100">
        {language && (
          <span className="block border-b border-slate-700 px-2.5 py-1 font-mono text-[10px] text-slate-400">
            {language}
          </span>
        )}
        <pre className="overflow-x-auto px-2.5 py-2 font-mono text-[11px] leading-relaxed">
          <code>{code}</code>
        </pre>
      </div>
    )}
    {explanation && (
      <p className="mt-2 leading-relaxed text-slate-700 dark:text-slate-200">
        {explanation}
      </p>
    )}
  </ChatCard>
);
