import type { ComparisonParams } from "@repo/shared/schemas";
import { Columns2 } from "lucide-react";

import { ChatCard } from "@/features/chat/components/ChatCard";

/** Optional props, and partial rows, while the arguments stream. */
export interface ComparisonCardProps {
  left?: string;
  right?: string;
  rows?: Partial<ComparisonParams["rows"][number]>[];
  verdict?: string;
}

/** Two things side by side, drawn by `showComparison`. */
export const ComparisonCard = ({
  left,
  right,
  rows = [],
  verdict,
}: ComparisonCardProps) => (
  <ChatCard
    kind="comparison"
    icon={Columns2}
    title={left && right ? `${left} vs ${right}` : undefined}
  >
    {rows.length > 0 && (
      <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
        <table className="w-full text-left">
          <thead className="bg-slate-50 dark:bg-slate-900/60">
            <tr>
              <th className="px-2.5 py-1.5" />
              <th className="px-2.5 py-1.5 font-semibold">{left}</th>
              <th className="px-2.5 py-1.5 font-semibold">{right}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr
                key={index}
                className="border-t border-slate-200 align-top dark:border-slate-700"
              >
                <th className="px-2.5 py-1.5 font-medium text-slate-500 dark:text-slate-400">
                  {row.aspect}
                </th>
                <td className="px-2.5 py-1.5">{row.left}</td>
                <td className="px-2.5 py-1.5">{row.right}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
    {verdict && (
      <p className="mt-2 font-medium text-indigo-700 dark:text-indigo-300">
        {verdict}
      </p>
    )}
  </ChatCard>
);
