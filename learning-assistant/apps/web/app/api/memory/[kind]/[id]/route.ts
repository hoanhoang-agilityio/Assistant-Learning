import { deleteMemoryItemHandler } from "@/features/memory/services/memory-api";
import { withSignedInUser } from "@/services/auth";

export const DELETE = withSignedInUser(deleteMemoryItemHandler);
