import { CanvasAreaView } from "@/features/canvas/components/CanvasAreaView";
import { useCanvasArea } from "@/features/canvas/hooks/use-canvas-area";

/** The right side of the page: the learning stages or the Board. */
export const CanvasArea = () => {
  const { view, surfaces, boardDraft, hasUnseen, handleSelectView } =
    useCanvasArea();

  return (
    <CanvasAreaView
      view={view}
      surfaces={surfaces}
      boardDraft={boardDraft}
      hasUnseen={hasUnseen}
      onSelectView={handleSelectView}
    />
  );
};
