import type { Material } from "@repo/shared/schemas";

import { MaterialStageView } from "@/features/canvas/components/stages/MaterialStageView";
import { useMaterialStage } from "@/features/canvas/hooks/use-material-stage";

export interface MaterialStageProps {
  material: Material;
}

/** The Learning Material stage: editable markdown synced to the agent, with Simplify. */
export const MaterialStage = ({ material }: MaterialStageProps) => {
  const {
    text,
    characterCount,
    mode,
    view,
    hasSimplified,
    hasSelection,
    isSaving,
    isLocked,
    handleChange,
    handleSelect,
    handleModeChange,
    handleViewChange,
    handleSimplifyAll,
    handleSimplifySelection,
  } = useMaterialStage(material);

  return (
    <MaterialStageView
      text={text}
      characterCount={characterCount}
      mode={mode}
      view={view}
      hasSimplified={hasSimplified}
      hasSelection={hasSelection}
      isSaving={isSaving}
      isLocked={isLocked}
      onChange={handleChange}
      onSelect={handleSelect}
      onModeChange={handleModeChange}
      onViewChange={handleViewChange}
      onSimplifyAll={handleSimplifyAll}
      onSimplifySelection={handleSimplifySelection}
    />
  );
};
