import type { Notes } from "@repo/shared/schemas";

import { NotesStageView } from "@/features/canvas/components/stages/NotesStageView";
import { useNotesStage } from "@/features/canvas/hooks/use-notes-stage";

export interface NotesStageProps {
  notes: Notes;
}

/** The Notes stage: editable markdown synced to the agent, with Simplify. */
export const NotesStage = ({ notes }: NotesStageProps) => {
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
  } = useNotesStage(notes);

  return (
    <NotesStageView
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
