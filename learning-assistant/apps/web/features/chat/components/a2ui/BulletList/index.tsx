import { readBoolean, readList } from "@/features/canvas/utils/a2ui-props";
import type { ChatComponentProps } from "@/features/chat/types/chat-surface";

/** Short points; numbered when `ordered`. */
export const BulletList = ({ props }: ChatComponentProps<"BulletList">) => {
  const items = readList<string>(props.items);
  const className =
    "list-inside space-y-1 leading-relaxed text-slate-700 dark:text-slate-200";

  return readBoolean(props.ordered) ? (
    <ol className={`${className} list-decimal`}>
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ol>
  ) : (
    <ul className={`${className} list-disc`}>
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
};
