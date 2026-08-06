"""State for the verification agent, and the shapes it reads.

The verifier must be blind to how the plan
was built. That is enforced here by omission — ``VerifyState`` has no
``messages`` field, so passing the build transcript in is a type error rather
than a convention someone violates in a month.

The plan and catalog shapes below are the contract the producing nodes
(``assemble_plan``, ``patch_plan``, ``ingest_plan``) must satisfy. They are
documented rather than validated at this boundary: a malformed plan reaching the
verifier is a bug upstream, and the checks degrade to an ``info`` issue saying
what could not be assessed rather than crashing a user's turn.

Plan::

    {
      "days": [
        {
          "name": "Push A",
          "exercises": [
            {"exercise_id": "bb_bench_press", "sets": 4, "reps": [6, 8], "rir": 2}
          ]
        }
      ]
    }

Catalog, keyed by ``exercise_id``::

    {
      "bb_bench_press": {
        "name": "Barbell bench press",
        "movement_pattern": "horizontal_push",
        "joint_actions": ["shoulder_horizontal_adduction", "elbow_extension"],
        "loaded_positions": ["shoulder_end_range_external"],
        "contribution": {"chest": 1.0, "triceps": 0.5, "front_delts": 0.5},
        "equipment": ["barbell", "bench"]
      }
    }
"""

from operator import add
from typing import Annotated, TypedDict

from app.schemas.graph import Issue, Verdict, VerifyScope


class VerifyState(TypedDict):
    """Working state of the verification subgraph.

    Deliberately has no ``messages`` field. Do not add one.
    """

    plan: dict
    profile: dict
    computed_macros: dict
    catalog: dict
    scope: list[VerifyScope]
    rubric_version: str
    issues: Annotated[list[Issue], add]
    verdict: Verdict | None
