"""Frame types for the streamed chat response."""

from enum import StrEnum


class StreamEventType(StrEnum):
    """What one server-sent event frame carries.

    Attributes:
        STEP: A node the run has reached, named for the user rather than for the graph.
        MESSAGE: One complete reply the turn produced.
        FORM: Fields the run is suspended waiting for, for the client to render.
        DONE: The run has settled; no further frames follow.
    """

    STEP = "step"
    MESSAGE = "message"
    FORM = "form"
    DONE = "done"


__all__ = ["StreamEventType"]
