import { CodeBlockView } from "@/features/canvas/components/a2ui/CodeBlockView";
import { useCopyToClipboard } from "@/features/canvas/hooks/use-copy-to-clipboard";
import { useHighlightedCode } from "@/features/canvas/hooks/use-highlighted-code";
import type { BoardComponentProps } from "@/features/canvas/types/board";
import { readList, readText } from "@/features/canvas/utils/a2ui-props";
import { normalizeCode, toCodeLines } from "@/features/canvas/utils/code-block";

/**
 * A Board code snippet with line numbers, highlighted lines and Copy. The
 * syntax colours arrive a moment later from shiki; until then, and for a
 * language shiki does not know, the code shows plain.
 */
export const CodeBlock = ({ props }: BoardComponentProps<"CodeBlock">) => {
  const code = readText(props.code);
  const language = readText(props.language);
  const { status, handleCopy } = useCopyToClipboard(code);
  const tokenLines = useHighlightedCode(normalizeCode(code), language);

  return (
    <CodeBlockView
      language={language}
      filename={readText(props.filename)}
      lines={toCodeLines(
        code,
        readList<number>(props.highlightLines),
        tokenLines,
      )}
      copyStatus={status}
      onCopy={() => void handleCopy()}
    />
  );
};
