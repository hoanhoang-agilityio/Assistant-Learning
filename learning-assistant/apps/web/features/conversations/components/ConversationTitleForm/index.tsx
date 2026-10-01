"use client";

import { ConversationTitleFormView } from "@/features/conversations/components/ConversationTitleFormView";
import { useTitleForm } from "@/features/conversations/hooks/use-title-form";

export interface ConversationTitleFormProps {
  initialTitle: string;
  isBusy: boolean;
  onSave: (title: string) => void;
  onCancel: () => void;
}

/** Renames a conversation in place: Enter saves, Escape cancels. */
export const ConversationTitleForm = ({
  initialTitle,
  isBusy,
  onSave,
  onCancel,
}: ConversationTitleFormProps) => {
  const { title, canSave, handleChange, handleSubmit, handleKeyDown } =
    useTitleForm(initialTitle, onSave, onCancel);

  return (
    <ConversationTitleFormView
      title={title}
      canSave={canSave && !isBusy}
      onChange={handleChange}
      onSubmit={handleSubmit}
      onKeyDown={handleKeyDown}
      onCancel={onCancel}
    />
  );
};
