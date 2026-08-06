"""Routing nodes: an LLM classifier and a deterministic dispatcher.

Split deliberately. ``classify`` is the only place an LLM influences control
flow, and it does so by returning a validated ``IntentDecision`` — not by
choosing to call something. ``dispatch`` then maps that decision to a target
with plain Python. Routing is never exposed as a tool: given the option to skip
a mandatory step, a model eventually does.

Import the nodes from their own modules — ``from
app.core.langgraph.routing.classify import classify``. Re-exporting them here
would bind a *function* named ``classify`` onto this package, shadowing the
submodule of the same name, so ``app.core.langgraph.routing.classify`` would no
longer resolve to the module for anything that patches or reloads it.
"""
