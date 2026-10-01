import {
  getSettingsHandler,
  saveSettingsHandler,
} from "@/features/settings/services/settings-api";
import { withSignedInUser } from "@/services/auth";

export const GET = withSignedInUser(getSettingsHandler);
export const PUT = withSignedInUser(saveSettingsHandler);
