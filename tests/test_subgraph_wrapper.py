from core.capabilities.wrapper import append_pipeline_steps, merge_subgraph_updates


def test_append_pipeline_steps_deduplicates() -> None:
    state = {"steps": ["planning:extract_profile"]}
    merged = append_pipeline_steps(state, "planning", ["extract_profile", "validate_profile"])
    assert merged == ["planning:extract_profile", "planning:validate_profile"]


def test_merge_subgraph_updates_appends_steps() -> None:
    state = {"steps": ["supervisor:route"]}
    result = merge_subgraph_updates(
        state,
        {"current_node": "research"},
        subgraph="research",
        steps=["todos_gate", "research_agent"],
    )
    assert result["current_node"] == "research"
    assert result["steps"] == [
        "supervisor:route",
        "research:todos_gate",
        "research:research_agent",
    ]
