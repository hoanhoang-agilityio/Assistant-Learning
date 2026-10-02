import { EMPTY_PROFILE } from "@repo/shared/constants/memory";
import type { LearningLevel, StudentMemory } from "@repo/shared/schemas";
import { type SubmitEvent, useEffect, useState } from "react";

import { MEMORY_COPY } from "@/features/memory/constants/memory";
import {
  fetchMemory,
  forgetMemoryItem,
  updateProfile,
} from "@/features/memory/services/memory-client";
import type {
  MemoryItemRef,
  ProfileFormValues,
  ProfileTextField,
} from "@/features/memory/types/memory";
import {
  clearProfileFormField,
  createProfileUpdate,
  removeMemoryItem,
  toProfileFormValues,
} from "@/features/memory/utils/memory";

const toErrorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

/**
 * The Memory panel's logic: loads what is kept about the student, edits the
 * profile (only changed fields are sent) and forgets one profile field,
 * concept or topic after a confirmation step. A failed load blocks the
 * panel with a retry; a failed save or forget is a notice above it.
 */
export const useMemoryPanel = () => {
  const [memory, setMemory] = useState<StudentMemory | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [values, setValues] = useState<ProfileFormValues>(() =>
    toProfileFormValues(EMPTY_PROFILE),
  );
  const [isSaving, setIsSaving] = useState(false);
  const [confirming, setConfirming] = useState<MemoryItemRef | null>(null);
  const [forgetting, setForgetting] = useState<MemoryItemRef | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;
    fetchMemory()
      .then((loaded) => {
        if (!isCancelled) {
          setMemory(loaded);
          setValues(toProfileFormValues(loaded.profile));
        }
      })
      .catch((error: unknown) => {
        console.error("[memory] Loading failed", error);
        if (!isCancelled) {
          setLoadError(MEMORY_COPY.loadFailed);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [loadAttempt]);

  const update = memory ? createProfileUpdate(memory.profile, values) : null;
  const isBusy = isSaving || forgetting !== null;

  const startAction = () => {
    setNotice(null);
    setActionError(null);
  };

  const handleRetry = () => {
    setLoadError(null);
    setLoadAttempt((count) => count + 1);
  };

  const handleLevelChange = (level: LearningLevel | null) =>
    setValues((current) => ({ ...current, level }));

  const handleTextChange = (field: ProfileTextField, text: string) =>
    setValues((current) => ({ ...current, [field]: text }));

  const handleSave = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!memory || !update || isBusy) {
      return;
    }

    startAction();
    setIsSaving(true);
    try {
      const profile = await updateProfile(update);
      setMemory({ ...memory, profile });
      setValues(toProfileFormValues(profile));
      setNotice(MEMORY_COPY.saved);
    } catch (error) {
      setActionError(toErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const handleForgetRequest = (item: MemoryItemRef) => {
    startAction();
    setConfirming(item);
  };

  const handleForgetCancel = () => setConfirming(null);

  const handleForgetConfirm = async () => {
    if (!memory || !confirming || isBusy) {
      return;
    }

    const item = confirming;
    startAction();
    setForgetting(item);
    try {
      await forgetMemoryItem(item);
      setMemory(removeMemoryItem(memory, item));
      if (item.kind === "profile") {
        setValues((current) => clearProfileFormField(current, item.id));
      }
      setConfirming(null);
      setNotice(MEMORY_COPY.forgotten);
    } catch (error) {
      setActionError(toErrorMessage(error));
    } finally {
      setForgetting(null);
    }
  };

  return {
    memory,
    loadError,
    values,
    canSave: update !== null && !isBusy,
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
  };
};
