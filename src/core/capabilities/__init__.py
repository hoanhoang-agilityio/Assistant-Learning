"""Capability registry and result-recording."""

from core.capabilities.dispatcher import apply_capability_result, make_capability_request
from core.capabilities.registry import (
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
    "make_capability_request",
    "validate_handoff_target",
]
