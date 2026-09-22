import type { FeedbackComponentProps } from "@/features/canvas/types/feedback";
import { readList, readText } from "@/features/canvas/utils/a2ui-props";

/** Numbered next steps. */
export const NextStepList = ({
  props,
}: FeedbackComponentProps<"NextStepList">) => {
  const title = readText(props.title);

  return (
    <div className="basis-full rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900">
      {title && (
        <h4 className="mb-2 text-xs font-semibold tracking-wider text-slate-500 uppercase">
          {title}
        </h4>
      )}
      <ol className="list-inside list-decimal space-y-1.5 text-xs leading-relaxed">
        {readList<string>(props.steps).map((step, index) => (
          <li key={index}>{step}</li>
        ))}
      </ol>
    </div>
  );
};
