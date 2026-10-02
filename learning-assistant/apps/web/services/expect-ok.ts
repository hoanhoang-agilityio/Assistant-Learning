/** The response, or an error with the server's message. */
export const expectOk = async (response: Response): Promise<Response> => {
  if (response.ok) {
    return response;
  }

  let message = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as { error?: unknown };
    if (typeof body.error === "string") {
      message = body.error;
    }
  } catch {
    // Keep the status message.
  }
  throw new Error(message);
};
