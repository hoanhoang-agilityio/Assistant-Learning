import { clerkMiddleware } from "@clerk/nextjs/server";

/**
 * Makes the Clerk session readable with `auth()` on every page and API route.
 * It is not the auth check: pages call `requireSignedInUser` and route
 * handlers go through `withSignedInUser` (`services/auth.ts`).
 */
export default clerkMiddleware();

export const config = {
  matcher: [
    // Every route except Next internals and static files…
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // …and always the API routes.
    "/(api|trpc)(.*)",
  ],
};
