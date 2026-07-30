"""Central registry of domain capabilities — identity and graph binding only."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from core.orchestration.agents.execution_context import CapabilityName

CAPABILITY_REGISTRY: dict[CapabilityName, CapabilityDefinition] = {}


class CapabilityDefinition(BaseModel):
    """Declarative capability metadata — no sequencing or business rules."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: CapabilityName
    node_name: str
    description: str
    can_return: bool


def _register(defn: CapabilityDefinition) -> CapabilityDefinition:
    CAPABILITY_REGISTRY[defn.name] = defn
    return defn


_register(
    CapabilityDefinition(
        name="user",
        node_name="user",
        description="Profile collection and validation",
        can_return=True,
    )
)
_register(
    CapabilityDefinition(
        name="planning",
        node_name="planning",
        description="Goal specification and training requirements",
        can_return=True,
    )
)
_register(
    CapabilityDefinition(
        name="research",
        node_name="research",
        description="Evidence retrieval and synthesis",
        can_return=True,
    )
)
_register(
    CapabilityDefinition(
        name="fitness",
        node_name="fitness",
        description="Workout generation, macros, and plan editing",
        can_return=True,
    )
)
_register(
    CapabilityDefinition(
        name="verification",
        node_name="verification",
        description="Independent validation of plans and artifacts",
        can_return=True,
    )
)
_register(
    CapabilityDefinition(
        name="hitl",
        node_name="hitl",
        description="Human approval for persistent artifacts",
        can_return=True,
    )
)
_register(
    CapabilityDefinition(
        name="persist",
        node_name="persist",
        description="Persist approved artifacts",
        can_return=False,
    )
)


def get_capability(name: CapabilityName) -> CapabilityDefinition:
    return CAPABILITY_REGISTRY[name]


def validate_handoff_target(name: CapabilityName) -> None:
    if name not in CAPABILITY_REGISTRY:
        raise ValueError(f"Unknown capability: {name}")


def capability_node_map() -> dict[str, str]:
    """Graph conditional-edge target map keyed by node name."""
    return {defn.node_name: defn.node_name for defn in CAPABILITY_REGISTRY.values()}
