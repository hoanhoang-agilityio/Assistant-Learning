#!/usr/bin/env python3
"""Export the supervisor and every agent as Mermaid markup and PNG.

Run::

    uv run python scripts/export_graph_diagrams.py                        # every graph
    uv run python scripts/export_graph_diagrams.py --graph supervisor     # just one
    uv run python scripts/export_graph_diagrams.py --format png           # also render

The graphs are compiled here **without a checkpointer**: drawing a topology
needs no Postgres, and requiring one would mean the diagrams can only be
regenerated on a machine with the database up.

What these pictures show is now narrower than it used to be, and the narrowing
is the point. An agent's internal graph is fixed — a ``model`` node, a ``tools``
node, and one node per middleware hook — so the diagram tells you which hooks are
wired and nothing about what the model will choose to call. The order of steps is
no longer a property of the topology; it is a decision made at runtime. Only
``verification`` still has a shape worth reading off the picture, because it is
the one graph left with arbitrary nodes and edges.

Only the Mermaid markup is written by default, and only it is committed. PNG is
opt-in because rendering posts the markup to the public mermaid.ink service,
which rejects some of the identifiers ``create_agent`` generates — a middleware
named ``ToolCallLimitMiddleware[commit_draft]`` escapes into brackets the API
will not parse. A missing PNG for one agent and not another is worse than none,
so the ``.mmd`` files are the artifact; pass ``--draw-method pyppeteer`` to
render locally when a picture is actually wanted.
"""

import argparse
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.runnables.graph import MermaidDrawMethod  # noqa: E402
from langgraph.graph.state import CompiledStateGraph  # noqa: E402

from app.core.langgraph.agents import AGENTS  # noqa: E402
from app.core.langgraph.supervisor import AGENT_NAME, build_supervisor  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "docs" / "diagrams"


# The supervisor plus every agent in the registry, so adding an agent adds its
# diagram with no edit here (`app/core/langgraph/agents/__init__.py`).
GRAPH_BUILDERS: dict[str, Callable[[], CompiledStateGraph]] = {
    AGENT_NAME: build_supervisor,
    **AGENTS,
}


def export_graph_diagram(
    name: str,
    output_dir: Path,
    *,
    formats: Iterable[str] = ("mmd",),
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
    formats: Iterable[str] = ("mmd",),
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
    """Export the requested diagrams and print what was written.

    Returns:
        Process exit code.
    """
    args = parse_args()
    formats = tuple(args.formats or ("mmd",))
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
