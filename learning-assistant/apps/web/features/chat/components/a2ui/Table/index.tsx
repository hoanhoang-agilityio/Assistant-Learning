import { readList } from "@/features/canvas/utils/a2ui-props";
import type { ChatComponentProps } from "@/features/chat/types/chat-surface";

/** A small table that scrolls sideways when the chat is narrow. */
export const Table = ({ props }: ChatComponentProps<"Table">) => {
  const columns = readList<string>(props.columns);
  const rows = readList<string[]>(props.rows);

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
      <table className="w-full text-left">
        <thead className="bg-slate-50 dark:bg-slate-900/60">
          <tr>
            {columns.map((column, index) => (
              <th key={index} className="px-2.5 py-1.5 font-semibold">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="border-t border-slate-200 align-top dark:border-slate-700"
            >
              {columns.map((_, cellIndex) => (
                <td key={cellIndex} className="px-2.5 py-1.5">
                  {row[cellIndex] ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
