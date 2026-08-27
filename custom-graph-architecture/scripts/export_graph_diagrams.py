#!/usr/bin/env python3
"""Export the coaching flow and the QA flow as Mermaid markup, derived from the graph itself.

Run::

    uv run python scripts/export_graph_diagrams.py                    # markup only
    uv run python scripts/export_graph_diagrams.py --format both      # markup and PNG

All three pictures are views of the one workflow graph, not separate graphs: the whole thing,
and then the set of nodes reachable from ``START`` once the other intent's edges are cut.
Deriving them from ``build_graph()`` rather than drawing them by hand is the point — a diagram
redrawn from the wiring cannot drift from it, and the wiring is what the tests already pin.

PNG rendering goes through ``langchain_core``'s own ``draw_mermaid_png`` — the function behind
``CompiledStateGraph.get_graph().draw_mermaid_png()``, which takes markup rather than a graph,
so the pruned views render through it too. Its default draw method posts the markup to the
public **mermaid.ink** service; ``--draw-method pyppeteer`` renders locally instead, if a
headless Chromium is installed. That is why PNG is opt-in and only the ``.mmd`` is written by
default.
"""

import argparse
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.runnables.graph import MermaidDrawMethod  # noqa: E402
from langchain_core.runnables.graph_mermaid import draw_mermaid_png  # noqa: E402
from langgraph.graph import END, START  # noqa: E402

from src.core.langgraph.graph import build_graph  # noqa: E402
from src.enums import Intent, Node  # noqa: E402

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
OUTPUT_DIR = DOCS_DIR / "diagrams"
PLAN = DOCS_DIR / "implementation-plan.md"

# The whole graph, then one view per intent. Cutting every edge the other intent labels leaves
# that branch's view: the fork at ``persist_profile``, and the duplicate label into the shared
# context chain. ``None`` cuts nothing, which is the whole workflow.
VIEWS: dict[str, str | None] = {
    "workflow": None,
    "coaching-flow": Intent.QA,
    "qa-flow": Intent.COACHING,
}

# What each node is, which is what the reader wants the shape to tell them.
LLM_NODES = {Node.PARSE_TURN, Node.COACH_AGENT, Node.QA_AGENT}
INTERRUPT_NODES = {Node.WAIT_FOR_USER, Node.HITL_REVIEW}
GATE_NODES = {
    Node.GUARD_INPUT,
    Node.DETERMINISTIC_VERIFICATION,
    Node.VERIFY_FAITHFULNESS,
}
STOP_NODES = {
    Node.BLOCKED,
    Node.OFF_TOPIC,
    Node.PROFILE_COLLECTION_EXHAUSTED,
    Node.NOTIFY_FAIL,
    Node.HITL_REJECTED_NO_FEEDBACK,
    Node.HITL_EXHAUSTED,
    Node.QA_FALLBACK,
}

CLASS_DEFS = """    classDef llm fill:#4a3b1f,stroke:#e0a44a,stroke-width:2px,color:#fff
    classDef gate fill:#3d1f1f,stroke:#e05b5b,stroke-width:2px,color:#fff
    classDef pause fill:#2d3b55,stroke:#5b8def,stroke-width:2px,color:#fff
    classDef stop fill:#3a3a3a,stroke:#8a8a8a,stroke-width:1px,color:#fff
    classDef finalize fill:#3d2d55,stroke:#a98fe8,stroke-width:2px,color:#fff"""


def graph_edges() -> list[tuple[str, str | None, str]]:
    """Every edge as ``(from, label, to)``, read off the builder rather than the drawing.

    The drawn graph collapses two labels leading to the same node into one edge, which would
    silently drop ``parse_turn --qa--> load_user_context`` from the QA picture.
    """
    builder = build_graph()
    edges: list[tuple[str, str | None, str]] = [
        (source, None, target) for source, target in builder.edges
    ]
    for source, branches in builder.branches.items():
        for branch in branches.values():
            for label, target in (branch.ends or {}).items():
                edges.append((source, label, target))
    return edges


