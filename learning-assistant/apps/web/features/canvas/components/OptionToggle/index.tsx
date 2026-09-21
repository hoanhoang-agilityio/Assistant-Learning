import type { ToggleOption } from "@/features/canvas/types/canvas";

export interface OptionToggleProps<T extends string> {
  label: string;
  options: readonly ToggleOption<T>[];
  value: T;
  /** Options that cannot be picked right now. */
  disabledIds?: readonly T[];
  onChange: (value: T) => void;
}

/** A small segmented control. */
export const OptionToggle = <T extends string>({
  label,
  options,
  value,
  disabledIds = [],
  onChange,
}: OptionToggleProps<T>) => (
  <div
    role="radiogroup"
    aria-label={label}
    className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-700 dark:bg-slate-900"
  >
    {options.map(({ id, label: optionLabel, icon: Icon }) => {
      const isActive = id === value;
      return (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={isActive}
          disabled={disabledIds.includes(id)}
          onClick={() => onChange(id)}
          className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
            isActive
              ? "bg-white text-indigo-600 shadow-sm dark:bg-slate-700 dark:text-indigo-300"
              : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
          }`}
        >
          <Icon className="h-3 w-3" />
          {optionLabel}
        </button>
      );
    })}
  </div>
);
