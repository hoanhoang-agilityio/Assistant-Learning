import { HOME_ROUTE } from "@repo/shared/constants/routes";
import { useRouter } from "next/navigation";
import {
  type ChangeEvent,
  useActionState,
  useLayoutEffect,
  useState,
} from "react";

import { INITIAL_API_KEY_FORM_STATE } from "@/features/api-key/constants/api-key";
import {
  useApiKeyActions,
  useApiKeyStore,
  useSealedApiKey,
} from "@/features/api-key/hooks/use-api-key-store";
import { submitApiKey } from "@/features/api-key/services/api-key-actions";
import type { ApiKeyFormState } from "@/features/api-key/types/api-key";

/**
 * The key form's value, visibility toggle and submit state. A valid key comes
 * back sealed from the server, is saved to `sessionStorage`, and the user goes
 * to the assistant. The input is controlled so a rejected key stays in the
 * field for the user to fix.
 */
export const useApiKeyForm = () => {
  const router = useRouter();
  const sealedKey = useSealedApiKey();
  const { setSealedKey, clearSealedKey } = useApiKeyActions();
  const [isHydrated, setIsHydrated] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [isKeyVisible, setIsKeyVisible] = useState(false);

  useLayoutEffect(() => {
    void Promise.resolve(useApiKeyStore.persist.rehydrate()).then(() =>
      setIsHydrated(true),
    );
  }, []);

  const submit = async (
    _previous: ApiKeyFormState,
    formData: FormData,
  ): Promise<ApiKeyFormState> => {
    const result = await submitApiKey(formData);
    if (!result.ok) {
      return { error: result.error };
    }

    setSealedKey(result.sealedKey);
    router.replace(HOME_ROUTE);
    return INITIAL_API_KEY_FORM_STATE;
  };

  const [state, formAction, isPending] = useActionState(
    submit,
    INITIAL_API_KEY_FORM_STATE,
  );

  const handleApiKeyChange = (event: ChangeEvent<HTMLInputElement>) => {
    setApiKey(event.target.value);
  };

  const handleToggleKeyVisibility = () => {
    setIsKeyVisible((isVisible) => !isVisible);
  };

  return {
    apiKey,
    error: state.error,
    hasSavedKey: isHydrated && sealedKey !== null,
    isPending,
    isKeyVisible,
    formAction,
    handleApiKeyChange,
    handleToggleKeyVisibility,
    handleForgetKey: clearSealedKey,
  };
};