def branch_view(
    edges: list[tuple[str, str | None, str]], cut_label: str | None
) -> list[tuple[str, str | None, str]]:
    """The edges reachable from ``START``, in walk order, once the other intent is cut off.

    Walk order rather than the builder's order: a diagram is read top to bottom, and the
    order edges happen to sit in a set is not an order anyone can follow.
    """
    kept = [edge for edge in edges if cut_label is None or edge[1] != cut_label]
    seen = {START}
    queue = deque([START])
    view: list[tuple[str, str | None, str]] = []
    while queue:
        node = queue.popleft()
        for edge in kept:
            if edge[0] != node:
                continue
            view.append(edge)
            if edge[2] not in seen:
                seen.add(edge[2])
                queue.append(edge[2])
    return view


def node_id(name: str) -> str:
    """The identifier used in the markup; ``START`` and ``END`` get readable ones."""
    return {START: "start", END: "finish"}.get(name, str(name))


def class_lines(nodes: set[str]) -> list[str]:
    """One ``class`` line per group present in this view."""
    groups = [
        ("llm", LLM_NODES),
        ("gate", GATE_NODES),
        ("pause", INTERRUPT_NODES),
        ("stop", STOP_NODES),
        ("finalize", {Node.FINALIZE_TURN}),
    ]
    lines = []
    for class_name, members in groups:
        present = sorted(str(node) for node in members & nodes)
        if present:
            lines.append(f"    class {','.join(present)} {class_name}")
    return lines


def to_mermaid(edges: list[tuple[str, str | None, str]], title: str) -> str:
    """Render one view as a Mermaid flowchart."""
    nodes = {edge[0] for edge in edges} | {edge[2] for edge in edges}
    lines = [
        f"%% {title} — generated by scripts/export_graph_diagrams.py, do not edit by hand",
        "flowchart TD",
        "    start([START])",
        "    finish([END])",
    ]

    for source, label, target in edges:
        arrow = f"-->|{label}|" if label else "-->"
        lines.append(f"    {node_id(source)} {arrow} {node_id(target)}")

    lines.append(CLASS_DEFS)
    lines.extend(class_lines(nodes))
    return "\n".join(lines) + "\n"


def splice_into_plan(view_name: str, markup: str) -> None:
    """Replace one fenced block in the implementation plan, so the doc renders the same picture."""
    start = f"<!-- {view_name}:start -->"
    end = f"<!-- {view_name}:end -->"
    text = PLAN.read_text()
    if start not in text or end not in text:
        return
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    block = f"{start}\n\n```mermaid\n{markup.strip()}\n```\n\n{end}"
    PLAN.write_text(head + block + tail)


def render_png(markup: str, path: Path, draw_method: MermaidDrawMethod) -> None:
    """Render one view with ``langchain_core``'s renderer, the one the graph object uses."""
    draw_mermaid_png(
        mermaid_syntax=markup,
        output_file_path=str(path),
        draw_method=draw_method,
        background_color="white",
    )


def parse_args() -> argparse.Namespace:
    """Read the output format and the renderer to use for PNG."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("mmd", "png", "both"),
        default="mmd",
        help="mmd writes markup only (default); png and both render through mermaid.ink",
    )
    parser.add_argument(
        "--draw-method",
        choices=[method.value for method in MermaidDrawMethod],
        default=MermaidDrawMethod.API.value,
        help="api posts to mermaid.ink; pyppeteer renders locally",
    )
    return parser.parse_args()


def main() -> None:
    """Write one ``.mmd`` per view, refresh the plan's copy of each, and optionally render."""
    args = parse_args()
    edges = graph_edges()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for view_name, cut_label in VIEWS.items():
        view = branch_view(edges, cut_label)
        markup = to_mermaid(view, view_name.replace("-", " "))

        if args.format in ("mmd", "both"):
            path = OUTPUT_DIR / f"{view_name}.mmd"
            path.write_text(markup)
            splice_into_plan(view_name, markup)
            print(f"wrote {path.relative_to(DOCS_DIR.parent)} ({len(view)} edges)")

        if args.format in ("png", "both"):
            path = OUTPUT_DIR / f"{view_name}.png"
            render_png(markup, path, MermaidDrawMethod(args.draw_method))
            print(f"wrote {path.relative_to(DOCS_DIR.parent)}")


if __name__ == "__main__":
    main()
