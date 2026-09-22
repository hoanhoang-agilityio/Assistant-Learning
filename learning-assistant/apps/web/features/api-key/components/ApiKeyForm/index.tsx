"use client";

import { ApiKeyFormView } from "@/features/api-key/components/ApiKeyFormView";
import { useApiKeyForm } from "@/features/api-key/hooks/use-api-key-form";

/** The OpenAI API key form, wired to the server check and the key store. */
export const ApiKeyForm = () => {
  const {
    apiKey,
    error,
    hasSavedKey,
    isPending,
    isKeyVisible,
    formAction,
    handleApiKeyChange,
    handleToggleKeyVisibility,
    handleForgetKey,
  } = useApiKeyForm();

  return (
    <ApiKeyFormView
      apiKey={apiKey}
      error={error}
      hasSavedKey={hasSavedKey}
      isPending={isPending}
      isKeyVisible={isKeyVisible}
      formAction={formAction}
      onApiKeyChange={handleApiKeyChange}
      onToggleKeyVisibility={handleToggleKeyVisibility}
      onForgetKey={handleForgetKey}
    />
  );
};
