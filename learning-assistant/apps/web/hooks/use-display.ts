import { useLayout } from "@/hooks/use-layout-store";
import { useWindowWidth } from "@/hooks/use-window-width";
import { resolveDisplay } from "@/utils/layout";

/** The layout on screen: frame, width, compact or not, and the chat mode. */
export const useDisplay = () => resolveDisplay(useLayout(), useWindowWidth());
