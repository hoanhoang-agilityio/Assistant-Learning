"""Capability registry and result-recording."""

from core.orchestration.routing.dispatcher import apply_capability_result
from core.orchestration.routing.registry import (
    CAPABILITY_REGISTRY,
    CapabilityDefinition,
    capability_node_map,
    get_capability,
    validate_handoff_target,
)

__all__ = [
    "CAPABILITY_REGISTRY",
    "CapabilityDefinition",
    "apply_capability_result",
    "capability_node_map",
    "get_capability",
    "validate_handoff_target",
]
