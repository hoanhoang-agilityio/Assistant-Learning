import type { Source } from "@repo/shared/schemas";
import { ExternalLink, Link2 } from "lucide-react";

import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import { readList, readText } from "@/features/canvas/utils/a2ui-props";

/** Cited sources as links, or a note when there are none. */
export const SourceList = ({ props }: CanvasComponentProps<"SourceList">) => {
  const sources = readList<Source>(props.sources);
  return (
    <section className={CARD_CLASS}>
      <h4 className="mb-3 flex items-center gap-2 text-sm font-bold">
        <Link2 className="h-4 w-4 text-indigo-500" /> {readText(props.title)}
      </h4>
      {sources.length === 0 ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {readText(props.emptyText)}
        </p>
      ) : (
        <ol className="space-y-2">
          {sources.map(({ title, url }, index) => (
            <li key={url} className="flex items-start gap-2 text-xs">
              <span className="w-4 shrink-0 text-slate-400">{index + 1}.</span>
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-w-0 items-center gap-1 text-indigo-600 hover:underline dark:text-indigo-400"
              >
                <span className="truncate">{title}</span>
                <ExternalLink className="h-3 w-3 shrink-0" />
              </a>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
};
