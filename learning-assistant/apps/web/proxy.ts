import { clerkMiddleware } from "@clerk/nextjs/server";

import { SIGN_IN_PATH, SIGN_UP_PATH } from "@/constants/auth";

/**
 * Makes the Clerk session readable with `auth()` on every page and API route.
 * It is not the auth check: pages call `requireSignedInUser` and route
 * handlers go through `withSignedInUser` (`services/auth.ts`). The sign-in
 * and sign-up paths are set here because the server-side `redirectToSignIn`
 * reads them from here, not from `ClerkProvider`; without them it sends the
 * user to Clerk's hosted page instead of ours.
 */
export default clerkMiddleware({
  signInUrl: SIGN_IN_PATH,
  signUpUrl: SIGN_UP_PATH,
});

export const config = {
  matcher: [
    // Every route except Next internals and static files…
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // …and always the API routes.
    "/(api|trpc)(.*)",
  ],
};
