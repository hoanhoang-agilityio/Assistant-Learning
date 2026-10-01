import {
  getMemoryHandler,
  updateProfileHandler,
} from "@/features/memory/services/memory-api";
import { withSignedInUser } from "@/services/auth";

export const GET = withSignedInUser(getMemoryHandler);
export const PATCH = withSignedInUser(updateProfileHandler);
