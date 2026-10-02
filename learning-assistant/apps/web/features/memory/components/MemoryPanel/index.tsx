"use client";

import { MemoryPanelView } from "@/features/memory/components/MemoryPanelView";
import { useMemoryPanel } from "@/features/memory/hooks/use-memory-panel";

/** The Memory panel, reached from Settings: view, edit and forget what is kept. */
export const MemoryPanel = () => {
  const {
    memory,
    loadError,
    values,
    canSave,
    isSaving,
    isBusy,
    confirming,
    forgetting,
    notice,
    actionError,
    handleRetry,
    handleLevelChange,
    handleTextChange,
    handleSave,
    handleForgetRequest,
    handleForgetCancel,
    handleForgetConfirm,
  } = useMemoryPanel();

  return (
    <MemoryPanelView
      memory={memory}
      loadError={loadError}
      values={values}
      canSave={canSave}
      isSaving={isSaving}
      isBusy={isBusy}
      confirming={confirming}
      forgetting={forgetting}
      notice={notice}
      actionError={actionError}
      onRetry={handleRetry}
      onLevelChange={handleLevelChange}
      onTextChange={handleTextChange}
      onSave={handleSave}
      onForgetRequest={handleForgetRequest}
      onForgetCancel={handleForgetCancel}
      onForgetConfirm={handleForgetConfirm}
    />
  );
};
