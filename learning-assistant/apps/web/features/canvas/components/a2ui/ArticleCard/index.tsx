import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { CanvasComponentProps } from "@/features/canvas/types/a2ui";
import { readText } from "@/features/canvas/utils/a2ui-props";

/** A reading card: eyebrow, title, body and one child (the key insight). */
export const ArticleCard = ({
  props,
  children,
}: CanvasComponentProps<"ArticleCard">) => {
  const eyebrow = readText(props.eyebrow);
  return (
    <article className={CARD_CLASS}>
      {eyebrow && (
        <span className="text-xs font-semibold tracking-wider text-indigo-500 uppercase">
          {eyebrow}
        </span>
      )}
      <h3 className="mt-2 mb-2 text-lg font-bold">{readText(props.title)}</h3>
      <p className="mb-4 text-xs leading-relaxed whitespace-pre-wrap text-slate-600 dark:text-slate-300">
        {readText(props.body)}
      </p>
      {props.child && children(props.child)}
    </article>
  );
};
