import {
  PROFILE_LANGUAGE_MAX_LENGTH,
  PROFILE_STYLE_MAX_LENGTH,
} from "@repo/shared/constants/memory";
import {
  type LearnerProfile,
  LEARNING_LEVELS,
  type LearningLevel,
} from "@repo/shared/schemas";
import { Loader2 } from "lucide-react";
import { type SubmitEvent, useId } from "react";

import { MemoryItemRow } from "@/features/memory/components/MemoryItemRow";
import { MEMORY_COPY } from "@/features/memory/constants/memory";
import type {
  MemoryItemRef,
  ProfileFormValues,
  ProfileTextField,
} from "@/features/memory/types/memory";
import { isSameMemoryItem } from "@/features/memory/utils/memory";

export interface MemoryProfileFormViewProps {
  /** The profile as kept: a field can be forgotten only when it is set. */
  saved: LearnerProfile;
  values: ProfileFormValues;
  canSave: boolean;
  isSaving: boolean;
  isBusy: boolean;
  confirming: MemoryItemRef | null;
  forgetting: MemoryItemRef | null;
  onLevelChange: (level: LearningLevel | null) => void;
  onTextChange: (field: ProfileTextField, text: string) => void;
  onSave: (event: SubmitEvent<HTMLFormElement>) => void;
  onForgetRequest: (item: MemoryItemRef) => void;
  onForgetCancel: () => void;
  onForgetConfirm: () => void;
}

const LEVEL_OPTIONS: readonly (LearningLevel | null)[] = [
  null,
  ...LEARNING_LEVELS,
];

const TEXT_FIELDS: readonly {
  field: ProfileTextField;
  label: string;
  placeholder: string;
  maxLength: number;
}[] = [
  {
    field: "style",
    label: MEMORY_COPY.style,
    placeholder: MEMORY_COPY.stylePlaceholder,
    maxLength: PROFILE_STYLE_MAX_LENGTH,
  },
  {
    field: "language",
    label: MEMORY_COPY.language,
    placeholder: MEMORY_COPY.languagePlaceholder,
    maxLength: PROFILE_LANGUAGE_MAX_LENGTH,
  },
];

const LABEL_CLASS =
  "mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300";

const segmentClass = (isSelected: boolean) =>
  `rounded border px-2.5 py-1 text-center text-[11px] whitespace-nowrap capitalize transition-all ${
    isSelected
      ? "border-indigo-600 bg-indigo-600 text-white"
      : "border-slate-200 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-700"
  }`;

/** The profile: level, explanation style and language, each forgettable. */
export const MemoryProfileFormView = ({
  saved,
  values,
  canSave,
  isSaving,
  isBusy,
  confirming,
  forgetting,
  onLevelChange,
  onTextChange,
  onSave,
  onForgetRequest,
  onForgetCancel,
  onForgetConfirm,
}: MemoryProfileFormViewProps) => {
  const formId = useId();

  const rowProps = (field: keyof LearnerProfile, label: string) => {
    const item: MemoryItemRef = { kind: "profile", id: field };
    return {
      label,
      canForget: saved[field] !== null,
      isConfirming: isSameMemoryItem(confirming, item),
      isForgetting: isSameMemoryItem(forgetting, item),
      isDisabled: isBusy,
      onForgetRequest: () => onForgetRequest(item),
      onForgetCancel,
      onForgetConfirm,
    };
  };

  return (
    <form onSubmit={onSave}>
      <ul className="divide-y divide-slate-100 dark:divide-slate-700/60">
        <MemoryItemRow {...rowProps("level", MEMORY_COPY.level)}>
          <fieldset>
            <legend className={LABEL_CLASS}>{MEMORY_COPY.level}</legend>
            <div className="flex flex-wrap gap-1">
              {LEVEL_OPTIONS.map((level) => (
                <button
                  key={level ?? MEMORY_COPY.levelUnset}
                  type="button"
                  aria-pressed={values.level === level}
                  onClick={() => onLevelChange(level)}
                  className={segmentClass(values.level === level)}
                >
                  {level ?? MEMORY_COPY.levelUnset}
                </button>
              ))}
            </div>
          </fieldset>
        </MemoryItemRow>

        {TEXT_FIELDS.map(({ field, label, placeholder, maxLength }) => (
          <MemoryItemRow key={field} {...rowProps(field, label)}>
            <label htmlFor={`${formId}-${field}`} className={LABEL_CLASS}>
              {label}
            </label>
            <input
              id={`${formId}-${field}`}
              type="text"
              value={values[field]}
              maxLength={maxLength}
              placeholder={placeholder}
              onChange={(event) => onTextChange(field, event.target.value)}
              className="w-full max-w-sm rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm outline-none focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-900"
            />
          </MemoryItemRow>
        ))}
      </ul>

      <div className="mt-3 flex justify-end">
        <button
          type="submit"
          disabled={!canSave}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {isSaving ? MEMORY_COPY.saving : MEMORY_COPY.save}
        </button>
      </div>
    </form>
  );
};
