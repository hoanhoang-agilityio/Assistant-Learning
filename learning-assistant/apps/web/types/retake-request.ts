/**
 * A request, from outside the assistant (the History page), to open a
 * conversation and retake its quiz once its state has loaded.
 */
export interface RetakeRequestStore {
  /** The conversation to retake, or `null` for none. */
  conversationId: string | null;
  actions: {
    requestRetake: (conversationId: string) => void;
    clearRetake: () => void;
  };
}
