import { Check, Copy, FileCode2, X } from "lucide-react";

import { CODE_BLOCK_COPY } from "@/features/canvas/constants/board";
import type { CopyStatus } from "@/features/canvas/types/board";
import {
  type CodeLine,
  toTokenStyle,
} from "@/features/canvas/utils/code-block";

const COPY_ICONS = {
  idle: <Copy className="h-3.5 w-3.5" />,
  copied: <Check className="h-3.5 w-3.5 text-emerald-400" />,
  failed: <X className="h-3.5 w-3.5 text-rose-400" />,
} as const satisfies Record<CopyStatus, unknown>;

export interface CodeBlockViewProps {
  language: string;
  /** Shown in the header instead of the language when set. */
  filename: string;
  lines: CodeLine[];
  copyStatus: CopyStatus;
  onCopy: () => void;
}

/**
 * A dark code panel: a header with the file or language and Copy, then
 * numbered lines in syntax colours, highlighted ones tinted. Long lines scroll sideways
 * inside the panel, never the Board.
 */
export const CodeBlockView = ({
  language,
  filename,
  lines,
  copyStatus,
  onCopy,
}: CodeBlockViewProps) => (
  <figure className="min-w-0 overflow-hidden rounded-xl border border-slate-800 bg-slate-950 text-slate-100 shadow-sm">
    <figcaption className="flex items-center justify-between gap-2 border-b border-slate-800 px-3 py-1.5 text-[11px] text-slate-400">
      <span className="flex min-w-0 items-center gap-1.5">
        <FileCode2 className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate font-mono">{filename || language}</span>
        {filename && (
          <span className="shrink-0 rounded bg-slate-800 px-1.5 text-[10px]">
            {language}
          </span>
        )}
      </span>
      <button
        type="button"
        onClick={onCopy}
        aria-label={CODE_BLOCK_COPY.copyLabel}
        className="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 transition-colors hover:bg-slate-800 hover:text-slate-100"
      >
        {COPY_ICONS[copyStatus]}
        <span aria-live="polite">{CODE_BLOCK_COPY[copyStatus]}</span>
      </button>
    </figcaption>
    <pre className="overflow-x-auto py-2 font-mono text-xs leading-relaxed">
      <code className="block min-w-max">
        {lines.map(({ number, tokens, isHighlighted }) => (
          <span
            key={number}
            className={`flex pr-4 ${
              isHighlighted
                ? "border-l-2 border-amber-400 bg-amber-400/10"
                : "border-l-2 border-transparent"
            }`}
          >
            <span
              aria-hidden
              className="w-10 shrink-0 pr-3 text-right text-slate-600 select-none"
            >
              {number}
            </span>
            <span className="whitespace-pre">
              {tokens.map((token, index) => (
                <span key={index} style={toTokenStyle(token)}>
                  {token.content}
                </span>
              ))}
              {/* Keeps an empty line one line tall. */}
              {tokens.every(({ content }) => content === "") && " "}
            </span>
          </span>
        ))}
      </code>
    </pre>
  </figure>
);
