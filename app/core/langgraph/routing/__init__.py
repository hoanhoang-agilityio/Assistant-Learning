"""Routing: the one node where an LLM influences control flow.

``classify`` influences it by returning a validated ``IntentDecision`` — not by
choosing to call something. Turning that decision into a destination is plain
Python, and it happens later and elsewhere, at ``intent_branch``, once the
profile gate has run. Routing is never exposed as a tool: given the option to
skip a mandatory step, a model eventually does.

Import the nodes from their own modules — ``from
app.core.langgraph.routing.classify import classify``. Re-exporting them here
would bind a *function* named ``classify`` onto this package, shadowing the
submodule of the same name, so ``app.core.langgraph.routing.classify`` would no
longer resolve to the module for anything that patches or reloads it.
"""
