#!/usr/bin/env python3
"""Export supervisor and subgraph diagrams as Mermaid markup and PNG images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from langchain_core.runnables.graph import MermaidDrawMethod  # noqa: E402

from core.graph.diagrams import (  # noqa: E402
    GRAPH_BUILDERS,
    export_all_graph_diagrams,
    export_graph_diagram,
)

DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "src" / "docs" / "diagrams"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export LangGraph diagrams as Mermaid markup and PNG images.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated .mmd and .png files.",
    )
    parser.add_argument(
        "--graph",
        choices=sorted(GRAPH_BUILDERS),
        help="Export a single graph instead of all graphs.",
    )
    parser.add_argument(
        "--format",
        action="append",
        choices=("mmd", "png"),
        dest="formats",
        help="Output format to generate. Defaults to both mmd and png.",
    )
    parser.add_argument(
        "--draw-method",
        choices=[method.value for method in MermaidDrawMethod],
        default=MermaidDrawMethod.API.value,
        help="PNG rendering backend. API uses mermaid.ink; pyppeteer renders locally.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    formats = tuple(args.formats or ("mmd", "png"))
    draw_method = MermaidDrawMethod(args.draw_method)

    if args.graph:
        written = export_graph_diagram(
            args.graph,
            args.output_dir,
            formats=formats,
            draw_method=draw_method,
        )
        for path in written.values():
            print(path)
        return 0

    all_written = export_all_graph_diagrams(
        args.output_dir,
        formats=formats,
        draw_method=draw_method,
    )
    for graph_name, paths in all_written.items():
        for path in paths.values():
            print(f"{graph_name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
