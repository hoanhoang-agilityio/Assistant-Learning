"""Routing: the one LLM call that still influences control flow.

It influences it by returning a validated ``IntentDecision`` — not by choosing
what to call. Under the old root graph that decision picked a branch; under the
supervisor it does two narrower things, both inside the topic gate: it ends an
off-topic turn before the agent loop starts, and it becomes ``intent_hint``,
which is advisory (``docs/supervisor-architecture.md`` §4.3).

Routing is still never exposed as a tool. Given the option to skip a mandatory
step, a model eventually does — which is why the gate is a ``before_agent`` hook,
compiled to a real node, rather than something the supervisor may decide to call.

Import from the submodule — ``from app.core.langgraph.routing.classify import
llm_classify``. Re-exporting here would bind a *function* onto this package,
shadowing the submodule of the same name, so
``app.core.langgraph.routing.classify`` would no longer resolve to the module for
anything that patches or reloads it.
"""
