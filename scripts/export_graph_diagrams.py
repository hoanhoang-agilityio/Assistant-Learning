#!/usr/bin/env python3
"""Export the ``app/`` root graph and every subgraph as Mermaid markup and PNG.

Run::

    uv run python scripts/export_graph_diagrams.py                  # every graph
    uv run python scripts/export_graph_diagrams.py --graph root     # just the root
    uv run python scripts/export_graph_diagrams.py --format mmd     # no network

The graphs are compiled here **without a checkpointer**, the same way the
routing tests do it: drawing a topology needs no Postgres, and requiring one
would mean the diagrams can only be regenerated on a machine with the database
up. ``_add_nodes`` exists for exactly this reason — it is the one place the root
graph's shape is declared, so what is drawn is what runs.

The ``destinations=`` argument on every node is what makes the drawing
truthful: an edge missing there is an edge missing from the picture, and a
branch nothing routes to shows up as unreachable rather than hiding.

PNG rendering defaults to ``MermaidDrawMethod.API``, which posts the Mermaid
markup to the public mermaid.ink service. Pass ``--format mmd`` to stay local,
or ``--draw-method pyppeteer`` to render offline in a headless browser.
"""

import argparse
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.runnables.graph import MermaidDrawMethod  # noqa: E402
from langgraph.graph import StateGraph  # noqa: E402
from langgraph.graph.state import CompiledStateGraph  # noqa: E402

from app.core.langgraph.agents import AGENTS  # noqa: E402
from app.core.langgraph.graph import GRAPH_NAME, LangGraphAgent, _add_nodes  # noqa: E402
from app.schemas.graph import RootState  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "docs" / "diagrams"


def build_root_graph() -> CompiledStateGraph:
    """Compile the root graph for drawing only.

    No checkpointer and no connection pool: persistence has no bearing on the
    topology, and ``create_graph()`` would refuse to build outside production
    when Postgres is unreachable.

    Returns:
        The compiled root graph.
    """
    builder = StateGraph(RootState)
    _add_nodes(builder, LangGraphAgent())
    builder.set_entry_point("classify")
    return builder.compile(name=GRAPH_NAME)


# The root graph plus every agent in the registry, so adding an agent adds its
# diagram with no edit here (`app/core/langgraph/agents/__init__.py`).
GRAPH_BUILDERS: dict[str, Callable[[], CompiledStateGraph]] = {
    GRAPH_NAME: build_root_graph,
    **AGENTS,
}


def export_graph_diagram(
    name: str,
    output_dir: Path,
    *,
    formats: Iterable[str] = ("mmd", "png"),
    draw_method: MermaidDrawMethod = MermaidDrawMethod.API,
) -> dict[str, Path]:
    """Export one graph's diagram to the output directory.

    Args:
        name: A key of ``GRAPH_BUILDERS``.
        output_dir: Directory for the generated files; created if absent.
        formats: Any of ``mmd``, ``mermaid`` and ``png``.
        draw_method: PNG backend.

    Returns:
        The written paths, keyed by format.

    Raises:
        ValueError: When ``name`` is not a known graph.
    """
    if name not in GRAPH_BUILDERS:
        supported = ", ".join(sorted(GRAPH_BUILDERS))
        raise ValueError(f"Unknown graph {name!r}. Supported graphs: {supported}")

    output_dir.mkdir(parents=True, exist_ok=True)
    graph = GRAPH_BUILDERS[name]().get_graph()
    requested = {fmt.lower().lstrip(".") for fmt in formats}
    written: dict[str, Path] = {}

    if requested & {"mmd", "mermaid"}:
        mermaid_path = output_dir / f"{name}.mmd"
        mermaid_path.write_text(graph.draw_mermaid(with_styles=True), encoding="utf-8")
        written["mmd"] = mermaid_path

    if "png" in requested:
        png_path = output_dir / f"{name}.png"
        graph.draw_mermaid_png(
            output_file_path=str(png_path),
            draw_method=draw_method,
            background_color="white",
            max_retries=5,
            retry_delay=2.0,
        )
        written["png"] = png_path

    return written


def export_all_graph_diagrams(
    output_dir: Path,
    *,
    formats: Iterable[str] = ("mmd", "png"),
    draw_method: MermaidDrawMethod = MermaidDrawMethod.API,
) -> dict[str, dict[str, Path]]:
    """Export diagrams for the root graph and every registered agent.

    Args:
        output_dir: Directory for the generated files.
        formats: Any of ``mmd``, ``mermaid`` and ``png``.
        draw_method: PNG backend.

    Returns:
        The written paths, keyed by graph name and then by format.
    """
    return {
        name: export_graph_diagram(
            name,
            output_dir,
            formats=formats,
            draw_method=draw_method,
        )
        for name in GRAPH_BUILDERS
    }


def parse_args() -> argparse.Namespace:
    """Parse the command line.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Export the app/ LangGraph diagrams as Mermaid markup and PNG images.",
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
    """Export the requested diagrams and print what was written.

    Returns:
        Process exit code.
    """
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
            print(f"{args.graph}: {path}")
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
