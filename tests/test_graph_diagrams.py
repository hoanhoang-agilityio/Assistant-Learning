from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.orchestration.graph.builder import build_graph
from core.orchestration.graph.diagrams import (
    GRAPH_BUILDERS,
    draw_graph_mermaid_png,
    export_all_graph_diagrams,
    export_graph_diagram,
    get_graph_mermaid,
)

_FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _mock_mermaid_ink_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.content = _FAKE_PNG_BYTES
    return response


def test_graph_builders_include_supervisor() -> None:
    # Capabilities are plain functions in the intent-driven architecture, not
    # separate compiled StateGraphs, so "supervisor" (the whole top-level
    # graph) is the only diagram-able graph left.
    assert set(GRAPH_BUILDERS) == {"supervisor"}


def test_get_graph_mermaid_contains_nodes() -> None:
    mermaid = get_graph_mermaid(build_graph())
    assert "graph TD" in mermaid
    assert "supervisor" in mermaid
    assert "planning" in mermaid
    assert "verification" in mermaid


def test_export_graph_diagram_writes_mermaid(tmp_path: Path) -> None:
    written = export_graph_diagram("supervisor", tmp_path, formats=("mmd",))
    mermaid_path = written["mmd"]
    assert mermaid_path.exists()
    assert "supervisor" in mermaid_path.read_text(encoding="utf-8")


def test_export_graph_diagram_rejects_unknown_graph(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown graph"):
        export_graph_diagram("missing", tmp_path)


def test_export_all_graph_diagrams_writes_mermaid_for_every_graph(tmp_path: Path) -> None:
    written = export_all_graph_diagrams(tmp_path, formats=("mmd",))
    assert set(written) == set(GRAPH_BUILDERS)
    for paths in written.values():
        assert paths["mmd"].exists()


@patch("langchain_core.runnables.graph_mermaid.requests.get")
def test_draw_graph_mermaid_png_returns_png_bytes(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_mermaid_ink_response()
    png_bytes = draw_graph_mermaid_png(build_graph())
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    mock_get.assert_called_once()


@patch("langchain_core.runnables.graph_mermaid.requests.get")
def test_export_graph_diagram_writes_png(mock_get: MagicMock, tmp_path: Path) -> None:
    mock_get.return_value = _mock_mermaid_ink_response()
    written = export_graph_diagram("supervisor", tmp_path, formats=("png",))
    png_path = written["png"]
    assert png_path.exists()
    assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
