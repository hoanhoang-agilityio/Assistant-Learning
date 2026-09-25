export interface StreamingNoteProps {
  label: string;
}

/** Says the view beside it is still being written. */
export const StreamingNote = ({ label }: StreamingNoteProps) => (
  <p
    role="status"
    aria-live="polite"
    className="flex items-center gap-2 text-xs font-semibold tracking-wider text-indigo-500 uppercase"
  >
    <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
    {label}
  </p>
);
