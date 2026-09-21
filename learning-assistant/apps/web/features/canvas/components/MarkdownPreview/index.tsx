import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

export interface MarkdownPreviewProps {
  markdown: string;
}

const COMPONENTS: Components = {
  h1: ({ children }) => <h1 className="mb-3 text-lg font-bold">{children}</h1>,
  h2: ({ children }) => (
    <h2 className="mt-5 mb-2 text-base font-bold">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-4 mb-2 text-sm font-bold">{children}</h3>
  ),
  p: ({ children }) => <p className="mb-3 leading-relaxed">{children}</p>,
  ul: ({ children }) => (
    <ul className="mb-3 list-disc space-y-1 pl-5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 list-decimal space-y-1 pl-5">{children}</ol>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-900 dark:text-white">
      {children}
    </strong>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-indigo-600 hover:underline dark:text-indigo-400"
    >
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-900">
      {children}
    </code>
  ),
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-4 border-indigo-200 pl-3 text-slate-500 dark:border-indigo-800 dark:text-slate-400">
      {children}
    </blockquote>
  ),
};

/** Rendered notes (GitHub-flavoured markdown), styled like the canvas. */
export const MarkdownPreview = ({ markdown }: MarkdownPreviewProps) => (
  <div className="min-h-80 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
    <Markdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
      {markdown}
    </Markdown>
  </div>
);
