"""Export LangGraph diagrams as Mermaid markup and PNG images."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from langchain_core.runnables.graph import MermaidDrawMethod
from langgraph.graph.state import CompiledStateGraph

from core.orchestration.graph.builder import build_graph

GraphBuilder = Callable[[], CompiledStateGraph]

GRAPH_BUILDERS: dict[str, GraphBuilder] = {
    "supervisor": build_graph,
}


def get_graph_mermaid(
    compiled_graph: CompiledStateGraph,
    *,
    with_styles: bool = True,
) -> str:
    """Return Mermaid markup for a compiled LangGraph."""
    return compiled_graph.get_graph().draw_mermaid(with_styles=with_styles)


def draw_graph_mermaid_png(
    compiled_graph: CompiledStateGraph,
    *,
    output_file_path: Path | str | None = None,
    draw_method: MermaidDrawMethod = MermaidDrawMethod.API,
    background_color: str = "white",
    max_retries: int = 5,
    retry_delay: float = 2.0,
) -> bytes:
    """Render a compiled LangGraph as a PNG image via Mermaid."""
    return compiled_graph.get_graph().draw_mermaid_png(
        output_file_path=str(output_file_path) if output_file_path is not None else None,
        draw_method=draw_method,
        background_color=background_color,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )


def export_graph_diagram(
    name: str,
    output_dir: Path,
    *,
    formats: Iterable[str] = ("mmd", "png"),
    draw_method: MermaidDrawMethod = MermaidDrawMethod.API,
) -> dict[str, Path]:
    """Export one graph diagram to the output directory."""
    if name not in GRAPH_BUILDERS:
        supported = ", ".join(sorted(GRAPH_BUILDERS))
        raise ValueError(f"Unknown graph {name!r}. Supported graphs: {supported}")

    output_dir.mkdir(parents=True, exist_ok=True)
    compiled_graph = GRAPH_BUILDERS[name]()
    requested_formats = {fmt.lower().lstrip(".") for fmt in formats}
    written: dict[str, Path] = {}

    if "mmd" in requested_formats or "mermaid" in requested_formats:
        mermaid_path = output_dir / f"{name}.mmd"
        mermaid_path.write_text(get_graph_mermaid(compiled_graph), encoding="utf-8")
        written["mmd"] = mermaid_path

    if "png" in requested_formats:
        png_path = output_dir / f"{name}.png"
        draw_graph_mermaid_png(
            compiled_graph,
            output_file_path=png_path,
            draw_method=draw_method,
        )
        written["png"] = png_path

    return written


def export_all_graph_diagrams(
    output_dir: Path,
    *,
    formats: Iterable[str] = ("mmd", "png"),
    draw_method: MermaidDrawMethod = MermaidDrawMethod.API,
) -> dict[str, dict[str, Path]]:
    """Export Mermaid and PNG diagrams for every registered graph."""
    return {
        name: export_graph_diagram(
            name,
            output_dir,
            formats=formats,
            draw_method=draw_method,
        )
        for name in GRAPH_BUILDERS
    }
