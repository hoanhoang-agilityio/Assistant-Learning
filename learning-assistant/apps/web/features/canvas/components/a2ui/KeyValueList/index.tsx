import { CARD_CLASS } from "@/features/canvas/constants/canvas";
import type { BoardComponentProps } from "@/features/canvas/types/board";
import { readList, readText } from "@/features/canvas/utils/a2ui-props";

/** Labelled facts, one per row; the rows stack on a narrow Board. */
export const KeyValueList = ({
  props,
}: BoardComponentProps<"KeyValueList">) => {
  const title = readText(props.title);

  return (
    <section className={CARD_CLASS}>
      {title && <h3 className="mb-3 text-base font-bold">{title}</h3>}
      <dl className="divide-y divide-slate-200 text-sm dark:divide-slate-700">
        {readList<{ key: string; value: string }>(props.items).map(
          ({ key, value }, index) => (
            <div
              key={index}
              className="grid gap-1 py-2 first:pt-0 last:pb-0 @xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] @xl:gap-4"
            >
              <dt className="font-mono text-xs font-semibold text-indigo-600 dark:text-indigo-300">
                {key}
              </dt>
              <dd className="text-slate-700 dark:text-slate-200">{value}</dd>
            </div>
          ),
        )}
      </dl>
    </section>
  );
};
