"""Export the workflow graph as Mermaid markup and, optionally, a PNG.

uv run python scripts/export_graph_diagram.py
uv run python scripts/export_graph_diagram.py --format png
"""

import argparse
from pathlib import Path

from langchain_core.runnables.graph import MermaidDrawMethod

from src.graph import build_compiled_graph

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "diagrams"


def export_graph_diagram(
    output_dir: Path,
    *,
    formats: tuple[str, ...] = ("mmd",),
    draw_method: MermaidDrawMethod = MermaidDrawMethod.API,
) -> dict[str, Path]:
    """Write the compiled workflow graph's diagram in the requested formats."""
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = build_compiled_graph().get_graph()
    requested = {fmt.lower().lstrip(".") for fmt in formats}
    written: dict[str, Path] = {}

    if requested & {"mmd", "mermaid"}:
        mermaid_path = output_dir / "workflow.mmd"
        mermaid_path.write_text(graph.draw_mermaid(with_styles=True), encoding="utf-8")
        written["mmd"] = mermaid_path

    if "png" in requested:
        png_path = output_dir / "workflow.png"
        graph.draw_mermaid_png(
            output_file_path=str(png_path),
            draw_method=draw_method,
            background_color="white",
            max_retries=5,
            retry_delay=2.0,
        )
        written["png"] = png_path

    return written


def parse_args() -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Export the workflow graph as Mermaid markup and PNG."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the generated .mmd/.png files.",
    )
    parser.add_argument(
        "--format",
        action="append",
        choices=("mmd", "png"),
        dest="formats",
        help="Output format to generate. Defaults to mmd only; png needs the network.",
    )
    parser.add_argument(
        "--draw-method",
        choices=[method.value for method in MermaidDrawMethod],
        default=MermaidDrawMethod.API.value,
        help="PNG rendering backend. API uses mermaid.ink; pyppeteer renders locally.",
    )
    return parser.parse_args()


def main() -> int:
    """Export the requested diagrams and print what was written."""
    args = parse_args()
    written = export_graph_diagram(
        args.output_dir,
        formats=tuple(args.formats or ("mmd",)),
        draw_method=MermaidDrawMethod(args.draw_method),
    )
    for path in written.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
