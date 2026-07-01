from core.graph.service import _resolve_display_node


def test_display_node_uses_next_node_while_running() -> None:
    state = {"current_node": "planning"}
    assert _resolve_display_node(state, ("research",), "running") == "research"


def test_display_node_uses_checkpoint_node_when_settled() -> None:
    state = {"current_node": "verification"}
    assert _resolve_display_node(state, ("hitl",), "waiting_hitl") == "verification"


def test_display_node_defaults_to_supervisor() -> None:
    assert _resolve_display_node({}, (), "running") == "supervisor"
