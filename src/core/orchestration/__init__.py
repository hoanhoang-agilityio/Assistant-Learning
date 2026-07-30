"""LangGraph orchestration: the supervisor, the routing policy, and run execution.

Groups what were five sibling folders (`graph/`, `agents/`, `capabilities/`,
`hitl/`, `persist/`) under one name, because they are one concern: deciding which
capability runs next and driving the graph.

`capabilities/` became `routing/` here. It never held capabilities -- it held the
registry, policy engine, dispatcher and node adapters that route *to* them -- and
the misleading name was also occupying the folder `subgraphs/` needed.
"""
