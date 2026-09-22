import type { Reflection } from "@repo/shared/schemas";

import { ReflectionFormView } from "@/features/canvas/components/ReflectionFormView";
import { useReflectionForm } from "@/features/canvas/hooks/use-reflection-form";

export interface ReflectionFormProps {
  reflection: Reflection | null;
}

/** The fixed reflection form under the Feedback surface. */
export const ReflectionForm = ({ reflection }: ReflectionFormProps) => {
  const {
    rating,
    text,
    isSaved,
    canSubmit,
    isLocked,
    handleRatingChange,
    handleTextChange,
    handleSubmit,
    handleEdit,
  } = useReflectionForm(reflection);

  return (
    <ReflectionFormView
      rating={rating}
      text={text}
      isSaved={isSaved}
      canSubmit={canSubmit}
      isLocked={isLocked}
      onRatingChange={handleRatingChange}
      onTextChange={handleTextChange}
      onSubmit={handleSubmit}
      onEdit={handleEdit}
    />
  );
};
