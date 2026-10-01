import { TITLE_MAX_LENGTH } from "@repo/shared/constants/conversations";
import { type KeyboardEvent, type SubmitEvent, useState } from "react";

/** The rename field's text, and when it may be saved. */
export const useTitleForm = (
  initialTitle: string,
  onSave: (title: string) => void,
  onCancel: () => void,
) => {
  const [title, setTitle] = useState(initialTitle);
  const trimmed = title.trim();
  const canSave = trimmed.length > 0 && trimmed.length <= TITLE_MAX_LENGTH;

  const handleSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (canSave) {
      onSave(trimmed);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      onCancel();
    }
  };

  return {
    title,
    canSave,
    handleChange: setTitle,
    handleSubmit,
    handleKeyDown,
  };
};
