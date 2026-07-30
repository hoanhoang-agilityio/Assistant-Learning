"""The ExecutionPlan kernel.

`schema.py` (7 external consumers) and `utils.py` (4) are read by fitness,
research, `llm/serializers`, `orchestration/graph/service` and `vfs/schema` --
so they are not planning-capability-private. Kept here rather than inside
`capabilities/planning/`, for the same reason `profile/` is here: everything
else would otherwise import from inside a capability's folder.

The planning *capability* (executor, node, output) lives in
`core/capabilities/planning/`.
"""
