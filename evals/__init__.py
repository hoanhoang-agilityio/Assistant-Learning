"""Offline evaluation of finished Langfuse traces.

Evals never gate a request. They read traces of turns that already happened,
score them with judge evaluators, and write the scores back to Langfuse. This
package imports *from* ``app`` — settings and the logger — and ``app`` never
imports from it, so an eval cannot change a turn's outcome even by accident.

The run loop itself is the Langfuse SDK's ``run_batched_evaluation``: it owns
pagination, concurrency, retries, per-item error isolation, the resume token and
the final flush of scores. What lives here is only what is specific to this
project — the mappers that read the supervisor's output, and the evaluators.

A regression an eval catches is a quality regression. Anything that must fail
hard belongs in the rubric checks (``app/core/langgraph/verification/``) or in
``tests/``.
"""
