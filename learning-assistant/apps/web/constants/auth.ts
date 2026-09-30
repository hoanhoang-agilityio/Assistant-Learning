/** Where Clerk's sign-in and sign-up components are mounted under `app/`. */
export const SIGN_IN_PATH = "/sign-in";
export const SIGN_UP_PATH = "/sign-up";

/** Where the user lands after signing out. */
export const AFTER_SIGN_OUT_PATH = SIGN_IN_PATH;

/** What an API route answers without a signed-in user. */
export const UNAUTHORIZED_STATUS = 401;
export const UNAUTHORIZED_ERROR = "Sign in to continue.";
